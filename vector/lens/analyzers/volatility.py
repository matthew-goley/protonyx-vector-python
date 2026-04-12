"""Per-ticker and portfolio-level volatility analyzer."""

from __future__ import annotations

import logging
import math
from math import sqrt
from typing import Any

import numpy as np

_log = logging.getLogger(__name__)

_MIN_DATA_POINTS = 30
_VOL_CLAMP_MIN = 0.0
_VOL_CLAMP_MAX = 150.0


def _annualized_vol(prices: list[float], ticker: str = '') -> float:
    clean = [p for p in prices if p is not None and not math.isnan(p) and p > 0]
    if len(clean) < _MIN_DATA_POINTS:
        if prices:
            _log.debug(
                'volatility skipped for %s: bad_data (have=%d, need=%d)',
                ticker, len(clean), _MIN_DATA_POINTS,
            )
        return 0.0
    arr = np.array(clean, dtype=float)
    log_returns = np.diff(np.log(arr))
    if len(log_returns) == 0:
        return 0.0
    vol = float(np.std(log_returns) * sqrt(252) * 100)
    if not math.isfinite(vol):
        _log.debug('volatility NaN/Inf for %s — skipping', ticker)
        return 0.0
    pre_clamp = vol
    vol = max(_VOL_CLAMP_MIN, min(_VOL_CLAMP_MAX, vol))
    if pre_clamp != vol:
        _log.debug(
            'volatility clamped for %s: %.2f → %.2f', ticker, pre_clamp, vol,
        )
    return vol


def _classify(vol_pct: float, thresholds: dict[str, float]) -> str:
    crit = thresholds.get('critical', 55)
    high = thresholds.get('high', 40)
    mod = thresholds.get('moderate', 28)
    low = thresholds.get('low', 15)
    if vol_pct > crit:
        return 'critical'
    if vol_pct > high:
        return 'high'
    if vol_pct > mod:
        return 'moderate'
    if vol_pct > low:
        return 'low'
    return 'none'


def analyze(
    positions: list[dict], store: Any, settings: dict, risk_profile: dict,
) -> dict:
    refresh = settings.get('refresh_interval', '5 min')
    thresholds = risk_profile.get('volatility', {})

    def _cv(p: dict) -> float:
        shares = float(p.get('shares', 0.0) or 0.0)
        price = float(p.get('price', 0.0) or 0.0)
        return shares * price if shares > 0 and price > 0 else float(p.get('equity', 0.0) or 0.0)

    total_equity = sum(_cv(p) for p in positions) or 1.0

    ticker_results: dict[str, dict] = {}
    weighted_vol = 0.0
    most_volatile_ticker = ''
    most_volatile_vol = 0.0

    for pos in positions:
        t = pos['ticker']
        weight = _cv(pos) / total_equity
        try:
            hist = store.get_history(t, '1y', refresh) or []
            vol = _annualized_vol(hist, ticker=t)
        except Exception:
            vol = 0.0

        daily_std = vol / sqrt(252) / 100 if vol > 0 else 0.0
        sev = _classify(vol, thresholds)
        # Only flag if high severity AND weight > 15%
        flag = sev in ('high', 'critical') and weight > 0.15

        ticker_results[t] = {
            'value': vol,
            'severity': sev,
            'flag': flag,
            'weight': weight,
            'details': {
                'annualized_vol': vol,
                'daily_std': daily_std,
            },
        }
        weighted_vol += vol * weight

        if vol > most_volatile_vol:
            most_volatile_vol = vol
            most_volatile_ticker = t

    port_sev = _classify(weighted_vol, thresholds)

    return {
        'ticker_results': ticker_results,
        'portfolio_result': {
            'value': weighted_vol,
            'severity': port_sev,
            'flag': port_sev in ('high', 'critical'),
            'details': {
                'annualized_vol': weighted_vol,
                'most_volatile_ticker': most_volatile_ticker,
                'most_volatile_vol': most_volatile_vol,
            },
        },
    }
