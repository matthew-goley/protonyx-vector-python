"""Upcoming earnings dates and EPS estimate analyzer."""

from __future__ import annotations

import logging
from datetime import date, datetime
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


def _determine_outlook(
    slope_annualized: float | None,
    vol_annualized: float | None,
) -> str:
    if slope_annualized is not None and vol_annualized is not None:
        if slope_annualized > 15 and vol_annualized <= 28:
            return 'beat_likely'
        if slope_annualized < -5 or vol_annualized > 40:
            return 'miss_risk'
    return 'neutral'


def analyze(
    positions: list[dict], store: Any, settings: dict, risk_profile: dict,
    *, prior_results: dict | None = None,
) -> dict:
    today = date.today()
    ticker_results: dict[str, dict] = {}
    def _cv(p: dict) -> float:
        cv = p.get('_current_value')
        if cv is not None:
            return float(cv)
        shares = float(p.get('shares', 0) or 0)
        price = float(p.get('price', 0) or 0)
        return shares * price if shares > 0 and price > 0 else float(p.get('equity', 0.0) or 0.0)

    total_equity = sum(_cv(p) for p in positions) or 1.0

    nearest_ticker = ''
    nearest_days: int | None = None
    nearest_eps: float | None = None
    tickers_with_upcoming: list[str] = []

    # Get slope/vol from prior results if available
    slope_data = (prior_results or {}).get('slope', {}).get('ticker_results', {})
    vol_data = (prior_results or {}).get('volatility', {}).get('ticker_results', {})

    for pos in positions:
        t = pos['ticker']
        weight = _cv(pos) / total_equity

        next_date: date | None = None
        days_until: int | None = None
        eps_estimate: float | None = None

        try:
            earnings = store.get_earnings(t) or []
            for e in earnings:
                ed = _parse_date(e.get('date'))
                if ed and ed >= today:
                    next_date = ed
                    days_until = (ed - today).days
                    eps_estimate = e.get('eps_estimate_avg')
                    break
        except Exception:
            pass

        # Determine outlook from prior slope/vol data
        slope_ann = None
        vol_ann = None
        if t in slope_data:
            slope_ann = slope_data[t].get('details', {}).get('annualized_pct')
        if t in vol_data:
            vol_ann = vol_data[t].get('details', {}).get('annualized_vol')
        outlook = _determine_outlook(slope_ann, vol_ann)

        sev = _severity_from_days(days_until)
        flag = sev != 'none'

        if flag:
            tickers_with_upcoming.append(t)

        if days_until is not None and (nearest_days is None or days_until < nearest_days):
            nearest_days = days_until
            nearest_ticker = t
            nearest_eps = eps_estimate

        ticker_results[t] = {
            'value': float(days_until) if days_until is not None else 999.0,
            'severity': sev,
            'flag': flag,
            'weight': weight,
            'details': {
                'next_earnings_date': next_date.isoformat() if next_date else None,
                'days_until': days_until,
                'eps_estimate': eps_estimate,
                'outlook': outlook,
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
                'nearest_eps': nearest_eps,
                'tickers_with_upcoming': tickers_with_upcoming,
            },
        },
    }
