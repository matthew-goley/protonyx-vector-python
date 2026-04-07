"""
Base class for all Vector dashboard widgets.

To create a new widget type:
1. Add a .py file in vector/widget_types/
2. Define a class that subclasses VectorWidget
3. Set NAME, DESCRIPTION, DEFAULT_ROWSPAN, DEFAULT_COLSPAN
4. Implement __init__ to build your UI (call super().__init__() first)

The widget will be auto-discovered and appear in the picker dialog.
"""

from PyQt6.QtWidgets import QFrame, QMenu
from PyQt6.QtCore import Qt, QPoint


class VectorWidget(QFrame):
    """Base class for all placeable dashboard widgets."""

    NAME: str = 'Widget'
    DESCRIPTION: str = ''
    DEFAULT_ROWSPAN: int = 2
    DEFAULT_COLSPAN: int = 2

    def __init__(self, window=None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName('vectorWidget')
        self._window = window   # VectorMainWindow reference — access store, positions, settings
        self._edit_mode = False
        self._drag_offset = QPoint()
        self._apply_style(False)

    def refresh(self) -> None:
        """Called by DashboardPage whenever data is refreshed. Override to update display."""

    # -- styling (subclasses may override) ------------------------------------

    def _apply_style(self, edit: bool) -> None:
        self.setProperty('editing', 'true' if edit else 'false')
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    # -- edit mode ------------------------------------------------------------

    def set_edit_mode(self, enabled: bool) -> None:
        self._edit_mode = enabled
        self._apply_style(enabled)
        self.setCursor(
            Qt.CursorShape.SizeAllCursor if enabled else Qt.CursorShape.ArrowCursor
        )

    # -- drag (works automatically when edit mode is on) ----------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.pos()
            self.raise_()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._edit_mode and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(self.mapToParent(event.pos() - self._drag_offset))
            parent = self.parent()
            if hasattr(parent, '_on_drag_move'):
                parent._on_drag_move(self)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._edit_mode and event.button() == Qt.MouseButton.LeftButton:
            parent = self.parent()
            if hasattr(parent, '_on_drag_release'):
                parent._on_drag_release(self)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        if not self._edit_mode:
            super().contextMenuEvent(event)
            return
        menu = QMenu(self)
        delete_action = menu.addAction('Delete Widget')
        if menu.exec(event.globalPos()) == delete_action:
            parent = self.parent()
            if hasattr(parent, 'remove_widget'):
                parent.remove_widget(self)
