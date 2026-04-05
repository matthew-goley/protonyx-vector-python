"""Top-level Lens assembler — orchestrates the full pipeline."""

from __future__ import annotations

import logging
from typing import Any

from .analysis_pool import run_analysis
from .cta_engine import compute_ctas
from .sentence1 import compose as compose_s1
from .sentence2 import compose as compose_s2
from .sentence3 import compose as compose_s3, compose_full_report

_log = logging.getLogger(__name__)

# Action → accent color mapping
_ACTION_COLORS: dict[str, str] = {
    'sell':      '#ff4d4d',
    'rebalance': '#ff9f43',
    'buy_new':   '#38bdf8',
    'buy_more':  '#38bdf8',
    'hold':      '#8d98af',
}


def build_lens_output(
    positions: list[dict[str, Any]],
    store: Any,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """
    Orchestrate the full Lens pipeline and return a rich result dict.

    The wrapper in ``lens_engine.py`` flattens this to the 7-tuple that
    ``LensDisplay.refresh()`` expects.
    """
    if not positions:
        return {
            'brief': (
                'Add your first position to see Lens analytics tailored '
                'to your actual holdings.'
            ),
            'color': '#8d98af',
            'recommended_tickers': [],
            'deposit_amount': 0.0,
            'underweight_sector': '',
            'action_type': 'hold',
            'caution_score': 0,
            'full_report': [],
            'ctas': [],
            'threat_level': 0.0,
            'pool_results': {},
            'projected_positions': [],
            'net_cta_delta': 0.0,
        }

    try:
        pool_results = run_analysis(positions, store, settings)
    except Exception:
        _log.debug('Lens analysis pool failed', exc_info=True)
        return _fallback_result()

    try:
        cta_list = compute_ctas(pool_results)
    except Exception:
        _log.debug('Lens CTA engine failed', exc_info=True)
        cta_list = []

    try:
        s1 = compose_s1(pool_results)
    except Exception:
        _log.debug('sentence1 failed', exc_info=True)
        s1 = ''

    try:
        s2 = compose_s2(pool_results)
    except Exception:
        _log.debug('sentence2 failed', exc_info=True)
        s2 = ''

    try:
        s3 = compose_s3(cta_list, pool_results)
    except Exception:
        _log.debug('sentence3 failed', exc_info=True)
        s3 = ''

    try:
        full_report = compose_full_report(cta_list, pool_results)
    except Exception:
        _log.debug('full_report failed', exc_info=True)
        full_report = []

    # Build brief — join non-empty sentences
    parts = [s for s in (s1, s2, s3) if s]
    brief = ' '.join(parts) if parts else 'No signals detected — the portfolio is holding steady.'

    # Determine outputs from top CTA
    top_cta = cta_list[0] if cta_list else {}
    action_type = top_cta.get('action', 'hold')
    color = _ACTION_COLORS.get(action_type, '#8d98af')

    # Recommended tickers from top CTA
    recommended_tickers: list[str] = []
    details = top_cta.get('details', {})
    suggested = details.get('suggested_tickers', [])
    if suggested:
        recommended_tickers = suggested
    elif top_cta.get('ticker'):
        recommended_tickers = [top_cta['ticker']]

    deposit_amount = top_cta.get('dollars', 0.0)
    underweight_sector = details.get('target_sector', details.get('heavy_sector', ''))

    # Caution score = total CTA dollars / total equity, scaled to 1–99.
    # Represents what fraction of the portfolio the engine suggests moving.
    total_equity = pool_results.get('_positions_summary', {}).get('total_equity', 1.0)
    threat_level = sum(abs(c.get('dollars', 0)) for c in cta_list) / max(total_equity, 1.0)
    caution_score = max(1, min(99, int(threat_level * 100)))

    # Build projected positions with all CTAs applied
    projected_positions, net_cta_delta = _apply_all_ctas(
        positions, cta_list, store, settings,
    )

    return {
        'brief': brief,
        'color': color,
        'recommended_tickers': recommended_tickers,
        'deposit_amount': deposit_amount,
        'underweight_sector': underweight_sector,
        'action_type': action_type,
        'caution_score': caution_score,
        'full_report': full_report,
        'ctas': cta_list,
        'threat_level': threat_level,
        'pool_results': pool_results,
        'projected_positions': projected_positions,
        'net_cta_delta': net_cta_delta,
    }


def _apply_all_ctas(
    positions: list[dict[str, Any]],
    cta_list: list[dict[str, Any]],
    store: Any,
    settings: dict[str, Any],
) -> tuple[list[dict[str, Any]], float]:
    """
    Apply every CTA to a copy of positions and return
    ``(projected_positions, net_cta_delta)``.

    - sell / rebalance: reduce position value (remove if fully sold).
    - buy_more: increase existing position value.
    - buy_new: add a new position (fetch sector/name from store).
    - hold: no change.
    """
    from copy import deepcopy

    pos_map: dict[str, dict] = {}
    for p in deepcopy(positions):
        t = p['ticker']
        # Use current market value as the position value
        price = p.get('price', 0.0)
        shares = p.get('shares', 0.0)
        p['_value'] = shares * price if price > 0 else p.get('equity', 0.0)
        pos_map[t] = p

    net_delta = 0.0

    for cta in cta_list:
        action = cta.get('action', 'hold')
        ticker = cta.get('ticker', '')
        dollars = cta.get('dollars', 0.0)

        if action in ('sell', 'rebalance') and ticker and dollars > 0:
            net_delta -= dollars
            if ticker in pos_map:
                pos = pos_map[ticker]
                pos['_value'] = max(0.0, pos['_value'] - dollars)
                price = pos.get('price', 0.0)
                if price > 0:
                    pos['shares'] = pos['_value'] / price
                if pos['_value'] <= 0:
                    del pos_map[ticker]

        elif action == 'buy_more' and ticker and dollars > 0:
            net_delta += dollars
            if ticker in pos_map:
                pos = pos_map[ticker]
                pos['_value'] += dollars
                price = pos.get('price', 0.0)
                if price > 0:
                    pos['shares'] = pos['_value'] / price

        elif action == 'buy_new' and ticker and dollars > 0:
            net_delta += dollars
            if ticker in pos_map:
                # Already held — treat as buy_more
                pos = pos_map[ticker]
                pos['_value'] += dollars
                price = pos.get('price', 0.0)
                if price > 0:
                    pos['shares'] = pos['_value'] / price
            else:
                # New position — fetch metadata
                price = 0.0
                sector = 'Unknown'
                name = ticker
                try:
                    refresh = settings.get('refresh_interval', '5 min')
                    snap = store.get_snapshot(ticker, refresh) or {}
                    price = snap.get('price', 0.0)
                    sector = snap.get('sector', 'Unknown') or 'Unknown'
                    name = snap.get('name', ticker) or ticker
                except Exception:
                    pass
                shares = dollars / price if price > 0 else 0.0
                pos_map[ticker] = {
                    'ticker': ticker,
                    'shares': shares,
                    'equity': dollars,
                    'price': price,
                    'sector': sector,
                    'name': name,
                    '_value': dollars,
                }

            # Also check suggested_tickers from details — multiple tickers
            # per CTA are split evenly via the main ticker field already
            # handled by cta_engine, so no extra work needed here.

    # Build final list, dropping the internal _value field
    projected: list[dict[str, Any]] = []
    for p in pos_map.values():
        out = {k: v for k, v in p.items() if k != '_value'}
        out['equity'] = p['_value']  # update equity to projected value
        projected.append(out)

    return projected, net_delta


def _fallback_result() -> dict[str, Any]:
    return {
        'brief': (
            'Unable to generate a lens insight right now. '
            'Check your positions and try refreshing.'
        ),
        'color': '#8d98af',
        'recommended_tickers': [],
        'deposit_amount': 0.0,
        'underweight_sector': '',
        'action_type': 'hold',
        'caution_score': 0,
        'full_report': [],
        'ctas': [],
        'threat_level': 0.0,
        'pool_results': {},
        'projected_positions': [],
        'net_cta_delta': 0.0,
    }
