"""Compute prioritized call-to-action list with dollar amounts."""

from __future__ import annotations

import logging
from typing import Any

from vector.constants import INDEX_ETFS, LOW_BETA_BY_SECTOR, SECTOR_SUGGESTIONS, sector_for

_log = logging.getLogger(__name__)


_MIN_SELL_DOLLARS = 500
_MIN_POSITION_VALUE_FOR_SELL = 1000

# Dead-weight (priority 8) is a "clean up the odd-lot tail" suggestion, not a
# risk trim, so it is exempt from _MIN_POSITION_VALUE_FOR_SELL — which otherwise
# rejects every sub-2% position before it can ever be flagged, making the whole
# priority dead code. It only needs a tiny floor so we don't emit a sell on a
# literal penny stub.
_MIN_DEAD_WEIGHT_VALUE = 25.0

# Priority 9 (underrepresented sector) only nudges books that are not yet
# broadly diversified. A portfolio already spread across this many sectors is
# diversified enough that "deposit into a slightly-light sector" is noise (it
# was firing on near-perfect 10-sector books).
_DIVERSIFIED_SECTOR_COUNT = 6

# A concentration threshold is the weight ABOVE which a holding/sector is flagged.
# Diluting it back to that same threshold requires ~$0 for a position sitting right
# at the trigger (target == current weight → near-zero buy). We instead dilute toward
# a target that is this fraction of the trigger, so the recommended buy is always
# materially sized while still scaling with the user's chosen threshold.
_CONCENTRATION_DILUTION_FACTOR = 0.75

# Aggregate cap on all buy CTAs combined, by risk tier. Each buy priority is
# capped on its own, but several (high beta + concentration dilution + sector
# underweight) can stack; this keeps the *total* recommended new deposit to a
# sensible slice of the portfolio so a brief never asks the user to invest more
# than this at once. Conservative is capped tightest — a low-risk investor with
# a broken book should not be told to deposit a huge sum (and, because their
# sells are mostly suppressed, an uncapped buy total becomes the entire net
# CTA delta — see the Leverage-Lover deposit-into-a-fire case).
_MAX_TOTAL_BUY_FRACTION_BY_TIER = {'high': 0.35, 'regular': 0.30, 'low': 0.20}
_MAX_TOTAL_BUY_FRACTION = 0.30  # fallback when tier is unknown

# A buy CTA below this floor (the greater of an absolute $ and 1% of the book)
# is dropped — sub-1% "deposit $30 into KO" suggestions are noise, not advice.
_MIN_BUY_DOLLARS = 200.0
_MIN_BUY_FRACTION = 0.01

# When a genuinely dangerous book is generating NO sell/rebalance proceeds (sells
# suppressed by the conservative tier, or every signal resolved to a HOLD), the
# engine must not tell the user to deposit fresh capital into it. If this much of
# the book (by _danger_weight: critical at full weight, high at half) sits in
# dangerous positions and nothing is being freed, all diversification buys are
# dropped — the right posture is hold / de-risk, not "deposit into the fire".
_NO_DEPOSIT_DANGER_WEIGHT = 0.30

# Fresh-deposit advice is also dropped when this much of the book sits in
# positions with REALIZED weakness (a high/critical unrealized loss or steep
# decline). Depositing elsewhere does not remedy a realized loss, so a book whose
# defining feature is losers should be de-risked, not topped up. Set above a
# single mid-size decliner (~15%) so a lone declining name inside an otherwise
# concentration-driven book does not wipe legitimate diversification advice; it
# fires once losers are a substantial share of the book. Tier-independent: it
# reads analyzer severities, which are set even when a tier suppresses the sell.
_NO_DEPOSIT_LOSS_WEIGHT = 0.20


def _round10(v: float) -> float:
    return round(v / 10) * 10


def _floor10(v: float) -> float:
    """Round DOWN to the nearest 10. Used when scaling buys to a hard cap so the
    rounded total can never exceed the cap (a +$10 rounding overshoot otherwise
    left a 'redistribute' plan marginally net-positive)."""
    return float(int(v // 10) * 10) if v > 0 else 0.0


def _cap_buy_amount(raw_amount: float, total_equity: float, group_size: int) -> float:
    """Cap a buy CTA so a single suggestion stays realistic.

    - No single buy exceeds 25% of current portfolio value.
    - Combined buys in the same diversification group stay under 50% of portfolio.
    """
    if total_equity <= 0:
        return _round10(raw_amount)
    per_cta_cap = total_equity * 0.25
    if group_size > 1:
        group_cap = (total_equity * 0.50) / group_size
        per_cta_cap = min(per_cta_cap, group_cap)
    return _round10(min(raw_amount, per_cta_cap))


def _sell_too_small(dollars: float, position_value: float) -> bool:
    """True if a sell/rebalance CTA is too small to suggest."""
    if position_value < _MIN_POSITION_VALUE_FOR_SELL:
        return True
    if abs(dollars) < _MIN_SELL_DOLLARS:
        return True
    return False


def _get_ticker_sector(ticker: str) -> str:
    """Look up which sector a ticker belongs to using SECTOR_SUGGESTIONS."""
    for sector, tickers in SECTOR_SUGGESTIONS.items():
        if ticker in tickers:
            return sector
    return 'Unknown'


def _pick_sector_tickers(
    target_sector: str, held_tickers: set[str], n: int = 2,
) -> list[str]:
    """Pick suggestion tickers from SECTOR_SUGGESTIONS, excluding already-held."""
    candidates = SECTOR_SUGGESTIONS.get(target_sector, [])
    picks = [t for t in candidates if t not in held_tickers][:n]
    return picks or candidates[:n]


def _underweight_sectors_sorted(
    sector_weights: dict[str, float],
    held_sectors: set[str],
    exclude_sectors: set[str] | None = None,
) -> list[str]:
    """Return sectors sorted lightest-first, excluding specified sectors.

    Sectors not held at all come first, then held sectors by ascending weight.
    """
    exclude = exclude_sectors or set()
    all_sectors = list(SECTOR_SUGGESTIONS.keys())

    # Sectors not held at all (and not excluded)
    unheld = [s for s in all_sectors if s not in held_sectors and s not in exclude]
    # Held sectors sorted by weight ascending (excluding problem sectors)
    held_sorted = sorted(
        ((s, w) for s, w in sector_weights.items() if s not in exclude),
        key=lambda x: x[1],
    )
    held_names = [s for s, _ in held_sorted]

    return unheld + held_names


def _best_underweight_sector(
    sector_weights: dict[str, float],
    held_sectors: set[str],
    exclude_sectors: set[str] | None = None,
) -> str:
    """Find the most underweight sector, excluding specified sectors."""
    ranked = _underweight_sectors_sorted(sector_weights, held_sectors, exclude_sectors)
    return ranked[0] if ranked else 'Technology'


def compute_ctas(pool_results: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return a list of CTAs sorted by priority (1 = highest).

    Each CTA: {priority, action, ticker, dollars, reason, severity, details}
    """
    ctas: list[dict] = []

    summary = pool_results.get('_positions_summary', {})
    total_equity = summary.get('total_equity', 1.0)
    ticker_weights = summary.get('ticker_weights', {})
    sector_weights = summary.get('sector_weights', {})
    held_tickers = set(ticker_weights.keys())
    held_sectors = set(sector_weights.keys())

    risk_profile = pool_results.get('_risk_profile', {})
    sell_scale = risk_profile.get('sell_scale', 0.5)
    risk_tier = risk_profile.get('tier', 'regular')
    store = pool_results.get('_store')

    def _market_cap(ticker: str) -> float:
        """Return market cap in USD, or 0.0 if not known. Checks quote and meta."""
        if not store:
            return 0.0
        try:
            q = store.get_quote(ticker) or {}
            mc = q.get('market_cap') or q.get('marketCap')
            if mc:
                return float(mc)
            m = store.get_meta(ticker) or {}
            mc = m.get('market_cap') or m.get('marketCap')
            return float(mc) if mc else 0.0
        except Exception:
            return 0.0

    def _conservative_sell_blocked(
        ticker: str, severity: str, ticker_weight: float,
    ) -> bool:
        """Conservative tier: block most sell-type CTAs.

        Blocks if stock is > $5B market cap (assumes large-cap when unknown),
        if severity isn't critical, or if position weight < 5%.

        Exception: a position that dominates the book (> 50% weight) is always
        eligible to be trimmed — even a conservative investor should reduce a
        single holding that is more than half the portfolio. Without this, a
        78%-in-one-leveraged-ETF book had its sell suppressed and was instead
        told to *deposit* tens of thousands to dilute it (unactionable).
        """
        if risk_tier != 'low':
            return False
        if ticker_weight > 0.50:
            return False
        mc = _market_cap(ticker)
        # Missing market cap: normally assume large cap and BLOCK the sell (a safe
        # default for blue chips). BUT a CRITICAL-severity position with unknown
        # cap is almost always a speculative small-cap that genuinely needs
        # trimming — assuming large-cap there made the conservative tier go fully
        # silent (all HOLDs) on max-caution small-cap disasters. So only assume
        # large-cap for non-critical signals; let critical unknowns through.
        if mc <= 0:
            mc = 0.0 if severity == 'critical' else 100_000_000_000.0
        if mc > 5_000_000_000:
            return True
        if severity != 'critical':
            return True
        if ticker_weight < 0.05:
            return True
        return False

    slope_res = pool_results.get('slope', {})
    vol_res = pool_results.get('volatility', {})
    conc_res = pool_results.get('concentration', {})
    beta_res = pool_results.get('beta', {})
    idx_res = pool_results.get('index_fund', {})
    perf_res = pool_results.get('performance', {})

    # Track which tickers have index-fund CTAs (for suppression)
    index_cta_tickers: set[str] = set()

    # --- Priority 1: Steep decline (SELL) ---
    for t, data in slope_res.get('ticker_results', {}).items():
        if data.get('severity') in ('high', 'critical') and data.get('flag'):
            sev = data['severity']
            ticker_weight = ticker_weights.get(t, 0)
            if _conservative_sell_blocked(t, sev, ticker_weight):
                continue
            sev_factor = 1.0 if sev == 'critical' else 0.5
            pos_value = summary.get('ticker_current_values', {}).get(
                t, ticker_weight * total_equity,
            )
            dollars = _round10(pos_value * sell_scale * sev_factor)
            if _sell_too_small(dollars, pos_value):
                continue
            if dollars > 0:
                ctas.append({
                    'priority': 1,
                    'action': 'sell',
                    'ticker': t,
                    'dollars': dollars,
                    'reason': 'steep_decline',
                    'severity': sev,
                    'details': {
                        'slope_pct': data['details'].get('annualized_pct', 0),
                    },
                })

    # --- Priority 2: Excessive volatility (SELL) ---
    for t, data in vol_res.get('ticker_results', {}).items():
        if data.get('flag'):
            sev = data['severity']
            ticker_weight = ticker_weights.get(t, 0)
            if _conservative_sell_blocked(t, sev, ticker_weight):
                continue
            sev_factor = 1.0 if sev == 'critical' else 0.5
            pos_value = summary.get('ticker_current_values', {}).get(
                t, ticker_weight * total_equity,
            )
            dollars = _round10(pos_value * sell_scale * sev_factor)
            if _sell_too_small(dollars, pos_value):
                continue
            if dollars > 0:
                # Don't double-flag if already flagged for steep decline
                already = any(c['ticker'] == t and c['reason'] == 'steep_decline' for c in ctas)
                if not already:
                    ctas.append({
                        'priority': 2,
                        'action': 'sell',
                        'ticker': t,
                        'dollars': dollars,
                        'reason': 'high_volatility',
                        'severity': sev,
                        'details': {
                            'vol_pct': data['details'].get('annualized_vol', 0),
                            'weight_pct': data.get('weight', 0) * 100,
                        },
                    })

    # --- Priority 3: Winner drift (REBALANCE / informational HOLD for conservative) ---
    for t, data in conc_res.get('ticker_results', {}).items():
        subs = data.get('details', {}).get('sub_signals', [])
        if 'winner_drift' in subs and data.get('flag'):
            # A ticker already flagged for a steep-decline / high-volatility SELL
            # cannot also be a "runaway winner that drifted up" — emitting both is
            # contradictory (e.g. SELL FCEL + HOLD FCEL winner_drift). The risk
            # sell takes precedence; skip the drift signal for that ticker.
            if any(c.get('ticker') == t and c.get('action') == 'sell' for c in ctas):
                continue
            entry_w = data['details'].get('entry_weight_pct', 25) / 100
            current_w = ticker_weights.get(t, 0)
            position_value = summary.get('ticker_current_values', {}).get(t, current_w * total_equity)
            raw_rebalance = (current_w - entry_w) * total_equity
            # Cap rebalance at 35% of the position's current value
            max_rebalance = position_value * 0.35
            dollars = _round10(min(raw_rebalance, max_rebalance))
            _log.debug(
                'winner_drift %s: current_weight=%.3f, entry_weight=%.3f, '
                'position_value=$%.0f, raw=$%.0f, capped=$%.0f',
                t, current_w, entry_w, position_value, raw_rebalance, dollars,
            )
            if risk_tier != 'low' and _sell_too_small(dollars, position_value):
                continue
            if dollars > 0:
                # Conservative normally only *notes* a drifted winner. But a
                # position that dominates the book (>50%) should be trimmable
                # even for a low-risk investor — mirroring the >50% sell
                # exception in _conservative_sell_blocked — rather than left as
                # an informational hold while the buy-to-dilute path tells the
                # user to deposit fresh capital into a position that is already
                # most of their portfolio.
                if risk_tier == 'low' and current_w <= 0.50:
                    ctas.append({
                        'priority': 3,
                        'action': 'hold',
                        'ticker': t,
                        'dollars': 0.0,
                        'reason': 'winner_drift_informational',
                        'severity': data['severity'],
                        'details': {
                            'current_weight': current_w * 100,
                            'entry_weight': entry_w * 100,
                            'drift_multiple': data['details'].get('drift_multiple', 1),
                        },
                    })
                else:
                    ctas.append({
                        'priority': 3,
                        'action': 'rebalance',
                        'ticker': t,
                        'dollars': dollars,
                        'reason': 'winner_drift',
                        'severity': data['severity'],
                        'details': {
                            'current_weight': current_w * 100,
                            'entry_weight': entry_w * 100,
                            'drift_multiple': data['details'].get('drift_multiple', 1),
                        },
                    })

    # --- Priority 4: Index fund informational (HOLD) ---
    for t, data in idx_res.get('ticker_results', {}).items():
        if data.get('flag'):
            index_cta_tickers.add(t)
            ctas.append({
                'priority': 4,
                'action': 'hold',
                'ticker': t,
                'dollars': 0.0,
                'reason': 'index_fund_informational',
                'severity': 'moderate',
                'details': {
                    'weight_pct': data['details'].get('weight_pct', 0),
                    'fund_type': data['details'].get('fund_type', 'broad_market'),
                },
            })

    # --- Priority 5: High portfolio beta (BUY) ---
    port_beta = beta_res.get('portfolio_result', {})
    if port_beta.get('severity') in ('high', 'critical') and port_beta.get('flag'):
        # Identify sectors with concentration issues to avoid
        heavy_sector = conc_res.get('portfolio_result', {}).get(
            'details', {},
        ).get('heaviest_sector', '')
        avoid_sectors = {heavy_sector} if heavy_sector else set()

        # Pick low-beta tickers from underweight sectors, avoiding problem sectors
        suggestions: list[str] = []
        uw_sectors = _underweight_sectors_sorted(
            sector_weights, held_sectors, avoid_sectors,
        )
        for s in uw_sectors:
            lb_tickers = LOW_BETA_BY_SECTOR.get(s, [])
            for lt in lb_tickers:
                if lt not in held_tickers and lt not in suggestions:
                    if _get_ticker_sector(lt) not in avoid_sectors:
                        suggestions.append(lt)
                        if len(suggestions) >= 2:
                            break
            if len(suggestions) >= 2:
                break

        if not suggestions:
            # Fallback: pick from any sector (still checking sector)
            for lb_tickers in LOW_BETA_BY_SECTOR.values():
                for lt in lb_tickers:
                    if lt not in held_tickers and lt not in suggestions:
                        suggestions.append(lt)
                        if len(suggestions) >= 2:
                            break
                if len(suggestions) >= 2:
                    break

        dollars = _cap_buy_amount(0.10 * total_equity, total_equity, 1)
        if dollars > 0:
            ctas.append({
                'priority': 5,
                'action': 'buy_new',
                'ticker': suggestions[0] if suggestions else '',
                'dollars': dollars,
                'reason': 'reduce_beta',
                'severity': port_beta['severity'],
                'details': {
                    'portfolio_beta': port_beta['details'].get('beta', 1.0),
                    'suggested_tickers': suggestions,
                },
            })

    # --- Priority 6: Single-stock concentration (BUY — up to 3 CTAs) ---
    for t, data in conc_res.get('ticker_results', {}).items():
        subs = data.get('details', {}).get('sub_signals', [])
        if 'stock_concentration' in subs and data.get('flag'):
            if t in INDEX_ETFS or t in index_cta_tickers:
                continue

            current_w = ticker_weights.get(t, 0)
            # A single position that is more than half the book is TRIMMED, not
            # diluted with fresh deposits. Telling someone with 60%+ in one name
            # to deposit cash into other sectors is unactionable — mirror the
            # >50% sell exceptions elsewhere and trim toward the target, for every
            # tier. Always skip the buy-to-dilute path for such a position.
            if current_w > 0.50:
                # An existing winner-drift rebalance is already a proper trim —
                # leave it (its narrative is more informative).
                has_rebalance = any(
                    c.get('ticker') == t and c.get('action') == 'rebalance'
                    for c in ctas
                )
                if not has_rebalance:
                    rp = pool_results.get('_risk_profile', {})
                    trigger_pct = rp.get('concentration', {}).get('moderate', 30)
                    target_weight = (trigger_pct * _CONCENTRATION_DILUTION_FACTOR) / 100
                    pos_value = summary.get('ticker_current_values', {}).get(
                        t, current_w * total_equity,
                    )
                    raw_trim = (current_w - target_weight) * total_equity
                    trim = _round10(min(raw_trim, pos_value * 0.35))
                    # The trim supersedes a SMALLER same-direction risk sell: a
                    # tier-scaled vol/decline sell (conservative sell_scale 0.10)
                    # would otherwise leave a 76% position barely reduced. Keep
                    # whichever de-risks more.
                    existing_sells = [
                        c for c in ctas
                        if c.get('ticker') == t and c.get('action') == 'sell'
                    ]
                    sell_max = max(
                        (abs(float(c.get('dollars', 0.0) or 0.0)) for c in existing_sells),
                        default=0.0,
                    )
                    if trim > 0 and trim >= sell_max:
                        ctas = [
                            c for c in ctas
                            if not (c.get('ticker') == t and c.get('action') == 'sell')
                        ]
                        ctas.append({
                            'priority': 6,
                            'action': 'rebalance',
                            'ticker': t,
                            'dollars': trim,
                            'reason': 'reduce_concentration',
                            'severity': data['severity'],
                            'details': {
                                'current_weight': current_w * 100,
                                'target_weight': target_weight * 100,
                                'heavy_ticker': t,
                            },
                        })
                continue

            rp = pool_results.get('_risk_profile', {})
            # Dilute toward a target safely BELOW the trigger threshold (see
            # _CONCENTRATION_DILUTION_FACTOR) — diluting back to the trigger itself
            # produces a ~$0 buy for a stock sitting right at it.
            trigger_pct = rp.get('concentration', {}).get('moderate', 30)
            target_weight = (trigger_pct * _CONCENTRATION_DILUTION_FACTOR) / 100
            v_stock = summary.get('ticker_current_values', {}).get(
                t, ticker_weights.get(t, 0) * total_equity,
            )
            if target_weight > 0:
                v_total_new = v_stock / target_weight
                total_dollars = _round10(v_total_new - total_equity)
            else:
                total_dollars = 0.0

            if total_dollars <= 0:
                continue

            # Find the sector of the concentrated ticker to exclude it
            ticker_sector = _get_ticker_sector(t)
            # Also check positions for actual sector
            for pos in pool_results.get('_positions_summary', {}).get('positions', []):
                if isinstance(pos, dict) and pos.get('ticker') == t:
                    ticker_sector = pos.get('sector', ticker_sector)
                    break
            if ticker_sector == 'Unknown':
                for s, sw in sector_weights.items():
                    if sw > 0.4:
                        ticker_sector = s
                        break

            exclude = {ticker_sector} if ticker_sector != 'Unknown' else set()
            uw_sectors = _underweight_sectors_sorted(
                sector_weights, held_sectors, exclude,
            )[:3]

            if not uw_sectors:
                uw_sectors = _underweight_sectors_sorted(
                    sector_weights, held_sectors,
                )[:3]

            # Split dollars across underweight sectors proportionally
            allocations = _split_dollars_by_underweight(
                uw_sectors, sector_weights, total_dollars,
            )

            group_size = max(len(allocations), 1)
            for sector, alloc_dollars in allocations:
                suggested = _pick_sector_tickers(sector, held_tickers, n=1)
                if suggested and _get_ticker_sector(suggested[0]) in exclude:
                    suggested = []
                if not suggested:
                    continue
                capped_dollars = _cap_buy_amount(alloc_dollars, total_equity, group_size)
                if capped_dollars <= 0:
                    continue
                ctas.append({
                    'priority': 6,
                    'action': 'buy_new',
                    'ticker': suggested[0],
                    'dollars': capped_dollars,
                    'reason': 'reduce_concentration',
                    'severity': data['severity'],
                    'details': {
                        'heavy_ticker': t,
                        'current_weight': data.get('weight', 0) * 100,
                        'target_weight': target_weight * 100,
                        'target_sector': sector,
                        'suggested_tickers': suggested,
                    },
                })

    # --- Priority 7: Sector over-concentration (BUY — up to 3 CTAs) ---
    port_conc = conc_res.get('portfolio_result', {})
    if port_conc.get('flag'):
        heavy_sector = port_conc['details'].get('heaviest_sector', '')
        heavy_pct = port_conc['details'].get('heaviest_sector_weight', 0)

        # Calculate total dollars needed. Same trigger-vs-target collision as
        # single-stock concentration: dilute toward a target BELOW the sector
        # trigger, not back to the trigger itself.
        sector_trigger = risk_profile.get('concentration', {}).get('sector_moderate', 50)
        if heavy_pct > sector_trigger:
            sector_eq = (heavy_pct / 100) * total_equity
            target = (sector_trigger * _CONCENTRATION_DILUTION_FACTOR) / 100
            v_total_new = sector_eq / target
            total_dollars = _round10(v_total_new - total_equity)
        else:
            total_dollars = _round10(0.10 * total_equity)

        if total_dollars > 0:
            exclude = {heavy_sector} if heavy_sector else set()
            uw_sectors = _underweight_sectors_sorted(
                sector_weights, held_sectors, exclude,
            )[:3]

            if not uw_sectors:
                uw_sectors = _underweight_sectors_sorted(
                    sector_weights, held_sectors,
                )[:3]

            allocations = _split_dollars_by_underweight(
                uw_sectors, sector_weights, total_dollars,
            )

            group_size = max(len(allocations), 1)
            for sector, alloc_dollars in allocations:
                suggested = _pick_sector_tickers(sector, held_tickers, n=1)
                # Verify suggested ticker is NOT in the heavy sector
                if suggested and _get_ticker_sector(suggested[0]) == heavy_sector:
                    suggested = []
                    candidates = SECTOR_SUGGESTIONS.get(sector, [])
                    for c in candidates:
                        if c not in held_tickers and _get_ticker_sector(c) != heavy_sector:
                            suggested = [c]
                            break
                if not suggested:
                    continue
                capped_dollars = _cap_buy_amount(alloc_dollars, total_equity, group_size)
                if capped_dollars <= 0:
                    continue
                ctas.append({
                    'priority': 7,
                    'action': 'buy_new',
                    'ticker': suggested[0],
                    'dollars': capped_dollars,
                    'reason': 'sector_underweight',
                    'severity': port_conc['severity'],
                    'details': {
                        'heavy_sector': heavy_sector,
                        # The sentence reports this as the TARGET sector's exposure,
                        # so it must be the target's weight — not the heavy sector's.
                        'sector_weight': round(sector_weights.get(sector, 0.0) * 100, 1),
                        'target_sector': sector,
                        'suggested_tickers': suggested,
                    },
                })

    # --- Priority 8: Dead weight (SELL — suppressed for conservative) ---
    # A sub-2% odd-lot is clutter regardless of its slope. The old near-flat
    # slope gate (ann <= 2.0) made this priority effectively dead code — real
    # odd-lots are rarely flat — so flag on weight + dollar value alone.
    if risk_tier != 'low':
        for t in slope_res.get('ticker_results', {}):
            w = ticker_weights.get(t, 0)
            if w < 0.02 and t not in INDEX_ETFS:
                pos_value = summary.get('ticker_current_values', {}).get(
                    t, w * total_equity,
                )
                dollars = _round10(pos_value)
                # Dead-weight is exempt from the generic sell floors (a tiny
                # odd-lot is BY DEFINITION below them); only skip penny stubs.
                if pos_value < _MIN_DEAD_WEIGHT_VALUE or dollars <= 0:
                    continue
                # Don't tag a position as dead weight if a stronger signal is
                # already selling/trimming it.
                if any(c.get('ticker') == t and c.get('action') in ('sell', 'rebalance')
                       for c in ctas):
                    continue
                ctas.append({
                    'priority': 8,
                    'action': 'sell',
                    'ticker': t,
                    'dollars': dollars,
                    'reason': 'dead_weight',
                    'severity': 'low',
                    'details': {
                        'weight_pct': w * 100,
                        'position_value': pos_value,
                    },
                })

    # --- Priority 9: Underrepresented sector (BUY — up to 3 CTAs) ---
    conc_details = port_conc.get('details', {})
    sector_wts = conc_details.get('sector_weights', {})
    sector_count = conc_details.get('sector_count', 0)
    # Only nudge books that hold a few sectors but aren't yet broadly diversified
    # (3..<6). A book already spread across 6+ sectors is diversified enough that
    # filling a slightly-light sector is noise, not advice.
    if 3 <= sector_count < _DIVERSIFIED_SECTOR_COUNT:
        # A sector that is "thin" only because its single holding is a sub-2%
        # odd-lot is not genuinely missing — don't recommend buying into it while
        # the odd-lot itself should be cleaned up (sell T, buy GOOGL). Derive this
        # from the holdings directly (sub-2% weight) rather than from emitted
        # dead_weight CTAs, so the exclusion ALSO applies to the conservative
        # tier, which suppresses dead_weight sells and would otherwise be told to
        # deposit into the very sector holding the stub it can't sell.
        dead_weight_sectors = {
            sector_for(t)
            for t, w in ticker_weights.items()
            if w < 0.02 and t not in INDEX_ETFS
        }
        thin_sectors = sorted(
            ((s, w) for s, w in sector_wts.items()
             if w < 10 and s not in ('Unknown', '') and s not in dead_weight_sectors),
            key=lambda x: x[1],
        )
        cta_count = 0
        group_size = min(len(thin_sectors), 3)
        for sector, sw_pct in thin_sectors:
            if cta_count >= 3:
                break
            suggested = _pick_sector_tickers(sector, held_tickers, n=1)
            sector_val = (sw_pct / 100) * total_equity
            raw_deposit = (0.10 * total_equity - sector_val) / 0.90
            deposit = _cap_buy_amount(raw_deposit, total_equity, group_size)
            if deposit > 0 and suggested:
                ctas.append({
                    'priority': 9,
                    'action': 'buy_new',
                    'ticker': suggested[0],
                    'dollars': deposit,
                    'reason': 'sector_underweight',
                    'severity': 'low',
                    'details': {
                        'heavy_sector': sector,
                        'sector_weight': sw_pct,
                        'target_sector': sector,
                        'suggested_tickers': suggested,
                    },
                })
                cta_count += 1

    # --- Priority 10: Unrealized loss (HOLD) ---
    for t, data in perf_res.get('ticker_results', {}).items():
        if data.get('flag'):
            # If this ticker is already being sold/trimmed, an informational
            # "underwater, holding the rest" line is redundant and reads as a
            # contradiction (SELL X + HOLD X) — the sell already conveys intent.
            if any(c.get('ticker') == t and c.get('action') in ('sell', 'rebalance')
                   for c in ctas):
                continue
            ctas.append({
                'priority': 10,
                'action': 'hold',
                'ticker': t,
                'dollars': 0.0,
                'reason': 'unrealized_loss',
                'severity': data['severity'],
                'details': {
                    'unrealized_pct': data['details'].get('unrealized_return_pct', 0),
                    'unrealized_dollar': data['details'].get('unrealized_dollar', 0),
                    'entry_price': data['details'].get('entry_price', 0),
                },
            })

    # --- Priority 11: Portfolio healthy (HOLD) ---
    if not ctas:
        ctas.append({
            'priority': 11,
            'action': 'hold',
            'ticker': '',
            'dollars': 0.0,
            'reason': 'portfolio_healthy',
            'severity': 'none',
            'details': {},
        })

    # Sort by priority
    ctas.sort(key=lambda c: c['priority'])

    # Suppress buy CTAs that target index fund tickers
    if index_cta_tickers:
        ctas = [
            c for c in ctas
            if not (c['action'] in ('buy_new', 'buy_more')
                    and c.get('ticker') in index_cta_tickers)
        ]

    ctas = _dedupe_ctas(ctas)

    # Drop sub-threshold buy noise, then keep the combined buy recommendation
    # within a sensible slice of the portfolio. The slice is tier-aware AND
    # danger-aware: the more of the book that sits in critical positions, the
    # less we recommend depositing, scaling to zero for a book that is wholly in
    # crisis — it should be de-risked (trim/sell), not topped up. This is what
    # stops the "deposit $13,800 into a leveraged-ETF fire" recommendation.
    ctas = _drop_tiny_buys(ctas, total_equity)
    base_fraction = _MAX_TOTAL_BUY_FRACTION_BY_TIER.get(risk_tier, _MAX_TOTAL_BUY_FRACTION)
    danger = _danger_weight(pool_results, ticker_weights)
    buy_fraction = base_fraction * max(0.0, 1.0 - danger)
    ctas = _cap_total_buys(ctas, total_equity, buy_fraction)
    # _cap_total_buys scales buys DOWN, which can push a buy back below the noise
    # floor — re-drop tiny buys so a scaled-down "deposit $80" never survives.
    ctas = _drop_tiny_buys(ctas, total_equity)

    # Trim redistribution: a concentration / winner-drift trim should REDISTRIBUTE
    # its proceeds, not be topped up with fresh capital — cap the combined buys to
    # the amount trimmed so the plan stays net <= 0. A plain risk SELL does NOT cap
    # diversification buys: a small volatility trim on one rising name must not wipe
    # the advice to diversify an over-concentrated book (that conflation silently
    # dropped diversification at the moderate tier that both neighbouring tiers
    # gave). Dangerous books are instead handled by the loss/danger gate below.
    rebalance_total = sum(
        abs(float(c.get('dollars', 0.0) or 0.0))
        for c in ctas if c.get('action') == 'rebalance'
    )
    has_rebalance = rebalance_total > 0
    if has_rebalance and total_equity > 0:
        ctas = _cap_total_buys(ctas, total_equity, rebalance_total / total_equity)
        ctas = _drop_tiny_buys(ctas, total_equity)

    # Don't deposit fresh capital into a book whose dominant risk is realized
    # loss/decline, or that is broadly dangerous — when there is no trim to
    # redistribute, drop the diversification buys entirely. A book whose only issue
    # is STRUCTURAL (concentration / volatility / beta on names that are not
    # losing) keeps its buys, because those buys are themselves the remedy. The
    # loss test is tier-independent, so it also covers the conservative tier whose
    # protective sells are blocked.
    if not has_rebalance and total_equity > 0:
        loss = _loss_weight(pool_results, ticker_weights)
        if danger >= _NO_DEPOSIT_DANGER_WEIGHT or loss >= _NO_DEPOSIT_LOSS_WEIGHT:
            ctas = [c for c in ctas if c.get('action') not in ('buy_new', 'buy_more')]

    # Keep a flagged single-stock concentration visible even when its dilution buys
    # were dropped/capped above — otherwise a dominant holding (e.g. 49% of the
    # book) can vanish from the readout entirely.
    _add_concentration_informational(ctas, conc_res, ticker_weights, risk_profile)

    # Never return an empty list: if every buy was dropped and nothing else remains,
    # synthesise a closing HOLD so the readout always has a card — the caution
    # variant when the book is genuinely risky, otherwise the healthy line.
    if not ctas:
        elevated = (
            danger >= _NO_DEPOSIT_DANGER_WEIGHT
            or _loss_weight(pool_results, ticker_weights) >= _NO_DEPOSIT_LOSS_WEIGHT
        )
        ctas.append({
            'priority': 11,
            'action': 'hold',
            'ticker': '',
            'dollars': 0.0,
            'reason': 'portfolio_caution' if elevated else 'portfolio_healthy',
            'severity': 'high' if elevated else 'none',
            'details': {},
        })

    # Buy CTAs describe a routine, approachable action (deposit into a sector or a
    # low-beta name). Tagging them with the *problem's* critical/high severity
    # overstates the urgency of the buy itself, so cap their displayed severity at
    # moderate. Buy templates key only on 'default', so rendering is unchanged —
    # this only affects the severity label/colour shown to the user.
    for c in ctas:
        if c.get('action') in ('buy_new', 'buy_more') and c.get('severity') in ('high', 'critical'):
            c['severity'] = 'moderate'

    return ctas


def _drop_tiny_buys(cta_list: list[dict], total_equity: float) -> list[dict]:
    """Remove buy CTAs whose dollar amount is below the noise floor (the greater
    of ``_MIN_BUY_DOLLARS`` and ``_MIN_BUY_FRACTION`` of the book). Sells/holds
    are untouched."""
    floor = max(_MIN_BUY_DOLLARS, total_equity * _MIN_BUY_FRACTION) if total_equity > 0 else _MIN_BUY_DOLLARS
    return [
        c for c in cta_list
        if not (c.get('action') in ('buy_new', 'buy_more')
                and float(c.get('dollars', 0.0) or 0.0) < floor)
    ]


def _cap_total_buys(
    cta_list: list[dict], total_equity: float, max_fraction: float,
) -> list[dict]:
    """Scale all buy CTAs down proportionally so their combined dollars stay within
    ``max_fraction`` of portfolio value. A fraction of 0 scales every buy to zero
    (and drops it) — used when the book is in crisis. Sells and holds are
    untouched. Buys that round to zero after scaling are dropped."""
    if total_equity <= 0:
        return cta_list
    buys = [c for c in cta_list if c.get('action') in ('buy_new', 'buy_more')]
    total_buy = sum(float(c.get('dollars', 0.0) or 0.0) for c in buys)
    cap = total_equity * max(0.0, max_fraction)
    if total_buy <= cap or total_buy <= 0:
        return cta_list
    scale = cap / total_buy
    for c in buys:
        # Floor (not round) so the scaled total can never exceed the cap — keeps a
        # 'redistribute the trim' plan from going marginally net-positive.
        c['dollars'] = _floor10(float(c.get('dollars', 0.0) or 0.0) * scale)
    return [
        c for c in cta_list
        if not (c.get('action') in ('buy_new', 'buy_more')
                and float(c.get('dollars', 0.0) or 0.0) <= 0)
    ]


def _danger_weight(
    pool_results: dict[str, Any], ticker_weights: dict[str, float],
) -> float:
    """Fraction of portfolio weight in dangerous positions, used to throttle
    'deposit fresh capital' advice.

    Critical-severity exposure (volatility / performance / slope / concentration)
    counts at FULL weight; high-severity (non-critical) at HALF. The half-weight
    high term is what stops a book full of deep-but-not-catastrophic losers from
    still being told to deposit fresh capital — at the aggressive tier the
    performance ``critical`` threshold is -60%, so -40..-55% losers register as
    ``high`` and would otherwise escape a critical-only throttle. Mirrors the
    breadth lift in ``lens_output._risk_floor``. Returns 0.0 for any healthy/mild
    book, so normal diversification buys are unaffected.
    """
    def _sev(key: str, t: str) -> str:
        return (
            (pool_results.get(key, {}) or {})
            .get('ticker_results', {})
            .get(t, {})
            .get('severity', 'none')
        )

    crit = 0.0
    high = 0.0
    for t, w in ticker_weights.items():
        sevs = [_sev(k, t) for k in ('volatility', 'performance', 'slope', 'concentration')]
        if any(s == 'critical' for s in sevs):
            crit += w
        elif any(s == 'high' for s in sevs):
            high += w
    return min(1.0, crit + 0.5 * high)


def _loss_weight(
    pool_results: dict[str, Any], ticker_weights: dict[str, float],
) -> float:
    """Fraction of the book in positions showing REALIZED weakness — a high/critical
    unrealized loss (performance) or steep decline (slope).

    Fresh deposits do not remedy a realized loss, so this gates 'deposit to
    diversify' advice. Crucially it does NOT count volatility / beta /
    concentration: those are structural risks that diversification and
    stabilization buys genuinely DO remedy (a 55% *rising* winner or a high-beta
    book should still be allowed to diversify), which is what keeps a small,
    unrelated volatility trim from wiping legitimate concentration advice. Reads
    analyzer severities directly, so it is tier-independent (set even when a tier
    suppresses the sell).
    """
    def _sev(key: str, t: str) -> str:
        return (
            (pool_results.get(key, {}) or {})
            .get('ticker_results', {})
            .get(t, {})
            .get('severity', 'none')
        )

    total = 0.0
    for t, w in ticker_weights.items():
        if (_sev('performance', t) in ('high', 'critical')
                or _sev('slope', t) in ('high', 'critical')):
            total += w
    return total


def _add_concentration_informational(
    ctas: list[dict],
    conc_res: dict[str, Any],
    ticker_weights: dict[str, float],
    risk_profile: dict[str, Any],
) -> None:
    """Append an informational HOLD for a flagged single-stock concentration whose
    dilution buys were dropped/capped, so a dominant holding never vanishes from
    the readout. Mutates ``ctas`` in place. Skips a name that already has any CTA
    or is the ``heavy_ticker`` behind a surviving buy (already represented)."""
    trigger = risk_profile.get('concentration', {}).get('moderate', 30) / 100.0
    represented: set[str] = set()
    for c in ctas:
        if c.get('ticker'):
            represented.add(c['ticker'])
        heavy = (c.get('details', {}) or {}).get('heavy_ticker')
        if heavy:
            represented.add(heavy)

    for t, data in conc_res.get('ticker_results', {}).items():
        subs = (data.get('details', {}) or {}).get('sub_signals', [])
        if 'stock_concentration' not in subs or not data.get('flag'):
            continue
        if t in represented or t in INDEX_ETFS:
            continue
        w = ticker_weights.get(t, 0.0)
        if w < trigger:
            continue
        ctas.append({
            'priority': 6,
            'action': 'hold',
            'ticker': t,
            'dollars': 0.0,
            'reason': 'concentration_informational',
            'severity': data.get('severity', 'high'),
            'details': {'current_weight': w * 100, 'weight_pct': w * 100},
        })
        represented.add(t)


def _dedupe_ctas(cta_list: list[dict]) -> list[dict]:
    """Remove duplicate CTAs, resolve action conflicts, and cap per-sector buys.

    - Same (action, ticker) collapses to the highest-priority (lowest number).
    - A ticker may carry at most one sell-group action (sell OR rebalance).
    - Buy CTAs are capped at 3 per target sector across the whole list.
    """
    # Step 1: dedupe by (action, ticker)
    seen: dict[tuple[str, str], dict] = {}
    for cta in cta_list:
        key = (cta['action'], cta.get('ticker', ''))
        if key not in seen or cta['priority'] < seen[key]['priority']:
            seen[key] = cta

    # Step 2: resolve sell vs rebalance conflicts on the same ticker
    by_slot: dict[tuple[str, str], dict] = {}
    for cta in seen.values():
        ticker = cta.get('ticker', '')
        action = cta['action']
        if action in ('sell', 'rebalance') and ticker:
            slot = (ticker, '_sell_group')
            prev = by_slot.get(slot)
            if prev is None or cta['priority'] < prev['priority']:
                by_slot[slot] = cta
        else:
            by_slot[(ticker, action)] = cta

    deduped = list(by_slot.values())
    deduped.sort(key=lambda c: c['priority'])

    # Cap buys per target sector at 3
    sector_counts: dict[str, int] = {}
    capped: list[dict] = []
    for cta in deduped:
        if cta['action'] in ('buy_new', 'buy_more'):
            sector = (cta.get('details', {}) or {}).get('target_sector', '')
            if sector:
                if sector_counts.get(sector, 0) >= 3:
                    continue
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
        capped.append(cta)

    return capped


def _split_dollars_by_underweight(
    sectors: list[str],
    sector_weights: dict[str, float],
    total_dollars: float,
) -> list[tuple[str, float]]:
    """Split total_dollars across sectors proportional to how underweight each is.

    Sectors not held at all get the largest share. Returns list of
    (sector, dollars) sorted by allocation descending.
    """
    if not sectors:
        return []

    # Compute "underweight score" — higher means more underweight
    avg_weight = (100.0 / max(len(SECTOR_SUGGESTIONS), 1))
    scores: list[tuple[str, float]] = []
    for s in sectors:
        current = sector_weights.get(s, 0.0)
        score = max(avg_weight - current, 1.0)
        scores.append((s, score))

    total_score = sum(sc for _, sc in scores)
    if total_score <= 0:
        # Equal split fallback
        per = _round10(total_dollars / len(sectors))
        return [(s, per) for s in sectors]

    allocations: list[tuple[str, float]] = []
    for s, sc in scores:
        alloc = _round10((sc / total_score) * total_dollars)
        if alloc > 0:
            allocations.append((s, alloc))

    # Sort largest allocation first
    allocations.sort(key=lambda x: x[1], reverse=True)
    return allocations
