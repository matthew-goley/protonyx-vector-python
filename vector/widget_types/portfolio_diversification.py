from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QWidget, QSizePolicy
from PyQt6.QtGui import QFont, QColor, QPainter
from PyQt6.QtCore import Qt, QRectF

from vector.widget_base import VectorWidget

_MUTED = '#8d98af'
# Gradient-themed palette: solid picks inspired by the 3-key gradient
_PIE_COLORS = [
    '#2dd4bf',  # teal
    '#38bdf8',  # sky blue
    '#1e3a8a',  # navy
    '#54BFFF',  # light blue
    '#FF6B2B',  # orange
    '#4ade80',  # green
    '#f3b84b',  # amber
    '#f87171',  # red
    '#a5f3fc',  # pale cyan
    '#6ee7b7',  # light teal
]


def _title_font(size: int = 22) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(True)
    return f


class _DonutChart(QWidget):
    """Simple filled pie chart."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._slices: list[tuple[float, QColor]] = []  # (pct, color)
        self.setMinimumSize(100, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_slices(self, slices: list[tuple[float, str]]) -> None:
        self._slices = [(pct, QColor(c)) for pct, c in slices]
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self._slices:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height())
        x_off = (self.width() - side) / 2
        y_off = (self.height() - side) / 2
        margin = 6.0
        rect = QRectF(x_off + margin, y_off + margin, side - margin * 2, side - margin * 2)

        painter.setPen(Qt.PenStyle.NoPen)

        start_angle = 90 * 16  # top (Qt: 0 = 3 o'clock, angles in 1/16 deg)
        for pct, color in self._slices:
            span = int(round(pct / 100.0 * 360 * 16))
            if span == 0:
                continue
            painter.setBrush(color)
            painter.drawPie(rect, start_angle, -span)
            start_angle -= span

        painter.end()


class _LegendRow(QWidget):
    """Compact legend: colored dot + sector name + percentage."""

    def __init__(self, sector: str, pct: float, color: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(22)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        dot = QLabel('●')
        dot.setFixedWidth(12)
        dot.setStyleSheet(f'color: {color}; font-size: 8pt; border: none;')
        row.addWidget(dot)

        name = QLabel(sector)
        name.setStyleSheet(f'color: #e7ebf3; font-size: 9pt; border: none;')
        row.addWidget(name, stretch=1)

        pct_lbl = QLabel(f'{pct:.1f}%')
        pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        pct_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 9pt; font-weight: 700; border: none;')
        row.addWidget(pct_lbl)


class PortfolioDiversificationWidget(VectorWidget):
    NAME = 'Diversification'
    DESCRIPTION = 'Sector allocation breakdown with concentration insight.'
    DEFAULT_ROWSPAN = 3
    DEFAULT_COLSPAN = 4

    def __init__(self, window=None, parent=None) -> None:
        super().__init__(window=window, parent=parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        title_lbl = QLabel('Diversification')
        title_lbl.setFont(_title_font(16))
        title_lbl.setStyleSheet('color: #e7ebf3; font-size: 16pt; border: none;')
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._sector_count_lbl = QLabel('')
        self._sector_count_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11pt; border: none;')
        header.addWidget(self._sector_count_lbl)
        layout.addLayout(header)

        # Insight line
        self._insight_lbl = QLabel('')
        self._insight_lbl.setWordWrap(True)
        self._insight_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 9pt; border: none;')
        layout.addWidget(self._insight_lbl)

        # Content: donut (left) + legend (right)
        content = QHBoxLayout()
        content.setSpacing(12)

        self._donut = _DonutChart()
        content.addWidget(self._donut, stretch=3)

        self._legend_widget = QWidget()
        self._legend_widget.setStyleSheet('background: transparent;')
        self._legend_layout = QVBoxLayout(self._legend_widget)
        self._legend_layout.setContentsMargins(0, 0, 0, 0)
        self._legend_layout.setSpacing(2)
        content.addWidget(self._legend_widget, stretch=2)

        layout.addLayout(content, stretch=1)

    def refresh(self) -> None:
        if not self._window:
            return
        positions = self._window.positions or []

        # Clear legend
        while self._legend_layout.count():
            item = self._legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not positions:
            self._sector_count_lbl.setText('')
            self._insight_lbl.setText('Add positions to see allocation.')
            self._donut.set_slices([])
            self._legend_layout.addStretch(1)
            return

        # Build sector map weighted by equity
        total_equity = sum(p.get('equity', 0) for p in positions)
        sector_map: dict[str, float] = {}
        for p in positions:
            sector = p.get('sector') or 'Unknown'
            sector_map[sector] = sector_map.get(sector, 0.0) + p.get('equity', 0.0)

        allocation = sorted(sector_map.items(), key=lambda x: x[1], reverse=True)
        self._sector_count_lbl.setText(f'{len(allocation)} sector{"s" if len(allocation) != 1 else ""}')

        top_sector, top_equity = allocation[0] if allocation else ('', 0)
        top_pct = (top_equity / total_equity * 100) if total_equity else 0
        if top_pct >= 70:
            self._insight_lbl.setText(f'{top_pct:.0f}% concentrated in {top_sector} — consider diversifying.')
        elif top_pct >= 45:
            self._insight_lbl.setText(f'{top_pct:.0f}% in {top_sector} — moderate concentration.')
        else:
            self._insight_lbl.setText('Allocation is well spread across sectors.')

        slices: list[tuple[float, str]] = []
        for i, (sector, equity) in enumerate(allocation):
            pct = (equity / total_equity * 100) if total_equity else 0
            color = _PIE_COLORS[i % len(_PIE_COLORS)]
            slices.append((pct, color))
            self._legend_layout.addWidget(_LegendRow(sector, pct, color))

        self._legend_layout.addStretch(1)
        self._donut.set_slices(slices)
