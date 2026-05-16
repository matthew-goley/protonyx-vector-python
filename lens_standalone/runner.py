"""Standalone CLI runner for the Lens engine.

Loads `debug_test.json`, runs the full Lens pipeline against yfinance via
`DataShim`, prints a colored terminal report, and writes `output.md`.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Silence yfinance / urllib3 chatter (404s on missing fundamentals, etc.)
# before any yfinance import in this process.
for _name in ('yfinance', 'peewee', 'urllib3', 'urllib3.connectionpool'):
    logging.getLogger(_name).setLevel(logging.CRITICAL)

from .data_shim import DataShim
from .lens.lens_output import build_lens_output


# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------

class _C:
    RESET = '\x1b[0m'
    DIM = '\x1b[2m'
    BOLD = '\x1b[1m'

    GREY = '\x1b[38;5;245m'
    WHITE = '\x1b[38;5;255m'

    RED = '\x1b[38;5;203m'
    ORANGE = '\x1b[38;5;215m'
    YELLOW = '\x1b[38;5;221m'
    GREEN = '\x1b[38;5;114m'
    CYAN = '\x1b[38;5;117m'
    BLUE = '\x1b[38;5;111m'
    MAGENTA = '\x1b[38;5;176m'


def _enable_windows_ansi() -> None:
    """Turn on ANSI processing + UTF-8 stdout on Windows. No-op on POSIX."""
    # Encoding: cp1252 stdout chokes on the box-drawing characters used in
    # the banner and section dividers. Reconfigure to UTF-8 if we can.
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    if os.name != 'nt':
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STDOUT
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


_ACTION_COLOR = {
    'sell': _C.RED,
    'rebalance': _C.ORANGE,
    'buy_new': _C.CYAN,
    'buy_more': _C.CYAN,
    'hold': _C.GREY,
}


def _money(value: float) -> str:
    sign = '-' if value < 0 else ''
    return f"{sign}${abs(value):,.0f}"


def _signed_money(value: float) -> str:
    sign = '+' if value >= 0 else '-'
    return f"{sign}${abs(value):,.0f}"


# ---------------------------------------------------------------------------
# Terminal section helpers
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    bar = '─' * max(0, 42 - len(title) - 1)
    print(f"{_C.DIM}── {_C.RESET}{_C.BOLD}{title}{_C.RESET} {_C.DIM}{bar}{_C.RESET}")


def _banner(positions: int, equity: float) -> None:
    inner = 41  # inner content width between the two box pipes
    top = '┌' + '─' * inner + '┐'
    bot = '└' + '─' * inner + '┘'

    title = 'LENS STANDALONE'
    title_inner = f"  {title}".ljust(inner)
    line1 = (
        f"{_C.BLUE}│{_C.RESET}"
        f"  {_C.BOLD}{title}{_C.RESET}"
        f"{' ' * (inner - len(title) - 2)}"
        f"{_C.BLUE}│{_C.RESET}"
    )

    pos_str = f"Portfolio: {positions} positions | ${equity:,.0f}"
    pos_inner = f"  {pos_str}".ljust(inner)
    line2 = f"{_C.BLUE}│{_C.RESET}{pos_inner}{_C.BLUE}│{_C.RESET}"

    print(f"{_C.BLUE}{top}{_C.RESET}")
    print(line1)
    print(line2)
    print(f"{_C.BLUE}{bot}{_C.RESET}")
    print()


# ---------------------------------------------------------------------------
# Markdown output writer
# ---------------------------------------------------------------------------

def _write_markdown(path: Path, positions: list[dict], settings: dict, result: dict) -> None:
    pool = result.get('pool_results', {})
    summary = pool.get('_positions_summary', {})
    total_equity = summary.get('total_equity', 0)
    sector_weights = summary.get('sector_weights', {})

    slope_t = pool.get('slope', {}).get('ticker_results', {})
    vol_t = pool.get('volatility', {}).get('ticker_results', {})
    beta_t = pool.get('beta', {}).get('ticker_results', {})
    perf_t = pool.get('performance', {}).get('ticker_results', {})

    lines: list[str] = []
    lines.append('# Lens Standalone Report')
    lines.append(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")
    lines.append(f"_Risk tier: `{settings.get('risk_tier', 'regular')}`_")
    lines.append('')
    lines.append('---')
    lines.append('')

    # Portfolio overview
    lines.append('## Portfolio')
    lines.append(f"**Total equity:** ${total_equity:,.2f}")
    lines.append(f"**Positions:** {len(positions)}")
    lines.append('')
    lines.append('| Ticker | Sector | Shares | Price | Value | Weight |')
    lines.append('|---|---|---:|---:|---:|---:|')
    tw = summary.get('ticker_weights', {})
    tcv = summary.get('ticker_current_values', {})
    tcp = summary.get('ticker_current_prices', {})
    for p in positions:
        t = p['ticker']
        lines.append(
            f"| {t} | {p.get('sector', '?')} | {p.get('shares', 0):g} | "
            f"${tcp.get(t, 0):,.2f} | ${tcv.get(t, 0):,.2f} | "
            f"{tw.get(t, 0) * 100:.1f}% |"
        )
    lines.append('')

    # Sector weights
    if sector_weights:
        lines.append('### Sector allocation')
        for s, w in sorted(sector_weights.items(), key=lambda x: -x[1]):
            lines.append(f"- {s}: {w * 100:.1f}%")
        lines.append('')

    # Brief
    lines.append('## Brief')
    lines.append(f"> {result.get('brief', '')}")
    lines.append('')

    # Caution score
    caution = result.get('caution_score', 0)
    action = result.get('action_type', 'hold')
    lines.append('## Caution score')
    lines.append(f"**{caution} / 99** — top action: `{action}`")
    lines.append(f"**Net CTA delta:** {_signed_money(result.get('net_cta_delta', 0))}")
    lines.append('')

    # CTAs
    ctas = result.get('ctas', [])
    lines.append(f"## CTAs ({len(ctas)})")
    if not ctas:
        lines.append('_No CTAs generated._')
    else:
        lines.append('| # | Priority | Action | Ticker | Dollars | Reason | Severity |')
        lines.append('|---|---:|---|---|---:|---|---|')
        for i, c in enumerate(ctas, 1):
            d = c.get('dollars', 0)
            if c.get('action') in ('sell', 'rebalance'):
                dstr = f"-${abs(d):,.0f}"
            elif c.get('action') in ('buy_new', 'buy_more'):
                dstr = f"+${d:,.0f}"
            else:
                dstr = '—'
            lines.append(
                f"| {i} | P{c.get('priority', '?')} | {c.get('action', '?')} | "
                f"`{c.get('ticker', '') or '—'}` | {dstr} | "
                f"{c.get('reason', '?')} | {c.get('severity', '?')} |"
            )
    lines.append('')

    # Full report
    full_report = result.get('full_report', [])
    if full_report:
        lines.append('## Full report')
        for i, sentence in enumerate(full_report, 1):
            lines.append(f"{i}. {sentence}")
        lines.append('')

    # Analyzer summaries
    lines.append('## Analyzer summaries')
    lines.append('')
    lines.append('### Per-ticker')
    lines.append('| Ticker | Slope (annualized) | Volatility | Beta | Unrealized P&L |')
    lines.append('|---|---:|---:|---:|---:|')
    for p in positions:
        t = p['ticker']
        s = slope_t.get(t, {}).get('details', {}).get('annualized_pct', 0)
        v = vol_t.get(t, {}).get('details', {}).get('annualized_vol', 0)
        b = beta_t.get(t, {}).get('details', {}).get('beta', 0)
        pl = perf_t.get(t, {}).get('details', {}).get('unrealized_return_pct', 0)
        lines.append(f"| {t} | {s:+.1f}% | {v:.1f}% | {b:.2f} | {pl:+.1f}% |")
    lines.append('')

    # Portfolio aggregates
    lines.append('### Portfolio aggregates')
    port_slope = pool.get('slope', {}).get('portfolio_result', {}).get('details', {})
    port_vol = pool.get('volatility', {}).get('portfolio_result', {}).get('details', {})
    port_beta = pool.get('beta', {}).get('portfolio_result', {}).get('details', {})
    port_conc = pool.get('concentration', {}).get('portfolio_result', {}).get('details', {})
    lines.append(f"- Slope: {port_slope.get('annualized_pct', 0):+.1f}% ({port_slope.get('state', '?')})")
    lines.append(f"- Volatility: {port_vol.get('annualized_vol', 0):.1f}%")
    lines.append(f"- Beta: {port_beta.get('beta', 0):.2f}")
    lines.append(f"- Heaviest sector: {port_conc.get('heaviest_sector', '?')} ({port_conc.get('heaviest_sector_weight', 0):.1f}%)")
    lines.append('')

    # Projected positions
    projected = result.get('projected_positions', [])
    lines.append(f"## Projected positions after CTAs ({len(projected)})")
    if projected:
        lines.append('| Ticker | Sector | Shares | Value |')
        lines.append('|---|---|---:|---:|')
        for p in projected:
            lines.append(
                f"| {p.get('ticker', '?')} | {p.get('sector', '?')} | "
                f"{p.get('shares', 0):.2f} | ${p.get('equity', 0):,.0f} |"
            )
    lines.append('')

    path.write_text('\n'.join(lines), encoding='utf-8')


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run() -> int:
    _enable_windows_ansi()

    here = Path(__file__).resolve().parent
    debug_path = here / 'debug_test.json'
    output_path = here / 'output.md'

    if not debug_path.exists():
        print(f"{_C.RED}error:{_C.RESET} {debug_path} not found")
        return 2

    config = json.loads(debug_path.read_text(encoding='utf-8'))
    positions = config.get('positions', [])
    settings = config.get('settings', {})

    if not positions:
        print(f"{_C.RED}error:{_C.RESET} debug_test.json contains no positions")
        return 2

    placeholder_equity = sum(
        float(p.get('shares', 0) or 0) * float(p.get('price', 0) or 0) or float(p.get('equity', 0) or 0)
        for p in positions
    )
    _banner(len(positions), placeholder_equity)

    print(f"{_C.DIM}Risk tier: {settings.get('risk_tier', 'regular')}  |  "
          f"Refresh: {settings.get('refresh_interval', '5 min')}{_C.RESET}")
    print()

    # Per-analyzer progress lines
    _ANALYZER_LABELS = {
        'slope': 'Slope',
        'volatility': 'Volatility',
        'earnings': 'Earnings',
        'concentration': 'Concentration',
        'dividends': 'Dividends',
        'beta': 'Beta',
        'performance': 'Performance',
        'index_fund': 'Index Fund',
    }
    ORDER = ['slope', 'volatility', 'earnings', 'concentration',
             'dividends', 'beta', 'performance', 'index_fund']

    # Pre-print pending rows
    pending: dict[str, int] = {}
    for i, name in enumerate(ORDER):
        label = _ANALYZER_LABELS.get(name, name)
        pending[name] = i
        print(f"{_C.GREY}●{_C.RESET} {label:<18} {_C.DIM}…{_C.RESET}")

    # Move cursor up to overwrite as analyzers complete
    def on_progress(name: str, elapsed: float) -> None:
        if name not in pending:
            return
        idx = pending[name]
        lines_up = len(ORDER) - idx
        label = _ANALYZER_LABELS.get(name, name)
        sys.stdout.write(f"\x1b[{lines_up}A")  # up N
        sys.stdout.write('\r')
        sys.stdout.write('\x1b[2K')  # clear line
        sys.stdout.write(
            f"{_C.GREEN}●{_C.RESET} {label:<18} "
            f"{_C.GREEN}✓{_C.RESET}  {_C.DIM}{elapsed:.1f}s{_C.RESET}"
        )
        sys.stdout.write(f"\x1b[{lines_up}B")  # down N
        sys.stdout.write('\r')
        sys.stdout.flush()

    print()
    print(f"{_C.DIM}fetching market data via yfinance — this can take a moment…{_C.RESET}")
    print()

    store = DataShim()
    t0 = time.perf_counter()
    result = build_lens_output(
        positions, store, settings,
        save_history=False,
        progress_cb=on_progress,
    )
    total_elapsed = time.perf_counter() - t0

    print()
    print(f"{_C.DIM}Total elapsed: {total_elapsed:.1f}s{_C.RESET}")
    print()

    # Brief
    _section('BRIEF')
    print(f"{_C.WHITE}{result.get('brief', '')}{_C.RESET}")
    print()

    # Caution score
    caution = result.get('caution_score', 0)
    action = result.get('action_type', 'hold')
    color = _ACTION_COLOR.get(action, _C.GREY)
    _section('CAUTION SCORE')
    print(f"{color}{_C.BOLD}{caution}{_C.RESET} {_C.DIM}/ 99{_C.RESET}  |  "
          f"Action: {color}{action}{_C.RESET}  |  "
          f"Net delta: {_signed_money(result.get('net_cta_delta', 0))}")
    print()

    # CTAs
    ctas = result.get('ctas', [])
    _section(f"CTAs ({len(ctas)} total)")
    if not ctas:
        print(f"{_C.DIM}No CTAs generated.{_C.RESET}")
    else:
        for c in ctas:
            a = c.get('action', '?')
            color = _ACTION_COLOR.get(a, _C.GREY)
            pri = f"P{c.get('priority', '?')}"
            t = c.get('ticker', '') or '—'
            d = c.get('dollars', 0)
            if a in ('sell', 'rebalance'):
                dstr = f"-${abs(d):,.0f}"
            elif a in ('buy_new', 'buy_more'):
                dstr = f"+${d:,.0f}"
            else:
                dstr = '       '
            print(
                f"  {_C.DIM}{pri:>3}{_C.RESET}  "
                f"{color}{a.upper():<9}{_C.RESET} "
                f"{_C.BOLD}{t:<6}{_C.RESET} "
                f"{color}{dstr:>9}{_C.RESET}  "
                f"{_C.DIM}{c.get('reason', '?')}{_C.RESET}"
            )
    print()

    # Full report
    full_report = result.get('full_report', [])
    if full_report:
        _section('FULL REPORT')
        for i, sentence in enumerate(full_report, 1):
            print(f"  {_C.DIM}{i:>2}.{_C.RESET} {sentence}")
        print()

    # Write markdown output
    _write_markdown(output_path, positions, settings, result)

    rel = output_path.name
    print(f"{_C.GREEN}✓{_C.RESET} Output written to {_C.BOLD}lens_standalone/{rel}{_C.RESET}")
    return 0
