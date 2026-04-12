"""Stock weight, sector weight, and winner drift concentration analyzer."""

from __future__ import annotations

import logging
from typing import Any

from vector.constants import INDEX_ETFS

_log = logging.getLogger(__name__)

_SEV_ORDER = {'none': 0, 'low': 1, 'moderate': 2, 'high': 3, 'critical': 4}


def _stock_severity(weight_pct: float, thresholds: dict) -> str:
    if weight_pct > thresholds.get('critical', 50):
        return 'critical'
    if weight_pct > thresholds.get('high', 40):
        return 'high'
    if weight_pct > thresholds.get('moderate', 30):
        return 'moderate'
    if weight_pct > thresholds.get('low', 20):
        return 'low'
    return 'none'


def analyze(
    positions: list[dict], store: Any, settings: dict, risk_profile: dict,
) -> dict:
    thresholds = risk_profile.get('concentration', {})
    # CURRENT market value total — matches _positions_summary canonical formula.
    total_current_value = sum(
        float(p.get('_current_value') or (float(p.get('shares', 0) or 0) * float(p.get('price', 0) or 0)))
        for p in positions
    ) or 1.0
    # Cost-basis total — used ONLY for entry-weight drift comparisons.
    total_cost_basis = sum(p.get('equity', 0.0) for p in positions) or 1.0

    ticker_results: dict[str, dict] = {}
    sector_weights: dict[str, float] = {}

    for pos in positions:
        t = pos['ticker']
        is_index = t in INDEX_ETFS
        shares = pos.get('shares', 0.0)
        cost_equity = pos.get('equity', 0.0)
        current_price = pos.get('price', 0.0)
        current_value = float(
            pos.get('_current_value')
            or (shares * current_price if current_price > 0 else cost_equity)
        )
        weight = current_value / total_current_value
        weight_pct = weight * 100

        # Cost-basis entry weight uses COST totals for both sides.
        entry_weight = cost_equity / total_cost_basis
        drift_multiple = weight / entry_weight if entry_weight > 0.001 else 1.0

        sub_signals: list[str] = []
        best_severity = 'none'

        # Sub-signal A: Stock concentration (suppressed for index ETFs)
        if not is_index:
            stock_sev = _stock_severity(weight_pct, thresholds)
            if stock_sev in ('moderate', 'high', 'critical'):
                sub_signals.append('stock_concentration')
                best_severity = stock_sev

        # Sub-signal C: Winner drift (suppressed for index ETFs)
        if not is_index and weight_pct > 30 and drift_multiple > 2.0:
            drift_sev = 'high' if drift_multiple > 2.5 else 'moderate'
            sub_signals.append('winner_drift')
            if _SEV_ORDER[drift_sev] > _SEV_ORDER[best_severity]:
                best_severity = drift_sev

        # Sub-signal B: accumulate sector weights (exclude index ETFs)
        if not is_index:
            sector = pos.get('sector') or 'Unknown'
            sector_weights[sector] = sector_weights.get(sector, 0.0) + current_value

        ticker_results[t] = {
            'value': weight_pct,
            'severity': best_severity,
            'flag': bool(sub_signals),
            'weight': weight,
            'details': {
                'sub_signals': sub_signals,
                'weight_pct': weight_pct,
                'entry_weight_pct': entry_weight * 100,
                'drift_multiple': drift_multiple,
                'heaviest_concentration_type': sub_signals[0] if sub_signals else 'none',
            },
        }

    # Sector over-concentration (portfolio level)
    sector_total = sum(sector_weights.values()) or 1.0
    sector_pcts = {s: v / sector_total * 100 for s, v in sector_weights.items()}
    known_sectors = [s for s in sector_pcts if s != 'Unknown']
    sector_count = len(known_sectors) or len(sector_pcts)

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
