from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QWidget
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PyQt6.QtCore import Qt, QRectF

from vector.widget_base import VectorWidget


_GREEN = '#4ade80'
_RED   = '#f87171'
_MUTED = '#8d98af'


class _SparklineFill(QWidget):
    """Full-width sparkline with a gradient fill beneath the line."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self._color = QColor(_GREEN)
        self.setFixedHeight(62)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_values(self, values: list[float], color: str = _GREEN) -> None:
        self._values = values
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)

        if len(self._values) < 2:
            return

        pad = 2.0
        rect = QRectF(pad, pad, self.width() - pad * 2, self.height() - pad * 2)

        low  = min(self._values)
        high = max(self._values)
        spread = max(high - low, 1e-9)
        step = rect.width() / max(len(self._values) - 1, 1)

        # Build point list + line path
        pts: list[tuple[float, float]] = []
        line = QPainterPath()
        for i, v in enumerate(self._values):
            x = rect.left() + i * step
            y = rect.bottom() - ((v - low) / spread) * rect.height()
            pts.append((x, y))
            if i == 0:
                line.moveTo(x, y)
            else:
                line.lineTo(x, y)

        # Fill path — close down to the bottom edge
        fill = QPainterPath(line)
        fill.lineTo(pts[-1][0], rect.bottom())
        fill.lineTo(pts[0][0],  rect.bottom())
        fill.closeSubpath()

        # Gradient fill: color → transparent
        grad = QLinearGradient(0.0, rect.top(), 0.0, rect.bottom())
        top_c = QColor(self._color); top_c.setAlpha(55)
        bot_c = QColor(self._color); bot_c.setAlpha(0)
        grad.setColorAt(0.0, top_c)
        grad.setColorAt(1.0, bot_c)

        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(fill)

        # Line on top
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._color, 2.0, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(line)


class TotalEquityWidget(VectorWidget):
    NAME = 'Total Equity'
    DESCRIPTION = 'Portfolio value with 5-day performance and sparkline.'
    DEFAULT_ROWSPAN = 2
    DEFAULT_COLSPAN = 4

    def __init__(self, window=None, parent=None) -> None:
        super().__init__(window=window, parent=parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(0)

        # ── Section descriptor ───────────────────────────────────────────
        title_lbl = QLabel('Total Equity')
        tf = QFont(); tf.setPointSize(16); tf.setBold(True)
        title_lbl.setFont(tf)
        title_lbl.setStyleSheet('font-size: 16pt; border: none;')
        layout.addWidget(title_lbl)

        layout.addSpacing(8)

        # ── Hero value ───────────────────────────────────────────────────
        self._value_lbl = QLabel('—')
        vf = QFont(); vf.setPointSize(15); vf.setBold(True)
        self._value_lbl.setFont(vf)
        self._value_lbl.setStyleSheet('font-size: 15pt; border: none;')
        layout.addWidget(self._value_lbl)

        layout.addSpacing(5)

        # ── Change row ───────────────────────────────────────────────────
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self._change_lbl = QLabel('')
        cf = QFont(); cf.setPointSize(11); cf.setBold(True)
        self._change_lbl.setFont(cf)
        self._change_lbl.setProperty('role', 'muted')
        self._change_lbl.setStyleSheet('font-size: 11pt; border: none;')
        row.addWidget(self._change_lbl)

        row.addStretch(1)

        self._period_lbl = QLabel('5-day change')
        self._period_lbl.setProperty('role', 'muted')
        self._period_lbl.setStyleSheet('font-size: 10pt; border: none;')
        self._period_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._period_lbl)

        layout.addLayout(row)

        layout.addSpacing(14)

        # ── Sparkline ────────────────────────────────────────────────────
        self._chart = _SparklineFill()
        layout.addWidget(self._chart)

    def refresh(self) -> None:
        if not self._window:
            return

        positions      = self._window.positions or []
        store          = self._window.store
        refresh_interval = self._window.settings.get('refresh_interval', '5 min')
        fmt            = self._window.format_currency

        if not positions:
            self._value_lbl.setText(fmt(0))
            self._value_lbl.setStyleSheet('font-size: 15pt; border: none;')
            self._change_lbl.setText('—')
            self._chart.set_values([])
            return

        # Build portfolio equity history from 5d/1h closes (~32 points)
        daily_totals: list[float] = []
        for pos in positions:
            try:
                closes = store.get_closes(pos['ticker'], '5d', '1h', refresh_interval)
            except Exception:  # noqa: BLE001
                closes = []
            shares = pos.get('shares', 0)
            if not closes:
                continue
            if not daily_totals:
                daily_totals = [shares * c for c in closes]
            else:
                n = min(len(daily_totals), len(closes))
                daily_totals = [daily_totals[i] + shares * closes[i] for i in range(n)]

        current_equity = sum(
            p.get('equity', p.get('shares', 0) * p.get('current_price', 0))
            for p in positions
        )

        if daily_totals:
            first, last = daily_totals[0], daily_totals[-1]
        else:
            first = last = current_equity

        change = last - first
        pct    = (change / first * 100) if first else 0.0
        color  = _GREEN if change >= 0 else _RED
        sign   = '+' if change >= 0 else ''

        self._value_lbl.setText(fmt(last if daily_totals else current_equity))
        self._value_lbl.setStyleSheet(f'color: {color}; font-size: 15pt; border: none;')

        self._change_lbl.setText(f'{sign}{fmt(change)}  {sign}{pct:.2f}%')
        self._change_lbl.setStyleSheet(f'color: {color}; font-size: 11pt; font-weight: 700; border: none;')

        self._chart.set_values(daily_totals if daily_totals else [current_equity], color)
