"""Sentence 2 — timing/catalyst composer (earnings + dividends)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from ._templates import load_templates as _load_templates

_log = logging.getLogger(__name__)


def _pick(templates: list[str], hash_key: str) -> str:
    if not templates:
        return ''
    h = int(hashlib.sha256(hash_key.encode()).hexdigest(), 16)
    return templates[h % len(templates)]


def compose(pool_results: dict[str, Any]) -> str:
    """
    Read earnings and dividends analyzer results, pick the most imminent
    catalyst, and return one sentence from sentences.json.
    """
    templates = _load_templates().get('sentence2', {})
    earn_res = pool_results.get('earnings', {})
    div_res = pool_results.get('dividends', {})

    earn_tickers = earn_res.get('ticker_results', {})
    div_tickers = div_res.get('ticker_results', {})
    earn_port = earn_res.get('portfolio_result', {}).get('details', {})
    div_port = div_res.get('portfolio_result', {}).get('details', {})

    sorted_tickers = sorted(earn_tickers.keys())
    hash_base = '|'.join(sorted_tickers) + '|s2'

    e_ticker = earn_port.get('nearest_ticker', '')
    e_days = earn_port.get('nearest_days')
    e_eps = earn_port.get('nearest_eps')

    d_ticker = div_port.get('nearest_ticker', '')
    d_days = div_port.get('nearest_days')

    yield_pct = div_port.get('portfolio_yield_pct', 0.0)

    d_amount = None
    if d_ticker and d_ticker in div_tickers:
        d_amount = div_tickers[d_ticker].get('details', {}).get('amount')
        d_yield = div_tickers[d_ticker].get('details', {}).get('annual_yield_pct', 0)
    else:
        d_yield = yield_pct

    if (e_days is not None and e_days <= 14 and
            d_days is not None and d_days <= 14):
        tmpls = templates.get('combined_catalyst', {}).get('earnings_and_dividend', [])
        tmpl = _pick(tmpls, hash_base)
        try:
            return tmpl.format(
                e_ticker=e_ticker, e_days=e_days, d_ticker=d_ticker, d_days=d_days,
            )
        except (KeyError, ValueError):
            return tmpl

    if e_days is not None and e_days <= 30 and e_ticker:
        outlook = 'neutral'
        if e_ticker in earn_tickers:
            outlook = earn_tickers[e_ticker].get('details', {}).get('outlook', 'neutral')

        earn_tmpls = templates.get('earnings', {}).get('earnings_imminent', {})
        tmpls = earn_tmpls.get(outlook, earn_tmpls.get('neutral', []))
        tmpl = _pick(tmpls, hash_base)
        try:
            return tmpl.format(
                e_ticker=e_ticker, e_days=e_days, eps=e_eps or 0,
                ticker=e_ticker, days=e_days,
            )
        except (KeyError, ValueError):
            return tmpl

    if d_days is not None and d_days <= 30 and d_ticker:
        tmpls = templates.get('dividends', {}).get('dividend_upcoming', [])
        tmpl = _pick(tmpls, hash_base)
        try:
            return tmpl.format(
                d_ticker=d_ticker, d_days=d_days, yield_pct=d_yield,
                ticker=d_ticker, days=d_days,
            )
        except (KeyError, ValueError):
            return tmpl

    if e_days is not None:
        tmpls = templates.get('earnings', {}).get('earnings_distant', [])
        tmpl = _pick(tmpls, hash_base)
        return tmpl

    tmpls = templates.get('dividends', {}).get('no_dividends', [])
    if tmpls:
        tmpl = _pick(tmpls, hash_base)
        try:
            return tmpl.format(yield_pct=yield_pct)
        except (KeyError, ValueError):
            return tmpl

    tmpls = templates.get('earnings', {}).get('no_earnings_data', [])
    tmpl = _pick(tmpls, hash_base)
    return tmpl or 'No imminent catalysts detected across current holdings.'
