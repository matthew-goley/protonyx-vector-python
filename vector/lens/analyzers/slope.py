"""Per-ticker and portfolio-level slope (direction) analyzer."""

from __future__ import annotations

import logging
import math
from typing import Any

from vector.analytics import linear_regression_slope_percent

_log = logging.getLogger(__name__)

_MIN_DATA_POINTS = 30
_SLOPE_CLAMP_MIN = -80.0
_SLOPE_CLAMP_MAX = 150.0


def _classify(annualized_pct: float, thresholds: dict[str, float]) -> str:
    crit = thresholds.get('critical', -25)
    high = thresholds.get('high', -15)
    mod = thresholds.get('moderate', -5)
    if annualized_pct <= crit:
        return 'critical'
    if annualized_pct <= high:
        return 'high'
    if annualized_pct <= mod:
        return 'moderate'
    if annualized_pct <= 5:
        return 'low'
    return 'none'


def analyze(
    positions: list[dict], store: Any, settings: dict, risk_profile: dict,
) -> dict:
    refresh = settings.get('refresh_interval', '5 min')
    thresholds = risk_profile.get('slope', {})

    def _cv(p: dict) -> float:
        shares = float(p.get('shares', 0.0) or 0.0)
        price = float(p.get('price', 0.0) or 0.0)
        return shares * price if shares > 0 and price > 0 else float(p.get('equity', 0.0) or 0.0)

    total_equity = sum(_cv(p) for p in positions) or 1.0

    ticker_results: dict[str, dict] = {}
    weighted_slope = 0.0

    for pos in positions:
        t = pos['ticker']
        weight = _cv(pos) / total_equity
        try:
            hist = store.get_history(t, '6mo', refresh) or []
            clean = [
                p for p in hist
                if p is not None and not math.isnan(p) and p > 0
            ]
            if len(clean) < _MIN_DATA_POINTS:
                raw_slope = 0.0
                annualized = 0.0
                insufficient_data = True
                if hist and len(clean) < _MIN_DATA_POINTS:
                    _log.debug(
                        'slope skipped for %s: bad_data (have=%d, need=%d)',
                        t, len(clean), _MIN_DATA_POINTS,
                    )
            else:
                raw_slope = linear_regression_slope_percent(clean)
                annualized = raw_slope * 252
                insufficient_data = False
                # Sanity check against actual peak-to-trough movement. 6mo
                # window ≈ annualize by ×2. If regression disagrees by >30
                # percentage points, fall back to the actual annualized return.
                first_price = clean[0]
                last_price = clean[-1]
                if first_price > 0:
                    actual_total_pct = (last_price - first_price) / first_price * 100
                    actual_annualized = actual_total_pct * 2
                    if abs(annualized - actual_annualized) > 30:
                        _log.debug(
                            'slope disagrees with actual for %s: regr=%.1f actual=%.1f',
                            t, annualized, actual_annualized,
                        )
                        annualized = actual_annualized
                        raw_slope = actual_annualized / 252
        except Exception:
            raw_slope = 0.0
            annualized = 0.0
            insufficient_data = True

        # Guard against NaN/Inf and clamp extreme values
        if not math.isfinite(annualized):
            _log.debug('slope NaN/Inf for %s — skipping', t)
            annualized = 0.0
            raw_slope = 0.0
            insufficient_data = True
        else:
            pre_clamp = annualized
            annualized = max(_SLOPE_CLAMP_MIN, min(_SLOPE_CLAMP_MAX, annualized))
            if pre_clamp != annualized:
                _log.debug(
                    'slope clamped for %s: %.2f → %.2f', t, pre_clamp, annualized,
                )

        if insufficient_data:
            sev = 'none'
        else:
            sev = _classify(annualized, thresholds)
        direction = 'up' if annualized > 5 else ('down' if annualized < -5 else 'flat')

        ticker_results[t] = {
            'value': annualized,
            'severity': sev,
            'flag': sev in ('moderate', 'high', 'critical') and not insufficient_data,
            'weight': weight,
            'details': {
                'direction': direction,
                'annualized_pct': annualized,
            },
        }
        weighted_slope += raw_slope * weight

    # Portfolio-level
    port_annual = weighted_slope * 252
    if not math.isfinite(port_annual):
        port_annual = 0.0
    port_annual = max(_SLOPE_CLAMP_MIN, min(_SLOPE_CLAMP_MAX, port_annual))
    port_sev = _classify(port_annual, thresholds)

    up_tickers = [t for t, r in ticker_results.items() if r['details']['direction'] == 'up']
    down_tickers = [t for t, r in ticker_results.items() if r['details']['direction'] == 'down']
    flat_tickers = [t for t, r in ticker_results.items() if r['details']['direction'] == 'flat']
    total = len(ticker_results)

    if total > 0 and len(down_tickers) / total > 0.7:
        state = 'broad_decline'
    elif total > 0 and len(up_tickers) / total > 0.7:
        state = 'broad_uptrend'
    else:
        state = 'mixed'

    return {
        'ticker_results': ticker_results,
        'portfolio_result': {
            'value': port_annual,
            'severity': port_sev,
            'flag': port_sev in ('moderate', 'high', 'critical'),
            'details': {
                'annualized_pct': port_annual,
                'state': state,
                'up_tickers': up_tickers,
                'down_tickers': down_tickers,
                'flat_tickers': flat_tickers,
                'up_count': len(up_tickers),
                'down_count': len(down_tickers),
                'total_count': total,
            },
        },
    }
