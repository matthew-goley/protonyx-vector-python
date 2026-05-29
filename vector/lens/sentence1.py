"""Sentence 1 — portfolio state composer (slope + volatility)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from vector.lens._templates import load_templates as _load_templates

_log = logging.getLogger(__name__)


def _pick(templates: list[str], hash_key: str) -> str:
    """Deterministic template selection based on hash."""
    if not templates:
        return ''
    h = int(hashlib.sha256(hash_key.encode()).hexdigest(), 16)
    return templates[h % len(templates)]


def compose(pool_results: dict[str, Any]) -> str:
    """
    Read slope and volatility analyzer results, pick the most relevant
    state observation, and return one sentence from sentences.json.
    """
    templates = _load_templates().get('sentence1', {})
    slope_res = pool_results.get('slope', {})
    vol_res = pool_results.get('volatility', {})
    perf_res = pool_results.get('performance', {})

    slope_tickers = slope_res.get('ticker_results', {})
    vol_tickers = vol_res.get('ticker_results', {})
    perf_tickers = perf_res.get('ticker_results', {})
    port_slope = slope_res.get('portfolio_result', {})
    port_vol = vol_res.get('portfolio_result', {})

    def _unrealized_pct(t: str) -> float:
        return perf_tickers.get(t, {}).get(
            'details', {},
        ).get('unrealized_return_pct', 0.0)

    slope_val = port_slope.get('details', {}).get('annualized_pct', 0)
    vol_val = port_vol.get('details', {}).get('annualized_vol', 0)

    # Build hash key for deterministic selection
    sorted_tickers = sorted(slope_tickers.keys())
    hash_base = '|'.join(
        f"{t}:{slope_tickers.get(t, {}).get('severity', 'none')}"
        for t in sorted_tickers
    )

    # 1. High-vol + unrealized loss — strongest signal, both dimensions agree
    loss_candidates: list[tuple[str, float, float, float]] = []
    for t in sorted_tickers:
        v_data = vol_tickers.get(t, {})
        v_ann = v_data.get('details', {}).get('annualized_vol', 0)
        v_sev = v_data.get('severity', 'none')
        loss_pct = _unrealized_pct(t)
        if v_sev in ('high', 'critical') and loss_pct < -5:
            s_ann = slope_tickers.get(t, {}).get('details', {}).get('annualized_pct', 0)
            loss_candidates.append((t, loss_pct, v_ann, s_ann))
    if loss_candidates:
        # Pick the deepest loss
        loss_candidates.sort(key=lambda x: x[1])
        t, loss_pct, v_ann, s_ann = loss_candidates[0]
        tmpls = templates.get('combined', {}).get('position_loss_with_volatility', [])
        tmpl = _pick(tmpls, hash_base)
        try:
            return tmpl.format(
                ticker=t, loss_pct=abs(loss_pct), vol=v_ann, slope=s_ann,
            )
        except (KeyError, ValueError):
            return tmpl

    # 1b. Deep unrealized loss even without elevated volatility. An underwater
    # book whose names recently bounced reads as a "broad uptrend" by slope, so
    # without this the brief would lead with momentum/strength on a portfolio
    # that is actually carrying significant losses. Lead with the deepest loss.
    deep_losers: list[tuple[str, float]] = []
    for t in sorted_tickers:
        loss_pct = _unrealized_pct(t)
        sev = perf_tickers.get(t, {}).get('severity', 'none')
        if loss_pct <= -25 or sev == 'critical':
            deep_losers.append((t, loss_pct))
    if deep_losers:
        deep_losers.sort(key=lambda x: x[1])
        t, loss_pct = deep_losers[0]
        tmpls = templates.get('combined', {}).get('position_loss_only', [])
        tmpl = _pick(tmpls, hash_base)
        try:
            return tmpl.format(ticker=t, loss_pct=abs(loss_pct))
        except (KeyError, ValueError):
            return tmpl

    # 2. High-vol + declining slope — prefer tickers also at unrealized loss
    declining_candidates: list[tuple[str, float, float, float]] = []
    for t in sorted_tickers:
        s_data = slope_tickers.get(t, {})
        v_data = vol_tickers.get(t, {})
        s_ann = s_data.get('details', {}).get('annualized_pct', 0)
        v_ann = v_data.get('details', {}).get('annualized_vol', 0)
        v_sev = v_data.get('severity', 'none')
        if v_sev in ('high', 'critical') and s_ann < -5:
            # Alignment score: prefer tickers also losing money
            pl = _unrealized_pct(t)
            align = 0 if pl < 0 else 1  # 0 = aligned (loss), 1 = unaligned (profit)
            declining_candidates.append((t, align, s_ann, v_ann))
    if declining_candidates:
        declining_candidates.sort(key=lambda x: (x[1], x[2]))
        t, _, s_ann, v_ann = declining_candidates[0]
        tmpls = templates.get('combined', {}).get('high_vol_declining', [])
        tmpl = _pick(tmpls, hash_base)
        try:
            return tmpl.format(ticker=t, vol=v_ann, slope=s_ann)
        except (KeyError, ValueError):
            return tmpl

    # NOTE: we deliberately do NOT lead the brief with a "high volatility on X
    # has not derailed its uptrend" sentence. Foregrounding the most volatile
    # *rising* holding praises the very position a risk-conscious reader should
    # be wary of (and surfaces the clamped, non-credible momentum figure). Loss
    # and decline signals above DO lead — those are the dominant risk — but a
    # purely-rising high-vol book falls through to the portfolio-state sentence.

    # 3. Portfolio-level slope state
    state = port_slope.get('details', {}).get('state', 'mixed')
    slope_tmpls = templates.get('slope', {})

    details = port_slope.get('details', {})

    # Don't frame a concentration-dominated book as "strength across holdings":
    # when one position is more than half the portfolio and at least one name is
    # declining, the broad-uptrend praise foregrounds the wrong thing. Fall back
    # to the neutral mixed framing (the dominant-position risk is surfaced by the
    # CTA sentence).
    weights = pool_results.get('_positions_summary', {}).get('ticker_weights', {})
    max_weight = max(weights.values()) if weights else 0.0
    if state == 'broad_uptrend' and max_weight > 0.50 and details.get('down_count', 0) >= 1:
        state = 'mixed'
    ctx = {
        'slope': slope_val,
        'vol': vol_val,
        'up_count': details.get('up_count', 0),
        'down_count': details.get('down_count', 0),
        'total': details.get('total_count', 0),
        'up_tickers': ', '.join(details.get('up_tickers', [])[:5]),
        'down_tickers': ', '.join(details.get('down_tickers', [])[:5]),
    }

    if state == 'broad_decline':
        tmpls = slope_tmpls.get('portfolio_broad_decline', [])
    elif state == 'broad_uptrend':
        tmpls = slope_tmpls.get('portfolio_broad_uptrend', [])
    else:
        tmpls = slope_tmpls.get('portfolio_mixed', [])

    if tmpls:
        tmpl = _pick(tmpls, hash_base)
        try:
            return tmpl.format(**ctx)
        except (KeyError, ValueError):
            return tmpl

    # 4. Fallback — low vol stable
    tmpls = templates.get('combined', {}).get('low_vol_stable', [])
    tmpl = _pick(tmpls, hash_base)
    try:
        return tmpl.format(slope=slope_val, vol=vol_val)
    except (KeyError, ValueError):
        return tmpl or 'The portfolio is holding steady with no unusual signals.'
