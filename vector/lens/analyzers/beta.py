"""Per-ticker and portfolio-level beta analyzer."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from vector.analytics import portfolio_beta as _portfolio_beta

_log = logging.getLogger(__name__)


def _ticker_beta(ticker_prices: list[float], spy_prices: list[float]) -> float:
    """Compute beta of a single ticker against SPY."""
    n = min(len(ticker_prices), len(spy_prices))
    if n < 10:
        return 1.0
    t_arr = np.array(ticker_prices[-n:], dtype=float)
    s_arr = np.array(spy_prices[-n:], dtype=float)
    t_ret = np.diff(t_arr) / t_arr[:-1]
    s_ret = np.diff(s_arr) / s_arr[:-1]
    var_s = float(np.var(s_ret))
    if var_s < 1e-12:
        return 1.0
    return float(np.cov(t_ret, s_ret)[0][1] / var_s)


def _classify(beta: float, thresholds: dict[str, float]) -> str:
    crit = thresholds.get('critical', 1.8)
    high = thresholds.get('high', 1.3)
    mod = thresholds.get('moderate', 1.0)
    if beta > crit:
        return 'critical'
    if beta > high:
        return 'high'
    if beta > mod:
        return 'moderate'
    if beta > 0.5:
        return 'low'
    return 'none'


def analyze(
    positions: list[dict], store: Any, settings: dict, risk_profile: dict,
) -> dict:
    refresh = settings.get('refresh_interval', '5 min')
    thresholds = risk_profile.get('beta', {})
    def _cv(p: dict) -> float:
        cv = p.get('_current_value')
        if cv is not None:
            return float(cv)
        shares = float(p.get('shares', 0) or 0)
        price = float(p.get('price', 0) or 0)
        return shares * price if shares > 0 and price > 0 else float(p.get('equity', 0.0) or 0.0)

    total_equity = sum(_cv(p) for p in positions) or 1.0

    # Fetch SPY once
    try:
        spy_prices = store.get_history('SPY', '1y', refresh) or []
    except Exception:
        spy_prices = []

    ticker_results: dict[str, dict] = {}
    highest_beta_ticker = ''
    highest_beta = 0.0

    for pos in positions:
        t = pos['ticker']
        weight = _cv(pos) / total_equity
        try:
            hist = store.get_history(t, '1y', refresh) or []
            beta = _ticker_beta(hist, spy_prices) if len(spy_prices) >= 10 else 1.0
        except Exception:
            beta = 1.0

        sev = _classify(beta, thresholds)

        ticker_results[t] = {
            'value': beta,
            'severity': sev,
            'flag': sev in ('high', 'critical'),
            'weight': weight,
            'details': {'beta': beta},
        }

        if beta > highest_beta:
            highest_beta = beta
            highest_beta_ticker = t

    # Portfolio-level beta via weighted daily returns
    port_beta = 1.0
    try:
        closes_map = {}
        for pos in positions:
            t = pos['ticker']
            h = store.get_history(t, '1y', refresh) or []
            if h:
                closes_map[t] = h
        from vector.analytics import portfolio_daily_returns
        port_rets = portfolio_daily_returns(positions, closes_map)
        if len(port_rets) >= 10 and len(spy_prices) > 1:
            spy_rets = [(spy_prices[i] - spy_prices[i - 1]) / spy_prices[i - 1]
                        for i in range(1, len(spy_prices))]
            if len(spy_rets) >= 10:
                port_beta = _portfolio_beta(port_rets, spy_rets)
    except Exception:
        pass

    port_sev = _classify(port_beta, thresholds)

    return {
        'ticker_results': ticker_results,
        'portfolio_result': {
            'value': port_beta,
            'severity': port_sev,
            'flag': port_sev in ('high', 'critical'),
            'details': {
                'beta': port_beta,
                'highest_beta_ticker': highest_beta_ticker,
                'highest_beta': highest_beta,
            },
        },
    }
