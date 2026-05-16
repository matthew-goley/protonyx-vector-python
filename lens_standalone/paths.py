"""Simplified path helpers for the standalone Lens package.

Only `resource_path` is provided — it resolves files relative to the
`lens_standalone/` directory so templates can be located in dev or in
any future packaged build.
"""

from __future__ import annotations

from pathlib import Path


_PACKAGE_ROOT = Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    """Resolve a file inside the lens_standalone package directory."""
    return _PACKAGE_ROOT.joinpath(*parts)
