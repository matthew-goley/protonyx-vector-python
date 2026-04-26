from __future__ import annotations

from typing import TYPE_CHECKING, Any

from datetime import datetime

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ..scale import sc
from ..widget_registry import discover_widgets, get_widget_class

if TYPE_CHECKING:
    from vector.app import VectorMainWindow

# ---------------------------------------------------------------------------
# Grid constants
# Base values at 1× DPI: _UNIT=90, _GAP=10, _CELL=100, _CONTENT_W=1090 px.
# Defined as lazy functions so they are evaluated after init_scale() runs.
# ---------------------------------------------------------------------------
_GRID_COLS    = 11
_CONTENT_COLS = _GRID_COLS


def _UNIT() -> int: return sc(90)
def _GAP() -> int: return sc(10)
def _CELL() -> int: return _UNIT() + _GAP()
def _CONTENT_W() -> int: return _CONTENT_COLS * _CELL() - _GAP()


# ---------------------------------------------------------------------------
# _SnapIndicator — ghost overlay shown while dragging
# ---------------------------------------------------------------------------

class _SnapIndicator(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(58, 141, 255, 30))
        pen = QPen(QColor(58, 141, 255, 160))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        painter.end()


# ---------------------------------------------------------------------------
# DashboardGrid — absolute-positioned content area
# ---------------------------------------------------------------------------

class DashboardGrid(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(_CONTENT_W())
        self._items: list[dict] = []
        self._snap = _SnapIndicator(self)
        self._edit_mode = False
        self.resize(_CONTENT_W(), _CELL())

    @staticmethod
    def _cell_rect(row: int, col: int, rowspan: int = 1, colspan: int = 1) -> QRect:
        unit, gap, cell = _UNIT(), _GAP(), _CELL()
        return QRect(
            col * cell,
            row * cell,
            colspan * unit + max(0, colspan - 1) * gap,
            rowspan * unit + max(0, rowspan - 1) * gap,
        )

    @staticmethod
    def _nearest_cell(pos: QPoint, colspan: int = 1) -> tuple[int, int]:
        cell = _CELL()
        col = max(0, min(_CONTENT_COLS - colspan, round(pos.x() / cell)))
        row = max(0, round(pos.y() / cell))
        return row, col

    def _refresh_height(self) -> None:
        max_bottom = max((i['row'] + i['rowspan'] for i in self._items), default=1)
        self.resize(_CONTENT_W(), max_bottom * _CELL() + _GAP())

    def add_widget(self, widget: QWidget, row: int, col: int,
                   rowspan: int = 1, colspan: int = 1,
                   fixed: bool = False) -> None:
        widget.setParent(self)
        widget.setGeometry(self._cell_rect(row, col, rowspan, colspan))
        widget.show()
        self._items.append({'widget': widget, 'row': row, 'col': col,
                            'rowspan': rowspan, 'colspan': colspan,
                            'fixed': fixed})
        self._refresh_height()

    def _occupied_cells(self, exclude: QWidget | None = None) -> set[tuple[int, int]]:
        occupied: set[tuple[int, int]] = set()
        for i in self._items:
            if i['widget'] is exclude:
                continue
            for r in range(i['row'], i['row'] + i['rowspan']):
                for c in range(i['col'], i['col'] + i['colspan']):
                    occupied.add((r, c))
        return occupied

    def _find_nearest_free(self, row: int, col: int, rowspan: int, colspan: int,
                           exclude: QWidget | None = None) -> tuple[int, int]:
        occupied = self._occupied_cells(exclude)

        def fits(r: int, c: int) -> bool:
            if c < 0 or c + colspan > _CONTENT_COLS or r < 0:
                return False
            return all((r + dr, c + dc) not in occupied
                       for dr in range(rowspan) for dc in range(colspan))

        if fits(row, col):
            return row, col
        for radius in range(1, 60):
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    if fits(row + dr, col + dc):
                        return row + dr, col + dc
        return 0, 0

    def next_free_cell(self, rowspan: int = 1, colspan: int = 1) -> tuple[int, int]:
        occupied = self._occupied_cells()

        def fits(r: int, c: int) -> bool:
            if c + colspan > _CONTENT_COLS:
                return False
            return all((r + dr, c + dc) not in occupied
                       for dr in range(rowspan) for dc in range(colspan))

        for row in range(50):
            for col in range(_CONTENT_COLS):
                if fits(row, col):
                    return row, col
        return 0, 0

    def get_layout(self) -> list[dict]:
        return [
            {
                'type': type(i['widget']).__name__,
                'row': i['row'], 'col': i['col'],
                'rowspan': i['rowspan'], 'colspan': i['colspan'],
            }
            for i in self._items if not i.get('fixed')
        ]

    def restore_layout(self, layout: list[dict], window) -> None:
        for entry in layout:
            cls = get_widget_class(entry['type'])
            if cls is None:
                continue
            widget = cls(window=window)
            widget.refresh()
            if self._edit_mode:
                widget.set_edit_mode(True)
            row = entry['row']
            col = entry['col']
            # Migrate layouts saved before the lens was expanded to _LENS_ROWSPAN rows:
            # any widget that would overlap the lens area (col >= 1, row < _LENS_ROWSPAN)
            # is shifted down to the first safe row.
            if col >= 1 and row < _LENS_ROWSPAN:
                row = _LENS_ROWSPAN
            self.add_widget(widget, row, col,
                            entry['rowspan'], entry['colspan'])

    def remove_widget(self, widget: QWidget) -> None:
        self._items = [i for i in self._items if i['widget'] is not widget]
        widget.setParent(None)
        widget.deleteLater()
        self._refresh_height()

    def set_edit_mode(self, enabled: bool) -> None:
        self._edit_mode = enabled
        for item in self._items:
            if item.get('fixed'):
                continue
            w = item['widget']
            if hasattr(w, 'set_edit_mode'):
                w.set_edit_mode(enabled)
        if not enabled:
            self._snap.hide()

    def _on_drag_move(self, widget: QWidget) -> None:
        item = next((i for i in self._items if i['widget'] is widget), None)
        if not item:
            return
        row, col = self._nearest_cell(widget.pos(), item['colspan'])
        needed_h = (row + item['rowspan']) * _CELL() + _GAP()
        if needed_h > self.height():
            self.resize(_CONTENT_W(), needed_h)
        self._snap.setGeometry(self._cell_rect(row, col, item['rowspan'], item['colspan']))
        self._snap.show()
        self._snap.raise_()

    def _on_drag_release(self, widget: QWidget) -> None:
        item = next((i for i in self._items if i['widget'] is widget), None)
        if not item:
            return
        row, col = self._nearest_cell(widget.pos(), item['colspan'])
        row, col = self._find_nearest_free(row, col, item['rowspan'], item['colspan'],
                                           exclude=widget)
        item['row'], item['col'] = row, col
        target = self._cell_rect(row, col, item['rowspan'], item['colspan'])
        anim = QPropertyAnimation(widget, b'geometry', self)
        anim.setDuration(140)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setEndValue(target)
        anim.start()
        self._snap.hide()
        self._refresh_height()


# ---------------------------------------------------------------------------
# _PickerCard + WidgetPickerDialog
# ---------------------------------------------------------------------------

class _PickerCard(QFrame):
    def __init__(self, name: str, description: str,
                 on_click, featured: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_click = on_click
        self._featured = featured
        self.setFixedHeight(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)
        name_lbl = QLabel(name)
        name_font = QFont()
        name_font.setBold(True)
        name_font.setPointSize(11)
        name_lbl.setFont(name_font)
        name_lbl.setStyleSheet('font-size: 11pt;')
        name_lbl.setFixedWidth(160)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet('color: #8d98af; font-size: 11pt;')
        layout.addWidget(name_lbl)
        layout.addWidget(desc_lbl, stretch=1)
        self._set_style(False)

    def _set_style(self, hovered: bool) -> None:
        if self._featured:
            border = '#2dd4bf' if not hovered else '#4ee8d3'
            bg = '#131e35' if hovered else '#0f1a2e'
        else:
            border = '#2dd4bf' if hovered else '#2c364a'
            bg = '#151e30' if hovered else '#121828'
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: {'2px' if self._featured else '1px'} solid {border};
                border-radius: 12px;
            }}
        """)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._set_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._set_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


class WidgetPickerDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chosen_class: type | None = None
        self.setModal(True)
        self.setWindowTitle('Add Widget')
        self.setMinimumWidth(440)
        main_win = QApplication.activeWindow()
        if main_win is not None:
            self.setMaximumWidth(main_win.width())
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        title = QLabel('Choose a widget')
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet('font-size: 15pt;')
        layout.addWidget(title)
        sub = QLabel('Select the widget you want to add to your dashboard.')
        sub.setStyleSheet('color: #8d98af;')
        sub.setWordWrap(True)
        layout.addWidget(sub)
        cards_col = QVBoxLayout()
        cards_col.setSpacing(8)
        for cls in discover_widgets():
            cards_col.addWidget(_PickerCard(
                cls.NAME, cls.DESCRIPTION,
                lambda c=cls: self._pick(c),
            ))
        layout.addLayout(cards_col)
        cancel = QPushButton('Cancel')
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel, alignment=Qt.AlignmentFlag.AlignRight)

    def _pick(self, cls: type) -> None:
        self.chosen_class = cls
        self.accept()


# ---------------------------------------------------------------------------
# DashboardPage
# ---------------------------------------------------------------------------

def _circle_btn_style(font_size: int, active: bool = False) -> str:
    r = sc(32)
    if active:
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #4ee8d3, stop:0.5 #5dd1ff, stop:1 #2d52b2);
                color: #ffffff;
                font-size: {font_size}pt;
                font-weight: 700;
                border: {sc(2)}px solid rgba(255,255,255,0.45);
                border-radius: {r}px;
            }}
        """
    return f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #2dd4bf, stop:0.5 #38bdf8, stop:1 #1e3a8a);
            color: #ffffff;
            font-size: {font_size}pt;
            font-weight: 300;
            border: none;
            border-radius: {r}px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #4ee8d3, stop:0.5 #5dd1ff, stop:1 #2d52b2);
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #20a892, stop:0.5 #1f9fd0, stop:1 #142a68);
        }}
    """


_LENS_ROWSPAN = 3   # rows the fixed lens occupies; widgets must start at or below this

_DEFAULT_LAYOUT = [
    {'type': 'PortfolioVectorWidget',     'row': 3, 'col': 5,  'rowspan': 3, 'colspan': 6},
    {'type': 'PositionsListWidget',       'row': 3, 'col': 0,  'rowspan': 3, 'colspan': 5},
    {'type': 'TotalEquityWidget',         'row': 6, 'col': 0,  'rowspan': 2, 'colspan': 4},
    {'type': 'PortfolioVolatilityWidget', 'row': 6, 'col': 4,  'rowspan': 2, 'colspan': 4},
]


class DashboardPage(QWidget):
    def __init__(self, window: 'VectorMainWindow') -> None:
        super().__init__()
        self.window = window
        self._edit_mode = False
        self._last_refresh: datetime | None = None
        self._build_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._update_refresh_label)
        self._refresh_timer.start(30_000)
        self._update_refresh_label()

    def _build_ui(self) -> None:
        from vector.widget_types.lens import LensDisplay

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._dash_grid = DashboardGrid()

        self._add_btn = QPushButton('+')
        self._add_btn.setFixedSize(sc(64), sc(64))
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(_circle_btn_style(28))
        self._add_btn.clicked.connect(self._open_picker)

        self._edit_btn = QPushButton('Edit')
        self._edit_btn.setFixedSize(sc(64), sc(64))
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(_circle_btn_style(13))
        self._edit_btn.clicked.connect(self._toggle_edit_mode)

        self._dash_grid.add_widget(self._add_btn, row=0, col=0, fixed=True)
        self._dash_grid.add_widget(self._edit_btn, row=1, col=0, fixed=True)

        self._lens = LensDisplay(window=self.window, show_button=True)
        self._lens.open_lens_clicked.connect(self._navigate_to_lens)

        self._lens_wrapper = QWidget()
        lens_stack = QStackedLayout(self._lens_wrapper)
        lens_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        lens_stack.setContentsMargins(0, 0, 0, 0)
        lens_stack.addWidget(self._lens)

        self._lens_overlay = QLabel()
        self._lens_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lens_overlay.setTextFormat(Qt.TextFormat.RichText)
        self._lens_overlay.setText(
            '<div align="center" style="font-size:18pt;">\U0001F512</div>'
            '<div align="center" style="font-size:13pt; font-weight:700; color:#ffffff;">'
            'Get Vector Professional</div>'
        )
        self._lens_overlay.setStyleSheet(
            'QLabel { background-color: rgba(11, 16, 32, 140); border-radius: 16px; color: #ffffff; }'
        )
        self._lens_overlay.hide()
        lens_stack.addWidget(self._lens_overlay)

        self._dash_grid.add_widget(self._lens_wrapper, row=0, col=1, rowspan=_LENS_ROWSPAN, colspan=10, fixed=True)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._dash_grid)
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._refresh_label = QLabel('Not yet refreshed')
        self._refresh_label.setStyleSheet(
            'color: #8d98af; font-size: 9pt; padding: 2px 6px;'
        )
        self._refresh_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        outer.addWidget(self._refresh_label)

        outer.addWidget(self._scroll, stretch=1)

        saved = self.window.store.load_layout()
        layout = saved if saved else _DEFAULT_LAYOUT
        layout = [e for e in layout if e.get('type') != 'RecommendationWidget']
        self._dash_grid.restore_layout(layout, self.window)

    def _navigate_to_lens(self) -> None:
        shell = self.window.shell
        if shell:
            shell.set_page('Vector Lens')

    def apply_lens_gate(self, gated: bool) -> None:
        # Clear any blur on the outer widget so the card's painted border stays crisp.
        self._lens.setGraphicsEffect(None)
        card = getattr(self._lens, '_card', None)
        targets = list(card.findChildren(QWidget)) if card is not None else [self._lens]
        for child in targets:
            if gated:
                blur = QGraphicsBlurEffect(child)
                blur.setBlurRadius(50)
                child.setGraphicsEffect(blur)
            else:
                child.setGraphicsEffect(None)
        if gated:
            self._lens_overlay.show()
            self._lens_overlay.raise_()
        else:
            self._lens_overlay.hide()

    def save_layout(self) -> None:
        self.window.store.save_layout(self._dash_grid.get_layout())

    def _open_picker(self) -> None:
        dialog = WidgetPickerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.chosen_class:
            cls = dialog.chosen_class
            widget = cls(window=self.window)
            widget.refresh()
            if self._edit_mode:
                widget.set_edit_mode(True)
            row, col = self._dash_grid.next_free_cell(cls.DEFAULT_ROWSPAN, cls.DEFAULT_COLSPAN)
            self._dash_grid.add_widget(widget, row, col,
                                       rowspan=cls.DEFAULT_ROWSPAN,
                                       colspan=cls.DEFAULT_COLSPAN)

    def _toggle_edit_mode(self) -> None:
        self._edit_mode = not self._edit_mode
        self._dash_grid.set_edit_mode(self._edit_mode)
        self._edit_btn.setStyleSheet(_circle_btn_style(13, active=self._edit_mode))

    def update_dashboard(self, positions: list[dict[str, Any]], analytics: dict[str, Any]) -> None:
        self._lens.refresh()
        for item in self._dash_grid._items:
            w = item['widget']
            if hasattr(w, 'refresh'):
                w.refresh()
        self._last_refresh = datetime.now()
        self._update_refresh_label()

    def _update_refresh_label(self) -> None:
        if self._last_refresh is None:
            self._refresh_label.setText('Not yet refreshed')
            return
        delta = datetime.now() - self._last_refresh
        secs = int(delta.total_seconds())
        if secs < 60:
            text = 'Last updated: just now'
        elif secs < 3600:
            m = secs // 60
            text = f'Last updated: {m} minute{"s" if m != 1 else ""} ago'
        elif secs < 86400:
            h = secs // 3600
            text = f'Last updated: {h} hour{"s" if h != 1 else ""} ago'
        else:
            d = secs // 86400
            text = f'Last updated: {d} day{"s" if d != 1 else ""} ago'
        self._refresh_label.setText(text)
