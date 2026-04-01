"""Compute prioritized call-to-action list with dollar amounts."""

from __future__ import annotations

import logging
from typing import Any

from vector.constants import INDEX_ETFS, LOW_BETA_BY_SECTOR, SECTOR_SUGGESTIONS

_log = logging.getLogger(__name__)


def _round10(v: float) -> float:
    return round(v / 10) * 10


def _pick_sector_tickers(
    target_sector: str, held_tickers: set[str], n: int = 2,
) -> list[str]:
    """Pick suggestion tickers from SECTOR_SUGGESTIONS, excluding already-held."""
    candidates = SECTOR_SUGGESTIONS.get(target_sector, [])
    picks = [t for t in candidates if t not in held_tickers][:n]
    return picks or candidates[:n]


def _best_underweight_sector(
    sector_weights: dict[str, float],
    held_sectors: set[str],
) -> str:
    """Find the most underweight sector or a sector not yet held."""
    all_sectors = list(SECTOR_SUGGESTIONS.keys())
    # Prefer a sector not held at all
    for s in all_sectors:
        if s not in held_sectors:
            return s
    # All sectors held: pick the lightest
    if sector_weights:
        return min(sector_weights, key=sector_weights.get)
    return 'Technology'


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
    sell_scale = risk_profile.get('sell_scale', 0.75)

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
            sev_factor = 1.0 if sev == 'critical' else 0.7
            pos_value = ticker_weights.get(t, 0) * total_equity
            dollars = _round10(pos_value * sell_scale * sev_factor)
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
            sev_factor = 1.0 if sev == 'critical' else 0.5
            pos_value = ticker_weights.get(t, 0) * total_equity
            dollars = _round10(pos_value * sell_scale * sev_factor)
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
                        },
                    })

    # --- Priority 3: Winner drift (REBALANCE) ---
    for t, data in conc_res.get('ticker_results', {}).items():
        subs = data.get('details', {}).get('sub_signals', [])
        if 'winner_drift' in subs and data.get('flag'):
            entry_w = data['details'].get('entry_weight_pct', 25) / 100
            current_w = data.get('weight', 0)
            dollars = _round10((current_w - entry_w) * total_equity)
            if dollars > 0:
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
        # Pick low-beta tickers from sectors user already holds
        suggestions: list[str] = []
        for s in held_sectors:
            for lb_sector, lb_tickers in LOW_BETA_BY_SECTOR.items():
                if lb_sector == s:
                    for lt in lb_tickers:
                        if lt not in held_tickers and lt not in suggestions:
                            suggestions.append(lt)
                            if len(suggestions) >= 2:
                                break
            if len(suggestions) >= 2:
                break
        if not suggestions:
            # Fallback: pick from any sector
            for lb_tickers in LOW_BETA_BY_SECTOR.values():
                for lt in lb_tickers:
                    if lt not in held_tickers and lt not in suggestions:
                        suggestions.append(lt)
                        if len(suggestions) >= 2:
                            break
                if len(suggestions) >= 2:
                    break

        dollars = _round10(0.10 * total_equity)
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

    # --- Priority 6: Single-stock concentration (BUY) ---
    for t, data in conc_res.get('ticker_results', {}).items():
        subs = data.get('details', {}).get('sub_signals', [])
        if 'stock_concentration' in subs and data.get('flag'):
            if t in INDEX_ETFS or t in index_cta_tickers:
                continue
            target_weight = conc_res.get('_risk_profile', {}).get('concentration', {}).get(
                'moderate', 30,
            ) / 100
            # Actually get moderate from risk profile in pool results
            rp = pool_results.get('_risk_profile', {})
            target_weight = rp.get('concentration', {}).get('moderate', 30) / 100
            v_stock = ticker_weights.get(t, 0) * total_equity
            if target_weight > 0:
                v_total_new = v_stock / target_weight
                dollars = _round10(v_total_new - total_equity)
            else:
                dollars = 0.0

            uw_sector = _best_underweight_sector(sector_weights, held_sectors)
            suggested = _pick_sector_tickers(uw_sector, held_tickers)

            if dollars > 0:
                ctas.append({
                    'priority': 6,
                    'action': 'buy_new',
                    'ticker': suggested[0] if suggested else '',
                    'dollars': dollars,
                    'reason': 'reduce_concentration',
                    'severity': data['severity'],
                    'details': {
                        'heavy_ticker': t,
                        'current_weight': data.get('weight', 0) * 100,
                        'target_weight': target_weight * 100,
                        'target_sector': uw_sector,
                        'suggested_tickers': suggested,
                    },
                })

    # --- Priority 7: Sector over-concentration (BUY) ---
    port_conc = conc_res.get('portfolio_result', {})
    if port_conc.get('flag'):
        heavy_sector = port_conc['details'].get('heaviest_sector', '')
        heavy_pct = port_conc['details'].get('heaviest_sector_weight', 0)
        uw_sector = _best_underweight_sector(sector_weights, held_sectors - {heavy_sector})
        suggested = _pick_sector_tickers(uw_sector, held_tickers)

        # Amount to bring heaviest below 50%
        if heavy_pct > 50:
            sector_eq = (heavy_pct / 100) * total_equity
            target = 0.50
            v_total_new = sector_eq / target
            dollars = _round10(v_total_new - total_equity)
        else:
            dollars = _round10(0.10 * total_equity)

        if dollars > 0:
            ctas.append({
                'priority': 7,
                'action': 'buy_new',
                'ticker': suggested[0] if suggested else '',
                'dollars': dollars,
                'reason': 'sector_underweight',
                'severity': port_conc['severity'],
                'details': {
                    'heavy_sector': heavy_sector,
                    'sector_weight': heavy_pct,
                    'target_sector': uw_sector,
                    'suggested_tickers': suggested,
                },
            })

    # --- Priority 8: Dead weight (SELL) ---
    for t, s_data in slope_res.get('ticker_results', {}).items():
        w = ticker_weights.get(t, 0)
        ann = s_data.get('details', {}).get('annualized_pct', 0)
        if w < 0.02 and ann <= 2.0 and t not in INDEX_ETFS:
            pos_value = w * total_equity
            ctas.append({
                'priority': 8,
                'action': 'sell',
                'ticker': t,
                'dollars': _round10(pos_value),
                'reason': 'dead_weight',
                'severity': 'low',
                'details': {
                    'weight_pct': w * 100,
                    'position_value': pos_value,
                },
            })

    # --- Priority 9: Underrepresented sector (BUY) ---
    conc_details = port_conc.get('details', {})
    sector_wts = conc_details.get('sector_weights', {})
    sector_count = conc_details.get('sector_count', 0)
    if sector_count >= 3:
        # Find sectors with only 1 ticker and < 10% weight
        # Need to count tickers per sector from positions
        sector_ticker_map: dict[str, list[str]] = {}
        for t2 in held_tickers:
            # We need sector info — use sector_weights keys as proxy
            pass
        # Simpler: check from sector_wts
        for sector, sw_pct in sector_wts.items():
            if sw_pct < 10 and sector not in ('Unknown', ''):
                suggested = _pick_sector_tickers(sector, held_tickers)
                sector_val = (sw_pct / 100) * total_equity
                deposit = _round10((0.10 * total_equity - sector_val) / 0.90)
                if deposit > 0:
                    ctas.append({
                        'priority': 9,
                        'action': 'buy_new',
                        'ticker': suggested[0] if suggested else '',
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
                    break  # only flag the smallest underrepresented sector

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

    return ctas
