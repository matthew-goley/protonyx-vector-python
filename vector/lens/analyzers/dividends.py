"""Upcoming ex-dividend dates and yield analyzer."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

_log = logging.getLogger(__name__)


def _parse_date(d: Any) -> date | None:
    if isinstance(d, date):
        return d
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str):
        for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S'):
            try:
                return datetime.strptime(d, fmt).date()
            except ValueError:
                continue
    return None


def _severity_from_days(days: int | None) -> str:
    if days is None:
        return 'none'
    if days <= 7:
        return 'high'
    if days <= 14:
        return 'moderate'
    if days <= 30:
        return 'low'
    return 'none'


def analyze(
    positions: list[dict], store: Any, settings: dict, risk_profile: dict,
) -> dict:
    today = date.today()
    one_year_ago = today - timedelta(days=365)
    def _cv(p: dict) -> float:
        cv = p.get('_current_value')
        if cv is not None:
            return float(cv)
        shares = float(p.get('shares', 0) or 0)
        price = float(p.get('price', 0) or 0)
        return shares * price if shares > 0 and price > 0 else float(p.get('equity', 0.0) or 0.0)

    total_equity = sum(_cv(p) for p in positions) or 1.0

    ticker_results: dict[str, dict] = {}
    nearest_ticker = ''
    nearest_days: int | None = None
    tickers_with_upcoming: list[str] = []
    weighted_yield = 0.0

    for pos in positions:
        t = pos['ticker']
        weight = _cv(pos) / total_equity
        current_price = pos.get('price', 0.0)

        next_ex_date: date | None = None
        days_until: int | None = None
        next_amount: float | None = None
        annual_div_total = 0.0

        try:
            divs = store.get_dividends(t) or []
            for d in divs:
                dd = _parse_date(d.get('date'))
                amt = d.get('amount', 0.0)
                if dd:
                    # Trailing 12-month dividends
                    if one_year_ago <= dd <= today and amt:
                        annual_div_total += amt
                    # Next upcoming
                    if dd >= today and next_ex_date is None:
                        next_ex_date = dd
                        days_until = (dd - today).days
                        next_amount = amt
        except Exception:
            pass

        annual_yield_pct = (
            (annual_div_total / current_price * 100)
            if current_price > 0 and annual_div_total > 0 else 0.0
        )
        weighted_yield += annual_yield_pct * weight

        sev = _severity_from_days(days_until)
        flag = sev != 'none'

        if flag:
            tickers_with_upcoming.append(t)

        if days_until is not None and (nearest_days is None or days_until < nearest_days):
            nearest_days = days_until
            nearest_ticker = t

        ticker_results[t] = {
            'value': float(days_until) if days_until is not None else 999.0,
            'severity': sev,
            'flag': flag,
            'weight': weight,
            'details': {
                'next_ex_date': next_ex_date.isoformat() if next_ex_date else None,
                'days_until': days_until,
                'amount': next_amount,
                'annual_yield_pct': annual_yield_pct,
            },
        }

    port_sev = _severity_from_days(nearest_days)

    return {
        'ticker_results': ticker_results,
        'portfolio_result': {
            'value': float(nearest_days) if nearest_days is not None else 999.0,
            'severity': port_sev,
            'flag': port_sev != 'none',
            'details': {
                'nearest_ticker': nearest_ticker,
                'nearest_days': nearest_days,
                'portfolio_yield_pct': weighted_yield,
                'tickers_with_upcoming': tickers_with_upcoming,
            },
        },
    }
