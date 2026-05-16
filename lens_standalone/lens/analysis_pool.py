"""Run all analyzers and cache combined results."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .risk_profile import load_risk_profile

_log = logging.getLogger(__name__)


def _safe_analyze(name: str, fn, *args, **kwargs) -> dict:
    """Run an analyzer, returning a neutral result on failure."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        _log.debug('Analyzer %s failed', name, exc_info=True)
        return {
            'ticker_results': {},
            'portfolio_result': {
                'value': 0.0,
                'severity': 'none',
                'flag': False,
                'details': {},
            },
        }


def run_analysis(
    positions: list[dict[str, Any]],
    store: Any,
    settings: dict[str, Any],
    progress_cb: Callable[[str, float], None] | None = None,
) -> dict[str, Any]:
    """
    Run all analyzers and return the combined results dict.

    ``progress_cb`` (optional) is invoked as ``progress_cb(analyzer_name,
    elapsed_seconds)`` after each analyzer completes — used by the CLI
    runner to display per-analyzer timing. The Vector app calls this
    without ``progress_cb`` so behavior is unchanged.
    """
    import time

    from .analyzers import (
        beta,
        concentration,
        dividends,
        earnings,
        index_fund,
        performance,
        slope,
        volatility,
    )

    risk_profile = load_risk_profile(settings)

    summary = _build_positions_summary(positions, store)
    total_equity = summary['total_equity'] or 1.0

    for p in positions:
        cv = summary['ticker_current_values'].get(p['ticker'], 0.0)
        p['_current_value'] = cv
        cp = summary['ticker_current_prices'].get(p['ticker'])
        if cp and not p.get('price'):
            p['price'] = cp

    def _timed(name: str, fn, *args, **kwargs):
        t0 = time.perf_counter()
        result = _safe_analyze(name, fn, *args, **kwargs)
        if progress_cb is not None:
            progress_cb(name, time.perf_counter() - t0)
        return result

    slope_res = _timed(
        'slope', slope.analyze, positions, store, settings, risk_profile,
    )
    vol_res = _timed(
        'volatility', volatility.analyze, positions, store, settings, risk_profile,
    )

    prior = {'slope': slope_res, 'volatility': vol_res}
    earnings_res = _timed(
        'earnings', earnings.analyze, positions, store, settings, risk_profile,
        prior_results=prior,
    )

    conc_res = _timed(
        'concentration', concentration.analyze, positions, store, settings, risk_profile,
    )
    div_res = _timed(
        'dividends', dividends.analyze, positions, store, settings, risk_profile,
    )
    beta_res = _timed(
        'beta', beta.analyze, positions, store, settings, risk_profile,
    )
    perf_res = _timed(
        'performance', performance.analyze, positions, store, settings, risk_profile,
    )
    idx_res = _timed(
        'index_fund', index_fund.analyze, positions, store, settings, risk_profile,
    )

    idx_tickers = idx_res.get('ticker_results', {})
    conc_tickers = conc_res.get('ticker_results', {})
    for t, idx_data in idx_tickers.items():
        if idx_data.get('flag') and t in conc_tickers:
            conc_tickers[t]['flag'] = False
            conc_tickers[t]['severity'] = 'none'

    return {
        'slope': slope_res,
        'volatility': vol_res,
        'concentration': conc_res,
        'earnings': earnings_res,
        'dividends': div_res,
        'beta': beta_res,
        'performance': perf_res,
        'index_fund': idx_res,
        '_risk_profile': risk_profile,
        '_store': store,
        '_positions_summary': summary,
    }


def _build_positions_summary(
    positions: list[dict[str, Any]], store: Any,
) -> dict[str, Any]:
    """THE single source of truth for portfolio weights and values."""
    if not positions:
        return {
            'total_equity': 0.0,
            'ticker_weights': {},
            'ticker_current_prices': {},
            'ticker_current_values': {},
            'sector_weights': {},
        }

    ticker_current_prices: dict[str, float] = {}
    for p in positions:
        t = p['ticker']
        price = 0.0
        try:
            snap = store.get_snapshot(t, '5 min') if store else None
            if snap and snap.get('price'):
                price = float(snap['price'])
        except Exception:
            price = 0.0
        if price <= 0:
            price = float(p.get('price', 0) or 0)
        ticker_current_prices[t] = price

    ticker_current_values: dict[str, float] = {}
    for p in positions:
        t = p['ticker']
        shares = float(p.get('shares', 0) or 0)
        ticker_current_values[t] = shares * ticker_current_prices.get(t, 0.0)

    total_equity = sum(ticker_current_values.values())

    if total_equity > 0:
        ticker_weights = {
            t: v / total_equity for t, v in ticker_current_values.items()
        }
    else:
        ticker_weights = {t: 0.0 for t in ticker_current_values}

    sector_weights: dict[str, float] = {}
    for p in positions:
        sector = p.get('sector') or 'Unknown'
        sector_weights[sector] = sector_weights.get(sector, 0.0) + ticker_weights.get(p['ticker'], 0.0)

    summary = {
        'total_equity': total_equity,
        'ticker_weights': ticker_weights,
        'ticker_current_prices': ticker_current_prices,
        'ticker_current_values': ticker_current_values,
        'sector_weights': sector_weights,
    }

    weight_sum = sum(ticker_weights.values())
    if total_equity > 0 and abs(weight_sum - 1.0) > 0.01:
        _log.debug(
            'ticker_weights sum to %.4f (should be ~1.0); positions=%s',
            weight_sum, [(p['ticker'], p.get('shares')) for p in positions],
        )

    return summary
