"""Compute prioritized call-to-action list with dollar amounts."""

from __future__ import annotations

import logging
from typing import Any

from vector.constants import INDEX_ETFS, LOW_BETA_BY_SECTOR, SECTOR_SUGGESTIONS

_log = logging.getLogger(__name__)


_MIN_SELL_DOLLARS = 500
_MIN_POSITION_VALUE_FOR_SELL = 1000


def _round10(v: float) -> float:
    return round(v / 10) * 10


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
        """
        if risk_tier != 'low':
            return False
        mc = _market_cap(ticker)
        # Missing data → assume large cap (safe default is to BLOCK the sell)
        if mc <= 0:
            mc = 100_000_000_000.0
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
            entry_w = data['details'].get('entry_weight_pct', 25) / 100
            current_w = ticker_weights.get(t, 0)
            position_value = summary.get('ticker_current_values', {}).get(t, current_w * total_equity)
            raw_rebalance = (current_w - entry_w) * total_equity
            # Cap rebalance at 35% of the position's current value
            max_rebalance = position_value * 0.35
            dollars = _round10(min(raw_rebalance, max_rebalance))
            print(
                f'[lens DEBUG] winner_drift {t}: current_weight={current_w:.3f}, '
                f'entry_weight={entry_w:.3f}, position_value=${position_value:,.0f}, '
                f'raw=${raw_rebalance:,.0f}, capped=${dollars:,.0f}'
            )
            if risk_tier != 'low' and _sell_too_small(dollars, position_value):
                continue
            if dollars > 0:
                if risk_tier == 'low':
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
                'reason': 'high_beta',
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
            rp = pool_results.get('_risk_profile', {})
            target_weight = rp.get('concentration', {}).get('moderate', 30) / 100
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

        # Calculate total dollars needed
        if heavy_pct > 50:
            sector_eq = (heavy_pct / 100) * total_equity
            target = 0.50
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
                        'sector_weight': heavy_pct,
                        'target_sector': sector,
                        'suggested_tickers': suggested,
                    },
                })

    # --- Priority 8: Dead weight (SELL — suppressed for conservative) ---
    if risk_tier != 'low':
        for t, s_data in slope_res.get('ticker_results', {}).items():
            w = ticker_weights.get(t, 0)
            ann = s_data.get('details', {}).get('annualized_pct', 0)
            if w < 0.02 and ann <= 2.0 and t not in INDEX_ETFS:
                pos_value = summary.get('ticker_current_values', {}).get(
                    t, w * total_equity,
                )
                dollars = _round10(pos_value)
                if _sell_too_small(dollars, pos_value):
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
    if sector_count >= 3:
        thin_sectors = sorted(
            ((s, w) for s, w in sector_wts.items()
             if w < 10 and s not in ('Unknown', '')),
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

    return ctas


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
