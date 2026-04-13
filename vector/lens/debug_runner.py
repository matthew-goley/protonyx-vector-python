"""Lens debug test runner.

Loads mock portfolios from debug_test.json, runs the Lens engine across all of
them at all 3 risk tiers, and writes a markdown report to output.md.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from vector.lens.lens_output import build_lens_output
from vector.paths import resource_path, user_data_dir


def _resolve_debug_test_path() -> Path:
    """Return a usable debug_test.json path.

    Priority: user data dir (editable) > dev repo root > bundled resource.
    If only the bundled version exists, copy it to the user data dir so it's
    editable on subsequent runs.
    """
    user_path = user_data_dir() / 'debug_test.json'
    if user_path.exists():
        return user_path

    dev_path = Path(__file__).resolve().parents[2] / 'debug_test.json'
    if dev_path.exists() and (dev_path.parent / 'main.py').exists():
        return dev_path

    bundled = resource_path('debug_test.json')
    if bundled.exists():
        try:
            user_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(bundled, user_path)
            return user_path
        except Exception:
            return bundled

    raise FileNotFoundError(f'debug_test.json not found. Expected at: {user_path}')


def _output_path() -> Path:
    """Write the debug report to the writable user data dir in packaged builds."""
    dev_root = Path(__file__).resolve().parents[2]
    if dev_root.is_dir() and (dev_root / 'main.py').exists():
        return dev_root / 'output.md'
    return user_data_dir() / 'output.md'


def _build_mock_position(raw: dict, store: Any) -> dict | None:
    ticker = raw['ticker'].upper().strip()
    shares = float(raw['shares'])
    entry_price = float(raw.get('entry_price', 0))

    try:
        snapshot = store.get_snapshot(ticker, '5 min')
        if not snapshot or not snapshot.get('price'):
            return None
        current_price = float(snapshot['price'])
        equity = shares * (entry_price if entry_price > 0 else current_price)
        return {
            'ticker': ticker,
            'shares': shares,
            'equity': equity,
            'price': current_price,
            'sector': snapshot.get('sector', 'Unknown'),
            'name': snapshot.get('name', ticker),
            'added_at': datetime.utcnow().isoformat(),
        }
    except Exception as e:
        print(f'[debug_runner] Failed to build position for {ticker}: {e}')
        return None


def _format_cta(cta: dict) -> str:
    action = cta.get('action', '?').upper()
    ticker = cta.get('ticker', '?') or '—'
    dollars = cta.get('dollars', 0.0) or 0.0
    reason = cta.get('reason', '?')
    severity = cta.get('severity', '?')

    if action in ('SELL', 'REBALANCE'):
        amount_str = f'-${abs(dollars):,.0f}'
    elif action in ('BUY_NEW', 'BUY_MORE'):
        amount_str = f'+${dollars:,.0f}'
    else:
        amount_str = '(no $)'

    return f'  - **{action}** `{ticker}` {amount_str} — _{reason}_ (severity: {severity})'


def _format_portfolio_section(portfolio: dict, results_by_tier: dict) -> str:
    lines: list[str] = []
    lines.append(f"## {portfolio['name']}")
    if portfolio.get('description'):
        lines.append(f"_{portfolio['description']}_")
        lines.append('')

    lines.append('**Positions:**')
    for pos in portfolio['positions']:
        lines.append(
            f"- {pos['ticker']}: {pos['shares']} shares @ entry "
            f"${pos.get('entry_price', '?')}"
        )
    lines.append('')

    for tier in ('low', 'regular', 'high'):
        tier_label = {'low': 'Conservative', 'regular': 'Moderate', 'high': 'Aggressive'}[tier]
        result = results_by_tier.get(tier)
        lines.append(f'### {tier_label} (`{tier}`)')

        if result is None:
            lines.append('_(failed — see console)_')
            lines.append('')
            continue

        lines.append(f"**Brief:** {result.get('brief', '(no brief)')}")
        lines.append('')
        lines.append(f"**Caution score:** {result.get('caution_score', 0)}/99")
        lines.append(f"**Net CTA delta:** ${result.get('net_cta_delta', 0):,.0f}")
        lines.append('')

        ctas = result.get('ctas', [])
        if not ctas:
            lines.append('_No CTAs generated._')
        else:
            lines.append(f'**CTAs ({len(ctas)}):**')
            for cta in ctas:
                lines.append(_format_cta(cta))
        lines.append('')

    lines.append('---')
    lines.append('')
    return '\n'.join(lines)


def run_debug_tests(
    store: Any,
    base_settings: dict,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Path:
    """Run all mock portfolios across all 3 tiers; write output.md; return its path."""
    debug_path = _resolve_debug_test_path()
    output_path = _output_path()

    with open(debug_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    portfolios = config.get('portfolios', [])
    if not portfolios:
        raise ValueError('debug_test.json contains no portfolios')

    total_steps = len(portfolios) * 3
    current_step = 0

    output_lines: list[str] = [
        '# Lens Debug Test Output',
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        f'_Portfolios tested: {len(portfolios)}_',
        '',
        '---',
        '',
    ]

    for portfolio in portfolios:
        if progress_callback:
            progress_callback(current_step, total_steps, f"Building {portfolio['name']}...")

        mock_positions: list[dict] = []
        for raw_pos in portfolio['positions']:
            built = _build_mock_position(raw_pos, store)
            if built:
                mock_positions.append(built)

        if not mock_positions:
            print(f"[debug_runner] Skipping {portfolio['name']} — no positions could be built")
            current_step += 3
            continue

        results_by_tier: dict[str, Any] = {}
        for tier in ('low', 'regular', 'high'):
            if progress_callback:
                progress_callback(
                    current_step, total_steps, f"{portfolio['name']} → {tier}",
                )

            test_settings = dict(base_settings)
            test_settings['risk_tier'] = tier

            try:
                result = build_lens_output(mock_positions, store, test_settings, save_history=False)
                results_by_tier[tier] = result
            except Exception as e:
                print(f"[debug_runner] {portfolio['name']} / {tier} failed: {e}")
                results_by_tier[tier] = None

            current_step += 1

        output_lines.append(_format_portfolio_section(portfolio, results_by_tier))

    if progress_callback:
        progress_callback(total_steps, total_steps, 'Writing output.md...')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    return output_path
