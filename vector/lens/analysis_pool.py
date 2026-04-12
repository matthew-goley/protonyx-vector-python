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

    # Build THE single source of truth for weights and values.
    summary = _build_positions_summary(positions, store)
    total_equity = summary['total_equity'] or 1.0

    # Enrich each position dict with its canonical current market value so
    # downstream analyzers can read it directly without recomputing.
    for p in positions:
        cv = summary['ticker_current_values'].get(p['ticker'], 0.0)
        p['_current_value'] = cv
        cp = summary['ticker_current_prices'].get(p['ticker'])
        if cp and not p.get('price'):
            p['price'] = cp

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
    """THE single source of truth for portfolio weights and values.

    Every weight calculation in the lens package must come from here.
    Uses current market value (shares × current price) throughout.
    """
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
        print(
            f'[lens DEBUG] WARNING: ticker_weights sum to {weight_sum:.4f}, '
            f'should be ~1.0'
        )
        print(
            f"[lens DEBUG] Positions: {[(p['ticker'], p.get('shares')) for p in positions]}"
        )
        print(f'[lens DEBUG] Current prices: {ticker_current_prices}')
        print(f'[lens DEBUG] Current values: {ticker_current_values}')
        print(f'[lens DEBUG] Total equity: {total_equity}')
        print(f'[lens DEBUG] Weights: {ticker_weights}')

    return summary
