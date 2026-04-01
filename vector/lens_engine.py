"""
Lens engine for Vector.

Placeholder module — the lens backend logic has been removed and will be
rebuilt from scratch.  The function signature and return format are preserved
so the UI framework (LensDisplay, VectorLensPage, Monte Carlo graphs,
pie charts, caution gauge) continues to work with placeholder data.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


def generate_lens(
    positions: list[dict[str, Any]],
    store: Any,
    settings: dict[str, Any],
) -> tuple[str, str, list[str], float, str, str, int]:
    """
    Placeholder — returns the canonical 7-tuple with stub values:

    - ``text``                — placeholder message
    - ``color``               — neutral grey
    - ``recommended_tickers`` — empty list
    - ``deposit_amount``      — 0.0
    - ``underweight_sector``  — empty string
    - ``action_type``         — 'hold'
    - ``caution_score``       — 0
    """
    if not positions:
        return (
            'Add your first position to see Lens analytics tailored to your '
            'actual holdings.',
            '#8d98af', [], 0.0, '', 'hold', 0,
        )

    return (
        'Vector Lens is being rebuilt — a new analysis engine is coming soon. '
        'Your positions are still being tracked and all market data is up to date.',
        '#8d98af',
        [],
        0.0,
        '',
        'hold',
        0,
    )
