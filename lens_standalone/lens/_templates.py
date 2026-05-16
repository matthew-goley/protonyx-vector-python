"""Sentence-template loader for the standalone Lens copy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..paths import resource_path

_CACHE: dict[str, Any] | None = None


def _find_templates_file() -> Path:
    local = Path(__file__).parent / 'templates' / 'sentences.json'
    if local.exists():
        return local

    bundled = resource_path('lens', 'templates', 'sentences.json')
    if bundled.exists():
        return bundled

    raise FileNotFoundError(
        f'sentences.json not found. Looked in:\n  {local}\n  {bundled}'
    )


def load_templates() -> dict[str, Any]:
    """Return the parsed sentences.json, cached after first load."""
    global _CACHE
    if _CACHE is None:
        path = _find_templates_file()
        with open(path, 'r', encoding='utf-8') as f:
            _CACHE = json.load(f)
    return _CACHE
