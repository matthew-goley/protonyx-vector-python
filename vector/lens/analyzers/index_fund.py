"""Index ETF detection analyzer."""

from __future__ import annotations

import logging
from typing import Any

from vector.constants import INDEX_ETFS, INDEX_FUND_TYPES

_log = logging.getLogger(__name__)


def analyze(
    positions: list[dict], store: Any, settings: dict, risk_profile: dict,
) -> dict:
    def _cv(p: dict) -> float:
        cv = p.get('_current_value')
        if cv is not None:
            return float(cv)
        shares = float(p.get('shares', 0) or 0)
        price = float(p.get('price', 0) or 0)
        return shares * price if shares > 0 and price > 0 else float(p.get('equity', 0.0) or 0.0)

    total_equity = sum(_cv(p) for p in positions) or 1.0

    ticker_results: dict[str, dict] = {}
    total_index_weight = 0.0
    index_tickers: list[str] = []
    dominant_index = ''
    dominant_weight = 0.0

    for pos in positions:
        t = pos['ticker']
        weight = _cv(pos) / total_equity
        weight_pct = weight * 100
        is_index = t in INDEX_ETFS

        fund_type = INDEX_FUND_TYPES.get(t, 'other') if is_index else 'other'

        flag = is_index and weight_pct > 30
        sev = 'moderate' if flag else 'none'

        ticker_results[t] = {
            'value': weight_pct,
            'severity': sev,
            'flag': flag,
            'weight': weight,
            'details': {
                'is_index': is_index,
                'weight_pct': weight_pct,
                'fund_type': fund_type,
            },
        }

        if is_index:
            total_index_weight += weight_pct
            index_tickers.append(t)
            if weight_pct > dominant_weight:
                dominant_weight = weight_pct
                dominant_index = t

    port_flag = total_index_weight > 30

    return {
        'ticker_results': ticker_results,
        'portfolio_result': {
            'value': total_index_weight,
            'severity': 'moderate' if port_flag else 'none',
            'flag': port_flag,
            'details': {
                'total_index_weight': total_index_weight,
                'index_tickers': index_tickers,
                'dominant_index': dominant_index or None,
            },
        },
    }
