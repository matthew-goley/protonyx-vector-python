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
    save_history: bool = True,
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

    # Caution score: sells dominate, buys contribute 30%, holds are ignored.
    # A "you should reduce risk" signal weighs much more than a "you have room
    # to grow" opportunity.
    total_equity = pool_results.get('_positions_summary', {}).get('total_equity', 1.0)
    caution_score = _compute_caution_score(cta_list, total_equity)
    threat_level = caution_score / 100.0

    # Build projected positions with all CTAs applied
    projected_positions, net_cta_delta = _apply_all_ctas(
        positions, cta_list, store, settings,
    )

    result = {
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

    if save_history:
        try:
            _save_snapshot(result)
        except Exception:
            _log.debug('lens snapshot save failed', exc_info=True)

    return result


def _save_snapshot(result: dict[str, Any]) -> None:
    """Append the current Lens result to lens_history.json (rolling 50)."""
    import json
    from datetime import datetime
    from vector.paths import user_file

    history_path = user_file('lens_history.json')

    snapshots: list[dict] = []
    if history_path.exists():
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                snapshots = data.get('snapshots', [])
        except Exception:
            snapshots = []

    total_equity = result.get('pool_results', {}).get(
        '_positions_summary', {},
    ).get('total_equity', 0)

    snapshot = {
        'timestamp': datetime.now().isoformat(timespec='seconds'),
        'brief': result.get('brief', ''),
        'caution_score': result.get('caution_score', 0),
        'action_type': result.get('action_type', 'hold'),
        'color': result.get('color', '#8d98af'),
        'total_equity': total_equity,
        'cta_count': len(result.get('ctas', [])),
    }
    # Only append if something meaningful has changed vs. the last snapshot
    if snapshots:
        last = snapshots[-1]
        same = (
            last.get('brief') == snapshot['brief']
            and last.get('caution_score') == snapshot['caution_score']
            and last.get('action_type') == snapshot['action_type']
            and last.get('cta_count') == snapshot['cta_count']
        )
        if same:
            return
    snapshots.append(snapshot)
    if len(snapshots) > 50:
        snapshots = snapshots[-50:]

    with open(history_path, 'w', encoding='utf-8') as f:
        json.dump({'snapshots': snapshots}, f, indent=2)


def _compute_caution_score(cta_list: list[dict[str, Any]], total_equity: float) -> int:
    """Caution score 1–99. Sells full weight, buys 30%, holds ignored."""
    if total_equity <= 0:
        return 0
    weighted_total = 0.0
    for cta in cta_list:
        action = cta.get('action', '')
        dollars = abs(float(cta.get('dollars', 0.0) or 0.0))
        if action in ('sell', 'rebalance'):
            weighted_total += dollars
        elif action in ('buy_new', 'buy_more'):
            weighted_total += dollars * 0.30
    score_pct = (weighted_total / total_equity) * 100
    return max(1, min(99, int(score_pct)))


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
