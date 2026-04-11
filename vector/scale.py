from __future__ import annotations

_scale: float = 1.0


def init_scale(app) -> None:
    """Initialise the DPI scale factor from the primary screen. Call once after QApplication is created."""
    from .constants import DEBUG_SCREEN_SCALE
    global _scale
    _scale = DEBUG_SCREEN_SCALE if DEBUG_SCREEN_SCALE is not None else app.primaryScreen().devicePixelRatio()


def sc(px: int | float) -> int:
    """Scale a pixel value by the current DPI scale factor."""
    return int(px * _scale)
