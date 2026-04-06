from __future__ import annotations

_scale: float = 1.0


def init_scale(app) -> None:
    """Initialise the DPI scale factor from the primary screen. Call once after QApplication is created."""
    global _scale
    _scale = app.primaryScreen().devicePixelRatio()


def sc(px: int | float) -> int:
    """Scale a pixel value by the current DPI scale factor."""
    return int(px * _scale)
