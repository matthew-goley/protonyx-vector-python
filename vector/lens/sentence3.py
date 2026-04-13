"""Sentence 3 — CTA composer (picks highest-priority action)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from vector.lens._templates import load_templates as _load_templates

_log = logging.getLogger(__name__)


def _pick(templates: list[str], hash_key: str) -> str:
    if not templates:
        return ''
    h = int(hashlib.sha256(hash_key.encode()).hexdigest(), 16)
    return templates[h % len(templates)]


def _build_ctx(cta: dict, pool_results: dict) -> dict[str, Any]:
    """Build the variable context dict for template formatting."""
    details = cta.get('details', {})
    summary = pool_results.get('_positions_summary', {})
    suggested = details.get('suggested_tickers', [])

    return {
        'ticker': cta.get('ticker', ''),
        'dollars': cta.get('dollars', 0),
        'weight': details.get('current_weight', details.get('weight_pct', details.get('weight', 0))),
        'slope': details.get('slope_pct', 0),
        'vol': details.get('vol_pct', 0),
        'sector': details.get('target_sector', details.get('heavy_sector', '')),
        'sector_weight': details.get('sector_weight', 0),
        'heavy_ticker': details.get('heavy_ticker', cta.get('ticker', '')),
        'target_weight': details.get('target_weight', 30),
        'entry_weight': details.get('entry_weight', 0),
        'value': pool_results.get('beta', {}).get('portfolio_result', {}).get('details', {}).get('beta', 1.0),
        'unrealized_pct': abs(details.get('unrealized_pct', 0)),
        'unrealized_dollar': abs(details.get('unrealized_dollar', 0)),
        'count': len(summary.get('ticker_weights', {})),
        'total': len(summary.get('ticker_weights', {})),
    }


def _render_cta(cta: dict, pool_results: dict, hash_key: str) -> str:
    """Render a single CTA into a sentence."""
    templates = _load_templates().get('sentence3', {})
    action = cta.get('action', 'hold')
    reason = cta.get('reason', 'portfolio_healthy')
    severity = cta.get('severity', 'none')

    action_tmpls = templates.get(action, {})
    reason_tmpls = action_tmpls.get(reason, {})

    # Try severity-specific, then 'default'
    tmpls = reason_tmpls.get(severity, reason_tmpls.get('default', []))
    if not tmpls:
        # Fallback: try hold > portfolio_healthy
        tmpls = templates.get('hold', {}).get('portfolio_healthy', {}).get('default', [])

    tmpl = _pick(tmpls, hash_key)
    if not tmpl:
        return 'No specific action is indicated at this time.'

    ctx = _build_ctx(cta, pool_results)
    try:
        return tmpl.format(**ctx)
    except (KeyError, ValueError) as exc:
        _log.debug('sentence3 format failed: %s', exc)
        return tmpl


_DIVERSIFICATION_REASONS = frozenset({
    'reduce_concentration', 'sector_underweight',
})


def compose(cta_list: list[dict], pool_results: dict) -> str:
    """
    Take the CTA list (already sorted by priority) and return one sentence.

    Diversification CTAs (reduce_concentration, sector_underweight) are
    always preferred for the brief because they're the most actionable
    and approachable recommendation for casual investors.
    """
    if not cta_list:
        templates = _load_templates().get('sentence3', {})
        tmpls = templates.get('hold', {}).get('portfolio_healthy', {}).get('default', [])
        return _pick(tmpls, 'empty') or 'No action signals detected.'

    # Prefer diversification CTAs — pick the first (largest dollar amount)
    top = None
    for cta in cta_list:
        if cta.get('reason') in _DIVERSIFICATION_REASONS:
            top = cta
            break

    # Fall back to highest-priority CTA
    if top is None:
        top = cta_list[0]

    sorted_tickers = sorted(
        pool_results.get('_positions_summary', {}).get('ticker_weights', {}).keys()
    )
    hash_key = f"s3|{top.get('reason', '')}|{'|'.join(sorted_tickers)}"

    return _render_cta(top, pool_results, hash_key)


def compose_full_report(cta_list: list[dict], pool_results: dict) -> list[str]:
    """Return one sentence per CTA in the list (all of them)."""
    results: list[str] = []
    for i, cta in enumerate(cta_list):
        hash_key = f"s3_full|{i}|{cta.get('reason', '')}"
        sentence = _render_cta(cta, pool_results, hash_key)
        if sentence:
            results.append(sentence)
    return results
