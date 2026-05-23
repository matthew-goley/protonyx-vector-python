from __future__ import annotations

_scale: float = 1.0


def init_scale(app) -> None:
    """Initialise the global UI scale factor. Call once after QApplication is created.

    The scale is **width-driven**, not a raw devicePixelRatio: it is the ratio of
    the available screen width to ``UI_BASE_WIDTH`` (the logical width the UI is
    authored for — sidebar + margins + the 11-column grid). This makes the whole
    UI scale as one unit to *fill* the screen, so there is no empty band on the
    right of a wide window, and everything stays in proportion on any resolution.

    On a 1080p panel running at 150% Windows scaling (logical viewport ~1280 px)
    this naturally resolves to ~0.9 — the factor verified to fit perfectly — and
    grows above 1.0 on larger desktops. ``DEBUG_SCREEN_SCALE`` overrides it with a
    fixed factor for testing.
    """
    from .constants import (
        DEBUG_SCREEN_SCALE,
        UI_BASE_WIDTH,
        UI_SCALE_MAX,
        UI_SCALE_MIN,
    )
    global _scale
    if DEBUG_SCREEN_SCALE is not None:
        _scale = float(DEBUG_SCREEN_SCALE)
        return
    try:
        avail = app.primaryScreen().availableGeometry().width()
    except Exception:  # noqa: BLE001 — never let scaling crash startup
        avail = UI_BASE_WIDTH
    factor = avail / UI_BASE_WIDTH
    _scale = max(UI_SCALE_MIN, min(UI_SCALE_MAX, factor))


def sc(px: int | float) -> int:
    """Scale a pixel dimension (width/height/margin/spacing) by the UI scale factor."""
    return int(round(px * _scale))


def scf(px: int | float) -> float:
    """Scale a pixel dimension, returning a float (for painter geometry)."""
    return px * _scale


def scpt(pt: int | float) -> int:
    """Scale a font point size by the UI scale factor, floored so text never vanishes."""
    from .constants import UI_MIN_POINT_SIZE
    return max(UI_MIN_POINT_SIZE, int(round(pt * _scale)))


def scale_factor() -> float:
    """Return the current global UI scale factor."""
    return _scale
