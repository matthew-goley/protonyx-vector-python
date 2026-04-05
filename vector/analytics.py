from __future__ import annotations

from math import sqrt
from typing import Any

import numpy as np


DIRECTION_STATES = [
    ('Strong', '#2dd4bf'),
    ('Steady', '#54BFFF'),
    ('Neutral', '#c7cedb'),
    ('Depreciating', '#FF6B2B'),
    ('Weak', '#ff5d5d'),
]


def linear_regression_slope_percent(prices: list[float]) -> float:
    if len(prices) < 2 or prices[0] == 0:
        return 0.0
    x = np.arange(len(prices), dtype=float)
    y = np.array(prices, dtype=float)
    slope, _intercept = np.polyfit(x, y, 1)
    return float((slope / prices[0]) * 100)



def portfolio_daily_returns(
    positions: list[dict],
    closes_map: dict[str, list[float]],
) -> list[float]:
    """
    Compute portfolio daily return series.
    closes_map: { ticker: [close0, close1, ...] }
    Returns list of daily returns aligned to the shortest series.
    """
    # Only include positions that have close data
    valid = [(p, closes_map[p['ticker']])
             for p in positions if p['ticker'] in closes_map and closes_map[p['ticker']]]
    if not valid:
        return []
    n = min(len(c) for _, c in valid)
    if n < 3:
        return []
    values = [
        sum(p.get('shares', 0) * closes[i] for p, closes in valid)
        for i in range(n)
    ]
    arr = np.array(values, dtype=float)
    return (np.diff(arr) / arr[:-1]).tolist()


def sharpe_ratio(daily_returns: list[float], risk_free_annual: float = 0.045) -> float:
    """Annualized Sharpe ratio given daily return series and annual risk-free rate."""
    if len(daily_returns) < 3:
        return 0.0
    arr = np.array(daily_returns, dtype=float)
    rf_daily = risk_free_annual / 252
    excess = arr - rf_daily
    std = float(np.std(arr))
    if std < 1e-9:
        return 0.0
    return float(np.mean(excess) / std * sqrt(252))


def portfolio_beta(portfolio_returns: list[float], benchmark_returns: list[float]) -> float:
    """Beta of portfolio vs benchmark."""
    n = min(len(portfolio_returns), len(benchmark_returns))
    if n < 3:
        return 1.0
    p = np.array(portfolio_returns[:n], dtype=float)
    b = np.array(benchmark_returns[:n], dtype=float)
    var_b = float(np.var(b))
    if var_b < 1e-12:
        return 1.0
    return float(np.cov(p, b)[0][1] / var_b)


def annualized_volatility(prices: list[float]) -> float:
    if len(prices) < 3:
        return 0.0
    series = np.array(prices, dtype=float)
    returns = np.diff(series) / series[:-1]
    if len(returns) == 0:
        return 0.0
    return float(np.std(returns) * sqrt(252))



def score_volatility(raw_volatility: float) -> int:
    return max(1, min(100, int(raw_volatility * 100)))



def classify_direction(value: float, thresholds: dict[str, float]) -> tuple[str, str, float]:
    if value >= thresholds['strong']:
        label, color = DIRECTION_STATES[0]
    elif value >= thresholds['steady']:
        label, color = DIRECTION_STATES[1]
    elif thresholds['neutral_low'] <= value <= thresholds['neutral_high']:
        label, color = DIRECTION_STATES[2]
    elif value <= thresholds['depreciating']:
        label, color = DIRECTION_STATES[4]
    else:
        label, color = DIRECTION_STATES[3]
    _sign = 1.0 if value >= 0 else -1.0
    arrow_angle = _sign * min(80.0, sqrt(abs(value)) * 300)
    return label, color, arrow_angle



def classify_volatility(score: int, low_cutoff: int, high_cutoff: int) -> tuple[str, str]:
    if score < low_cutoff:
        return 'Low Volatility', '#2dd4bf'
    if score <= high_cutoff:
        return 'Moderate', '#38bdf8'
    return 'High Risk', '#ff5d5d'



def compute_portfolio_analytics(
    positions: list[dict[str, Any]],
    history_map: dict[str, dict[str, list[float]]],
    thresholds: dict[str, float],
    vol_settings: dict[str, Any],
) -> dict[str, Any]:
    total_equity = sum(position.get('equity', 0.0) for position in positions)
    weighted_slope = 0.0
    weighted_volatility = 0.0
    sector_map: dict[str, float] = {}
    sparkline_map: dict[str, list[float]] = {}
    tickers_missing_history: list[str] = []
    tickers_with_data = 0

    for position in positions:
        ticker = position['ticker']
        equity = position.get('equity', 0.0)
        history = history_map.get(ticker, {})
        six_month_prices = history.get('6mo', [])
        month_prices = history.get('1mo', [])
        slope = linear_regression_slope_percent(six_month_prices)
        volatility = annualized_volatility(history.get(vol_settings['lookback_period'], six_month_prices))

        # Track data quality per ticker
        has_sufficient_data = len(six_month_prices) >= 5
        if not has_sufficient_data:
            tickers_missing_history.append(ticker)
        else:
            tickers_with_data += 1

        if total_equity:
            weight = equity / total_equity
            weighted_slope += slope * weight
            weighted_volatility += volatility * weight
        sector = position.get('sector') or 'Unknown'
        sector_map[sector] = sector_map.get(sector, 0.0) + equity
        sparkline_map[ticker] = month_prices
        position['slope_percent'] = slope
        position['volatility'] = volatility

    # Detect unreliable data conditions
    all_slopes_zero = all(abs(p.get('slope_percent', 0.0)) < 1e-6 for p in positions)
    all_vol_zero = all(abs(p.get('volatility', 0.0)) < 1e-6 for p in positions)
    many_missing = len(tickers_missing_history) > 0
    data_unreliable = (all_slopes_zero and len(positions) > 0) or (all_vol_zero and len(positions) > 0) or many_missing

    direction_label, direction_color, arrow_angle = classify_direction(weighted_slope, thresholds)
    volatility_score = score_volatility(weighted_volatility)
    volatility_label, volatility_color = classify_volatility(
        volatility_score,
        int(vol_settings['low_cutoff']),
        int(vol_settings['high_cutoff']),
    )

    allocation = []
    for sector, value in sorted(sector_map.items(), key=lambda item: item[1], reverse=True):
        percent = (value / total_equity * 100) if total_equity else 0.0
        allocation.append({'sector': sector, 'equity': value, 'percent': percent})

    # Compute portfolio equity from ~5 trading days ago
    equity_5d_ago = 0.0
    equity_5d_valid = True
    for position in positions:
        ticker = position['ticker']
        month_prices = sparkline_map.get(ticker, [])
        shares = position.get('shares', 0.0)
        if len(month_prices) >= 6:
            equity_5d_ago += shares * month_prices[-6]
        elif len(month_prices) >= 2:
            equity_5d_ago += shares * month_prices[0]
        else:
            equity_5d_valid = False
            equity_5d_ago += position.get('equity', 0.0)

    equity_5d_change = total_equity - equity_5d_ago if equity_5d_valid else 0.0
    equity_5d_pct = (equity_5d_change / equity_5d_ago * 100) if equity_5d_ago and equity_5d_valid else 0.0

    quality_info = {
        'data_unreliable': data_unreliable,
        'tickers_missing_history': tickers_missing_history,
        'all_slopes_zero': all_slopes_zero,
        'all_vol_zero': all_vol_zero,
    }

    return {
        'portfolio_value': total_equity,
        'weighted_slope': weighted_slope,
        'direction_label': direction_label,
        'direction_color': direction_color,
        'arrow_angle': arrow_angle,
        'allocation': allocation,
        'volatility_score': volatility_score,
        'volatility_label': volatility_label,
        'volatility_color': volatility_color,
        'sparklines': sparkline_map,
        'data_quality': quality_info,
        'equity_5d_change': equity_5d_change,
        'equity_5d_pct': equity_5d_pct,
        'equity_5d_valid': equity_5d_valid,
        'direction_insight': _direction_insight(direction_label, weighted_slope, positions, quality_info),
        'volatility_insight': _volatility_insight(volatility_label, volatility_score, positions, quality_info),
        'diversification_insight': _diversification_insight(allocation),
    }


# ---------------------------------------------------------------------------
# Sector -> well-known tickers for suggestion engine
# ---------------------------------------------------------------------------
_SECTOR_TICKERS: dict[str, list[str]] = {
    'Technology': ['AAPL', 'MSFT', 'NVDA', 'GOOG', 'META'],
    'Healthcare': ['JNJ', 'UNH', 'PFE', 'ABT', 'TMO'],
    'Financial Services': ['JPM', 'BRK-B', 'V', 'MA', 'BAC'],
    'Financials': ['JPM', 'BRK-B', 'V', 'MA', 'BAC'],
    'Consumer Cyclical': ['AMZN', 'TSLA', 'HD', 'NKE', 'MCD'],
    'Consumer Defensive': ['PG', 'KO', 'PEP', 'WMT', 'COST'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG'],
    'Industrials': ['CAT', 'UNP', 'HON', 'UPS', 'DE'],
    'Communication Services': ['GOOG', 'META', 'DIS', 'NFLX', 'TMUS'],
    'Utilities': ['NEE', 'DUK', 'SO', 'D', 'AEP'],
    'Real Estate': ['AMT', 'PLD', 'CCI', 'EQIX', 'SPG'],
    'Basic Materials': ['LIN', 'APD', 'SHW', 'ECL', 'NEM'],
    'ETF': ['SPY', 'QQQ', 'VTI', 'IWM', 'VEA'],
}

_UNDERREPRESENTED_SECTORS = [
    'Healthcare', 'Financial Services', 'Consumer Defensive',
    'Energy', 'Industrials', 'Utilities', 'Real Estate',
    'Technology', 'Consumer Cyclical', 'Basic Materials',
    'Communication Services', 'ETF',
]


def _direction_insight(label: str, slope: float, positions: list[dict[str, Any]], quality: dict[str, Any]) -> str:
    """Generate a rich-text insight about portfolio direction."""
    if quality.get('all_slopes_zero') or quality.get('data_unreliable'):
        missing = quality.get('tickers_missing_history', [])
        if missing:
            tickers = ', '.join(f'<b>{t}</b>' for t in missing[:3])
            return (
                f'<span style="color: #f3b84b;">⚠ Unable to calculate direction accurately.</span> '
                f'Price history could not be loaded for {tickers}. '
                'This is usually caused by a <b>slow or unstable connection</b>. Try refreshing when your network improves.'
            )
        return (
            '<span style="color: #f3b84b;">⚠ Direction data looks unreliable.</span> '
            'All positions are showing <b>0.0% slope</b>, which typically means price history '
            'failed to load. Check your internet connection and try refreshing.'
        )

    sorted_pos = sorted(positions, key=lambda p: p.get('slope_percent', 0.0))
    worst = sorted_pos[0] if sorted_pos else None
    best = sorted_pos[-1] if sorted_pos else None

    if label == 'Strong':
        line1 = f'Your portfolio is <b>trending strongly upward</b> at <b>{slope:+.2f}%</b> slope.'
        if best:
            line2 = f"<b>{best['ticker']}</b> is leading your gains — momentum looks healthy across your holdings."
        else:
            line2 = 'Momentum looks <b>healthy</b> across your holdings.'
        return f'{line1} {line2}'
    elif label == 'Steady':
        line1 = f'Your portfolio is showing <b>steady growth</b> at <b>{slope:+.2f}%</b> slope.'
        line2 = 'This is a <b>positive signal</b> — your holdings are appreciating at a sustainable pace.'
        return f'{line1} {line2}'
    elif label == 'Neutral':
        line1 = 'Your portfolio is <b>holding flat</b> with no clear directional trend.'
        line2 = 'This could be a <b>consolidation period</b>. Keep an eye on upcoming earnings or sector shifts.'
        return f'{line1} {line2}'
    elif label == 'Depreciating':
        line1 = f'Your portfolio is <b>trending downward</b> at <b>{slope:+.2f}%</b> slope.'
        if worst:
            line2 = f"<b>{worst['ticker']}</b> is dragging performance. Consider <b>reviewing your exposure</b> or setting a stop-loss level."
        else:
            line2 = 'Consider <b>reviewing underperforming positions</b>.'
        return f'{line1} {line2}'
    else:  # Weak
        line1 = f'Your portfolio is under <b>significant downward pressure</b> at <b>{slope:+.2f}%</b> slope.'
        if worst:
            line2 = f"<b>{worst['ticker']}</b> is your weakest position. A <b>defensive rebalance</b> may help limit further losses."
        else:
            line2 = 'A <b>defensive rebalance</b> may help limit further losses.'
        return f'{line1} {line2}'


def _volatility_insight(label: str, score: int, positions: list[dict[str, Any]], quality: dict[str, Any]) -> str:
    """Generate a rich-text insight about portfolio volatility."""
    if quality.get('all_vol_zero') or quality.get('data_unreliable'):
        missing = quality.get('tickers_missing_history', [])
        if missing:
            tickers = ', '.join(f'<b>{t}</b>' for t in missing[:3])
            return (
                f'<span style="color: #f3b84b;">⚠ Volatility data is incomplete.</span> '
                f'Could not load enough price history for {tickers}. '
                'A stronger connection is needed to calculate risk accurately.'
            )
        return (
            '<span style="color: #f3b84b;">⚠ Volatility readings appear unreliable.</span> '
            'All positions returned <b>zero volatility</b>, which usually means the data did not load properly. '
            'Try refreshing once your connection stabilizes.'
        )

    most_volatile = max(positions, key=lambda p: p.get('volatility', 0.0)) if positions else None

    if label == 'Low Volatility':
        line1 = f'Your investments are <b>steady</b> with a volatility score of <b>{score}</b>.'
        line2 = 'Price swings have been <b>minimal</b> — this is a sign of a well-anchored portfolio.'
        return f'{line1} {line2}'
    elif label == 'Moderate':
        line1 = f'Your portfolio shows <b>moderate volatility</b> at a score of <b>{score}</b>.'
        if most_volatile:
            line2 = f"<b>{most_volatile['ticker']}</b> is your most volatile holding. This level of movement is typical but <b>worth monitoring</b>."
        else:
            line2 = 'This level of movement is typical but <b>worth monitoring</b>.'
        return f'{line1} {line2}'
    else:  # High Risk
        line1 = f'Your investments are <b>highly volatile</b> with a score of <b>{score}</b>.'
        if most_volatile:
            line2 = f"<b>{most_volatile['ticker']}</b> is contributing the most risk. Consider <b>hedging or reducing exposure</b> to stabilize returns."
        else:
            line2 = 'Consider <b>hedging or reducing exposure</b> to stabilize returns.'
        return f'{line1} {line2}'


def _diversification_insight(allocation: list[dict[str, Any]]) -> str:
    """Generate a rich-text insight about sector diversification."""
    if not allocation:
        return 'Add positions to see diversification insights.'

    top = allocation[0]
    top_pct = float(top['percent'])
    top_sector = str(top['sector'])
    held_sectors = {str(a['sector']) for a in allocation}

    # Find a sector the user is NOT in for a suggestion
    missing_sector = None
    for s in _UNDERREPRESENTED_SECTORS:
        if s not in held_sectors:
            missing_sector = s
            break

    if top_pct >= 70:
        line1 = f"<b>{top_pct:.0f}%</b> of your portfolio is concentrated in <b>{top_sector}</b>."
        line2 = 'That is a <b>heavy concentration</b> in one sector.'
    elif top_pct >= 45:
        line1 = f"<b>{top_pct:.0f}%</b> of your investments are in <b>{top_sector}</b>."
        line2 = 'Your portfolio leans toward this sector — some <b>diversification could reduce risk</b>.'
    else:
        line1 = f'Your largest sector exposure is <b>{top_sector}</b> at <b>{top_pct:.0f}%</b>.'
        line2 = 'Your allocation is <b>relatively well spread</b> across sectors.'

    if missing_sector and missing_sector in _SECTOR_TICKERS:
        suggestions = _SECTOR_TICKERS[missing_sector][:3]
        ticker_str = ', '.join(f'<b>{t}</b>' for t in suggestions)
        line3 = f'Consider adding <b>{missing_sector}</b> exposure through tickers like {ticker_str}.'
    elif len(allocation) == 1:
        line3 = 'Adding positions in <b>different sectors</b> would improve your risk profile.'
    else:
        line3 = ''

    return f'{line1} {line2} {line3}'.strip()
