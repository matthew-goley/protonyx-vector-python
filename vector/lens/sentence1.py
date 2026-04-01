"""Sentence 1 — portfolio state composer (slope + volatility)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# Load templates once at module level
_TEMPLATES: dict | None = None


def _load_templates() -> dict:
    global _TEMPLATES
    if _TEMPLATES is None:
        p = Path(__file__).parent / 'templates' / 'sentences.json'
        with open(p, 'r', encoding='utf-8') as f:
            _TEMPLATES = json.load(f)
    return _TEMPLATES


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

    slope_tickers = slope_res.get('ticker_results', {})
    vol_tickers = vol_res.get('ticker_results', {})
    port_slope = slope_res.get('portfolio_result', {})
    port_vol = vol_res.get('portfolio_result', {})

    slope_val = port_slope.get('details', {}).get('annualized_pct', 0)
    vol_val = port_vol.get('details', {}).get('annualized_vol', 0)

    # Build hash key for deterministic selection
    sorted_tickers = sorted(slope_tickers.keys())
    hash_base = '|'.join(
        f"{t}:{slope_tickers.get(t, {}).get('severity', 'none')}"
        for t in sorted_tickers
    )

    # 1. Check for combined high-vol + declining ticker
    for t in sorted_tickers:
        s_data = slope_tickers.get(t, {})
        v_data = vol_tickers.get(t, {})
        s_ann = s_data.get('details', {}).get('annualized_pct', 0)
        v_ann = v_data.get('details', {}).get('annualized_vol', 0)
        s_sev = s_data.get('severity', 'none')
        v_sev = v_data.get('severity', 'none')

        if v_sev in ('high', 'critical') and s_ann < -5:
            tmpls = templates.get('combined', {}).get('high_vol_declining', [])
            tmpl = _pick(tmpls, hash_base)
            try:
                return tmpl.format(ticker=t, vol=v_ann, slope=s_ann)
            except (KeyError, ValueError):
                return tmpl

    # 2. Check for combined high-vol + rising ticker
    for t in sorted_tickers:
        s_data = slope_tickers.get(t, {})
        v_data = vol_tickers.get(t, {})
        s_ann = s_data.get('details', {}).get('annualized_pct', 0)
        v_ann = v_data.get('details', {}).get('annualized_vol', 0)
        v_sev = v_data.get('severity', 'none')

        if v_sev in ('high', 'critical') and s_ann > 5:
            tmpls = templates.get('combined', {}).get('high_vol_rising', [])
            tmpl = _pick(tmpls, hash_base)
            try:
                return tmpl.format(ticker=t, vol=v_ann, slope=s_ann)
            except (KeyError, ValueError):
                return tmpl

    # 3. Portfolio-level slope state
    state = port_slope.get('details', {}).get('state', 'mixed')
    slope_tmpls = templates.get('slope', {})

    details = port_slope.get('details', {})
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
