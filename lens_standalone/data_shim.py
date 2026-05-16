"""Lightweight DataStore replacement backed directly by yfinance.

Implements only the methods the Lens engine reads from a Vector
``DataStore``. Results are cached in-memory for the lifetime of a single
process — no disk caching, every fresh run hits yfinance.

When ``lens_standalone`` is imported back into the Vector app, this
module is unused: the app supplies its own ``DataStore``.
"""

from __future__ import annotations

from typing import Any

import yfinance as yf


class DataShim:
    """yfinance-backed stand-in for ``vector.store.DataStore``."""

    def __init__(self) -> None:
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._history: dict[tuple[str, str], list[float]] = {}
        self._quotes: dict[str, dict[str, Any]] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._dividends: dict[str, list[dict[str, Any]]] = {}
        self._earnings: dict[str, list[dict[str, Any]]] = {}
        self._tickers: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _ticker(self, ticker: str) -> Any:
        if ticker not in self._tickers:
            self._tickers[ticker] = yf.Ticker(ticker)
        return self._tickers[ticker]

    def _ensure_quote_meta(self, ticker: str) -> None:
        """Populate cached quote + meta for a ticker (idempotent)."""
        if ticker in self._quotes and ticker in self._meta:
            return

        t = self._ticker(ticker)

        info: dict[str, Any] = {}
        try:
            info = t.info or {}
        except Exception:
            info = {}

        fi: dict[str, Any] = {}
        try:
            fi = {k: t.fast_info[k] for k in t.fast_info}
        except Exception:
            fi = {}

        price = (
            _sf(fi.get('lastPrice'))
            or _sf(fi.get('last_price'))
            or _sf(info.get('regularMarketPrice'))
            or _sf(info.get('currentPrice'))
        )
        if not price:
            try:
                hist = t.history(period='5d', interval='1d', auto_adjust=False)
                if not hist.empty:
                    price = float(hist['Close'].dropna().iloc[-1])
            except Exception:
                pass
        price = price or 0.0

        market_cap = _sf(fi.get('marketCap')) or _sf(info.get('marketCap')) or 0.0

        self._quotes[ticker] = {
            'price': price,
            'market_cap': market_cap,
            'prev_close': _sf(fi.get('regularMarketPreviousClose')) or _sf(info.get('previousClose')) or price,
            'beta': _sf(info.get('beta')),
            'pe_ratio': _sf(info.get('trailingPE')),
        }

        self._meta[ticker] = {
            'name': info.get('shortName') or info.get('longName') or ticker,
            'long_name': info.get('longName') or info.get('shortName') or ticker,
            'sector': _resolve_sector(info),
            'industry': info.get('industry'),
            'market_cap': market_cap,
        }

    # ------------------------------------------------------------------
    # Public interface — matches DataStore signatures Lens consumes
    # ------------------------------------------------------------------

    def get_snapshot(self, ticker: str, refresh_interval: str) -> dict[str, Any]:
        """Return ``{ticker, price, sector, name}`` for a single ticker."""
        if ticker in self._snapshots:
            return self._snapshots[ticker]

        self._ensure_quote_meta(ticker)
        quote = self._quotes.get(ticker, {})
        meta = self._meta.get(ticker, {})

        snap = {
            'ticker': ticker,
            'price': quote.get('price', 0.0),
            'sector': meta.get('sector', 'Unknown'),
            'name': meta.get('name', ticker),
        }
        self._snapshots[ticker] = snap
        return snap

    def get_history(self, ticker: str, period: str, refresh_interval: str) -> list[float]:
        """Return close-price list for the given period."""
        key = (ticker, period)
        if key in self._history:
            return self._history[key]

        try:
            frame = self._ticker(ticker).history(
                period=period, interval='1d', auto_adjust=False,
            )
            closes = (
                [float(v) for v in frame['Close'].dropna().tolist()]
                if not frame.empty else []
            )
        except Exception:
            closes = []

        self._history[key] = closes
        return closes

    def get_quote(self, ticker: str) -> dict[str, Any]:
        """Return cached quote dict ({} until ``get_snapshot`` has run)."""
        if ticker not in self._quotes:
            self._ensure_quote_meta(ticker)
        return self._quotes.get(ticker, {})

    def get_meta(self, ticker: str) -> dict[str, Any]:
        """Return cached meta dict (name, sector, industry, market_cap)."""
        if ticker not in self._meta:
            self._ensure_quote_meta(ticker)
        return self._meta.get(ticker, {})

    def get_dividends(self, ticker: str) -> list[dict[str, Any]]:
        """Return historical dividends as ``[{date, amount}, ...]``."""
        if ticker in self._dividends:
            return self._dividends[ticker]

        divs: list[dict[str, Any]] = []
        try:
            series = self._ticker(ticker).dividends
            if series is not None and not series.empty:
                divs = [
                    {'date': str(idx.date()), 'amount': float(val)}
                    for idx, val in zip(series.index, series.values, strict=False)
                ]
        except Exception:
            pass

        self._dividends[ticker] = divs
        return divs

    def get_earnings(self, ticker: str) -> list[dict[str, Any]]:
        """Return upcoming earnings as ``[{date, eps_estimate_avg, ...}, ...]``."""
        if ticker in self._earnings:
            return self._earnings[ticker]

        earnings: list[dict[str, Any]] = []
        try:
            cal = self._ticker(ticker).calendar or {}
            for d in cal.get('Earnings Date', []) or []:
                earnings.append({
                    'date': str(d),
                    'eps_estimate_avg': _sf(cal.get('Earnings Average')),
                    'eps_estimate_low': _sf(cal.get('Earnings Low')),
                    'eps_estimate_high': _sf(cal.get('Earnings High')),
                })
        except Exception:
            pass

        self._earnings[ticker] = earnings
        return earnings


# ---------------------------------------------------------------------------
# tiny helpers copied/adapted from vector.store
# ---------------------------------------------------------------------------

def _sf(value: Any) -> float | None:
    """Safe float — returns None if the value is empty or non-numeric."""
    if value is None or value == '':
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _resolve_sector(info: dict[str, Any]) -> str:
    """Return a usable sector string, or 'Unknown' if yfinance has nothing."""
    return (
        info.get('sector')
        or info.get('sectorDisp')
        or info.get('category')
        or 'Unknown'
    )
