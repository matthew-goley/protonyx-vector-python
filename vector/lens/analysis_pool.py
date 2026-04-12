"""Run all analyzers and cache combined results."""

from __future__ import annotations

import logging
from typing import Any

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
) -> dict[str, Any]:
    """
    Run all analyzers and return the combined results dict.

    Execution order: slope and volatility run first so earnings can use
    their results for the ``outlook`` field.  After all analyzers finish,
    index-fund suppression is applied to concentration results.
    """
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
    total_equity = sum(p.get('equity', 0.0) for p in positions) or 1.0

    # Phase 1: slope and volatility (needed by earnings for outlook)
    slope_res = _safe_analyze(
        'slope', slope.analyze, positions, store, settings, risk_profile,
    )
    vol_res = _safe_analyze(
        'volatility', volatility.analyze, positions, store, settings, risk_profile,
    )

    # Phase 2: earnings (depends on slope/vol for outlook)
    prior = {'slope': slope_res, 'volatility': vol_res}
    earnings_res = _safe_analyze(
        'earnings', earnings.analyze, positions, store, settings, risk_profile,
        prior_results=prior,
    )

    # Phase 3: remaining analyzers (independent)
    conc_res = _safe_analyze(
        'concentration', concentration.analyze, positions, store, settings, risk_profile,
    )
    div_res = _safe_analyze(
        'dividends', dividends.analyze, positions, store, settings, risk_profile,
    )
    beta_res = _safe_analyze(
        'beta', beta.analyze, positions, store, settings, risk_profile,
    )
    perf_res = _safe_analyze(
        'performance', performance.analyze, positions, store, settings, risk_profile,
    )
    idx_res = _safe_analyze(
        'index_fund', index_fund.analyze, positions, store, settings, risk_profile,
    )

    # Post-process: suppress concentration flags for index ETFs
    idx_tickers = idx_res.get('ticker_results', {})
    conc_tickers = conc_res.get('ticker_results', {})
    for t, idx_data in idx_tickers.items():
        if idx_data.get('flag') and t in conc_tickers:
            conc_tickers[t]['flag'] = False
            conc_tickers[t]['severity'] = 'none'

    # Build convenience summary
    ticker_weights: dict[str, float] = {}
    ticker_prices: dict[str, float] = {}
    sector_weights: dict[str, float] = {}
    for pos in positions:
        t = pos['ticker']
        eq = pos.get('equity', 0.0)
        ticker_weights[t] = eq / total_equity
        ticker_prices[t] = pos.get('price', 0.0)
        sector = pos.get('sector') or 'Unknown'
        sector_weights[sector] = sector_weights.get(sector, 0.0) + eq / total_equity

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
        '_positions_summary': {
            'total_equity': total_equity,
            'ticker_weights': ticker_weights,
            'ticker_current_prices': ticker_prices,
            'sector_weights': sector_weights,
        },
    }
