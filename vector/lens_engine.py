"""
Lens engine wrapper for Vector.

Thin shell that calls the modular ``vector.lens`` package and returns
the canonical 7-tuple expected by ``LensDisplay.refresh()`` and all
other existing call sites.
"""

from __future__ import annotations

from typing import Any

from vector.lens.lens_output import build_lens_output


def generate_lens(
    positions: list[dict[str, Any]],
    store: Any,
    settings: dict[str, Any],
) -> tuple[str, str, list[str], float, str, str, int]:
    result = build_lens_output(positions, store, settings)
    return (
        result['brief'],
        result['color'],
        result['recommended_tickers'],
        result['deposit_amount'],
        result['underweight_sector'],
        result['action_type'],
        result['caution_score'],
    )


def generate_lens_full(
    positions: list[dict[str, Any]],
    store: Any,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Return the complete Lens result dict for the full Lens page."""
    return build_lens_output(positions, store, settings)
