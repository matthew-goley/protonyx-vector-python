"""Subset of vector.analytics — only the math functions Lens consumes."""

from __future__ import annotations

import numpy as np


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
    """Portfolio daily return series aligned to the shortest available history."""
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
