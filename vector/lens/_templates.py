"""Shared sentence-template loader.

Works in dev, PyInstaller, and Nuitka standalone builds. Prefers the
package-local file (the normal case when templates ship as package data);
falls back to `resource_path()` if the packager placed the templates next
to the executable instead of inside the package tree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vector.paths import resource_path

_CACHE: dict[str, Any] | None = None


def _find_templates_file() -> Path:
    local = Path(__file__).parent / 'templates' / 'sentences.json'
    if local.exists():
        return local

    bundled = resource_path('vector', 'lens', 'templates', 'sentences.json')
    if bundled.exists():
        return bundled

    assets_bundled = resource_path('lens', 'templates', 'sentences.json')
    if assets_bundled.exists():
        return assets_bundled

    raise FileNotFoundError(
        f'sentences.json not found. Looked in:\n  {local}\n  {bundled}\n  {assets_bundled}'
    )


def load_templates() -> dict[str, Any]:
    """Return the parsed sentences.json, cached after first load."""
    global _CACHE
    if _CACHE is None:
        path = _find_templates_file()
        with open(path, 'r', encoding='utf-8') as f:
            _CACHE = json.load(f)
    return _CACHE
