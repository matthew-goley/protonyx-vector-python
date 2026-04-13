from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_pyinstaller() -> bool:
    return hasattr(sys, "_MEIPASS")


def _is_nuitka() -> bool:
    # Nuitka 1.x+ sets sys.frozen to True on standalone builds,
    # and Nuitka-compiled modules receive a __compiled__ attribute.
    if getattr(sys, "frozen", False) and not _is_pyinstaller():
        return True
    return "__compiled__" in globals()


def is_frozen() -> bool:
    """True when running from a PyInstaller or Nuitka packaged build."""
    return _is_pyinstaller() or _is_nuitka()


def _bundle_root() -> Path:
    """Return the root directory that holds bundled read-only resources."""
    if _is_pyinstaller():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    if _is_nuitka():
        return Path(sys.executable).parent
    # Dev: repository root (vector/paths.py → repo root)
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Return absolute path to a bundled read-only resource.

    Resolves correctly in:
      - Development (`python main.py`)
      - PyInstaller onefile / onedir builds (`sys._MEIPASS`)
      - Nuitka `--standalone` builds (next to the executable)
    """
    return _bundle_root().joinpath(*parts)


def user_data_dir() -> Path:
    """Return the writable user app-data directory.

    Windows: %LOCALAPPDATA%/Protonyx/Vector
    Fallback: ~/Vector/data
    """
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        path = Path(local_app_data) / "Protonyx" / "Vector"
    else:
        path = Path.home() / "Vector" / "data"

    path.mkdir(parents=True, exist_ok=True)
    return path


def user_file(*parts: str) -> Path:
    """Return a path inside the user data directory."""
    return user_data_dir().joinpath(*parts)
