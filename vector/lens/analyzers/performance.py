"""Unrealized P&L from cost basis analyzer."""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


def _classify(return_pct: float, thresholds: dict[str, float]) -> str:
    """Only flags losses — gains are severity 'none'."""
    crit = thresholds.get('critical', -40)
    high = thresholds.get('high', -25)
    mod = thresholds.get('moderate', -15)
    low = thresholds.get('low', -5)
    if return_pct < crit:
        return 'critical'
    if return_pct < high:
        return 'high'
    if return_pct < mod:
        return 'moderate'
    if return_pct < low:
        return 'low'
    return 'none'


def analyze(
    positions: list[dict], store: Any, settings: dict, risk_profile: dict,
) -> dict:
    thresholds = risk_profile.get('performance', {})
    total_equity = sum(p.get('equity', 0.0) for p in positions) or 1.0

    ticker_results: dict[str, dict] = {}
    total_cost_basis = 0.0
    total_current_value = 0.0
    worst_ticker = ''
    worst_return = 0.0

    for pos in positions:
        t = pos['ticker']
        shares = pos.get('shares', 0.0)
        cost_equity = pos.get('equity', 0.0)  # cost basis (shares × entry price)
        current_price = pos.get('price', 0.0)
        weight = cost_equity / total_equity

        entry_price = cost_equity / shares if shares > 0 else 0.0
        current_value = shares * current_price if current_price > 0 else cost_equity

        if entry_price > 0 and current_price > 0:
            unrealized_pct = (current_price / entry_price - 1) * 100
        else:
            unrealized_pct = 0.0

        unrealized_dollar = current_value - cost_equity

        total_cost_basis += cost_equity
        total_current_value += current_value

        sev = _classify(unrealized_pct, thresholds)

        ticker_results[t] = {
            'value': unrealized_pct,
            'severity': sev,
            'flag': sev in ('moderate', 'high', 'critical'),
            'weight': weight,
            'details': {
                'entry_price': entry_price,
                'current_price': current_price,
                'unrealized_return_pct': unrealized_pct,
                'unrealized_dollar': unrealized_dollar,
            },
        }

        if unrealized_pct < worst_return:
            worst_return = unrealized_pct
            worst_ticker = t

    total_unrealized_dollar = total_current_value - total_cost_basis
    total_unrealized_pct = (
        (total_unrealized_dollar / total_cost_basis * 100)
        if total_cost_basis > 0 else 0.0
    )
    port_sev = _classify(total_unrealized_pct, thresholds)

    return {
        'ticker_results': ticker_results,
        'portfolio_result': {
            'value': total_unrealized_pct,
            'severity': port_sev,
            'flag': port_sev in ('moderate', 'high', 'critical'),
            'details': {
                'total_unrealized_pct': total_unrealized_pct,
                'total_unrealized_dollar': total_unrealized_dollar,
                'worst_ticker': worst_ticker,
                'worst_return_pct': worst_return,
            },
        },
    }
