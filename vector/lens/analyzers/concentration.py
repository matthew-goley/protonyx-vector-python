"""Stock weight, sector weight, and winner drift concentration analyzer."""

from __future__ import annotations

import logging
from typing import Any

from vector.constants import INDEX_ETFS

_log = logging.getLogger(__name__)


def _stock_severity(weight_pct: float, thresholds: dict) -> str:
    crit = thresholds.get('critical', 50)
    high = thresholds.get('high', 40)
    mod = thresholds.get('moderate', 30)
    low = thresholds.get('low', 20)
    if weight_pct > crit:
        return 'critical'
    if weight_pct > high:
        return 'high'
    if weight_pct > mod:
        return 'moderate'
    if weight_pct > low:
        return 'low'
    return 'none'


def analyze(
    positions: list[dict], store: Any, settings: dict, risk_profile: dict,
) -> dict:
    thresholds = risk_profile.get('concentration', {})
    total_equity = sum(p.get('equity', 0.0) for p in positions) or 1.0

    ticker_results: dict[str, dict] = {}

    # Pre-compute entry weights (cost-basis approximation)
    total_cost_basis = sum(p.get('equity', 0.0) for p in positions) or 1.0

    for pos in positions:
        t = pos['ticker']
        shares = pos.get('shares', 0.0)
        cost_equity = pos.get('equity', 0.0)
        current_price = pos.get('price', 0.0)
        current_value = shares * current_price if current_price > 0 else cost_equity
        weight = current_value / total_equity
        weight_pct = weight * 100

        entry_weight = cost_equity / total_cost_basis if total_cost_basis > 0 else 0.0
        entry_weight_pct = entry_weight * 100
        drift_multiple = weight / entry_weight if entry_weight > 0.001 else 1.0

        sub_signals: list[str] = []
        best_severity = 'none'

        # Sub-signal A: Stock concentration
        stock_sev = _stock_severity(weight_pct, thresholds)
        stock_flag = stock_sev in ('moderate', 'high', 'critical')

        # Index ETFs don't trigger stock concentration
        if t in INDEX_ETFS:
            stock_flag = False
            stock_sev = 'none'

        if stock_flag:
            sub_signals.append('stock_concentration')
            best_severity = stock_sev

        # Sub-signal C: Winner drift
        drift_sev = 'none'
        if weight_pct > 30 and drift_multiple > 2.0 and t not in INDEX_ETFS:
            if drift_multiple > 2.5:
                drift_sev = 'high'
            else:
                drift_sev = 'moderate'
            sub_signals.append('winner_drift')
            # Take the worse severity
            sev_order = {'none': 0, 'low': 1, 'moderate': 2, 'high': 3, 'critical': 4}
            if sev_order.get(drift_sev, 0) > sev_order.get(best_severity, 0):
                best_severity = drift_sev

        flag = len(sub_signals) > 0

        ticker_results[t] = {
            'value': weight_pct,
            'severity': best_severity,
            'flag': flag,
            'weight': weight,
            'details': {
                'sub_signals': sub_signals,
                'weight_pct': weight_pct,
                'entry_weight_pct': entry_weight_pct,
                'drift_multiple': drift_multiple,
                'heaviest_concentration_type': (
                    'winner_drift' if 'winner_drift' in sub_signals
                    else 'stock_concentration' if 'stock_concentration' in sub_signals
                    else 'none'
                ),
            },
        }

    # Sub-signal B: Sector over-concentration (portfolio level)
    sector_weights: dict[str, float] = {}
    for pos in positions:
        t = pos['ticker']
        if t in INDEX_ETFS:
            continue  # exclude index funds from sector calculation
        sector = pos.get('sector') or 'Unknown'
        current_price = pos.get('price', 0.0)
        shares = pos.get('shares', 0.0)
        val = shares * current_price if current_price > 0 else pos.get('equity', 0.0)
        sector_weights[sector] = sector_weights.get(sector, 0.0) + val

    sector_total = sum(sector_weights.values()) or 1.0
    sector_pcts = {s: v / sector_total * 100 for s, v in sector_weights.items()}
    sector_count = len({s for s in sector_pcts if s != 'Unknown'}) or len(sector_pcts)

    heaviest_sector = max(sector_pcts, key=sector_pcts.get) if sector_pcts else 'Unknown'
    heaviest_pct = sector_pcts.get(heaviest_sector, 0.0)

    sector_mod = thresholds.get('sector_moderate', 50)
    if heaviest_pct > 60 or sector_count <= 1:
        sector_sev = 'high'
    elif heaviest_pct > sector_mod or sector_count <= 2:
        sector_sev = 'moderate'
    elif heaviest_pct > 40:
        sector_sev = 'low'
    else:
        sector_sev = 'none'

    return {
        'ticker_results': ticker_results,
        'portfolio_result': {
            'value': heaviest_pct,
            'severity': sector_sev,
            'flag': sector_sev in ('moderate', 'high', 'critical'),
            'details': {
                'concentration_type': 'sector',
                'heaviest_sector': heaviest_sector,
                'heaviest_sector_weight': heaviest_pct,
                'sector_count': sector_count,
                'sector_weights': sector_pcts,
            },
        },
    }
