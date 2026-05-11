"""
yfinance API call counter — prints a persistent one-line tally to the
terminal that updates in-place every time yfinance is touched.

Output is suppressed when stderr is not a TTY (release build with no
console, redirected output, etc.) so the counter still tracks calls but
does not spam logs.
"""
from __future__ import annotations

import sys
import threading

_count = 0
_lock = threading.Lock()


def yf_count() -> int:
    """Increment the counter, refresh the terminal line, return new total."""
    global _count
    with _lock:
        _count += 1
        n = _count
        _render(n)
    return n


def get_count() -> int:
    """Return the current total without incrementing."""
    return _count


def _render(n: int) -> None:
    stream = sys.stderr
    try:
        if not stream.isatty():
            return
    except Exception:  # noqa: BLE001
        return
    try:
        stream.write(f'\r[yfinance] API calls: {n}    ')
        stream.flush()
    except Exception:  # noqa: BLE001
        pass
