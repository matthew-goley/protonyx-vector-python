"""
Portfolio Vector widget — directional arrow + plain-language verdict.

The arrow always renders with the app's signature teal-to-navy gradient.
Direction is communicated through angle alone. A verdict sentence on the right
explains what the data means in plain terms, similar to the Lens display.
"""

import math

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from vector.analytics import classify_direction, linear_regression_slope_percent
from vector.widget_base import VectorWidget

_MUTED = '#8d98af'
_GRAD_START = '#2dd4bf'
_GRAD_MID   = '#38bdf8'
_GRAD_END   = '#1e3a8a'

# Plain-language verdicts per direction label.
# Picked deterministically by slope magnitude so the text is stable across refreshes.
_VERDICTS: dict[str, list[str]] = {
    'Strong': [
        "Your portfolio is building real momentum — the data projects continued appreciation if conditions hold.",
        "Strong upward trajectory across your holdings — current momentum suggests further gains ahead.",
        "Your investments are trending sharply upward — this is the profile of a portfolio in an active growth phase.",
    ],
    'Steady': [
        "Your investments are growing at a sustainable pace — the trend is healthy and consistent.",
        "A steady upward slope across your holdings — the kind of compounding that builds wealth quietly.",
        "Your portfolio is appreciating steadily — no noise, no drama, just consistent forward movement.",
    ],
    'Neutral': [
        "Your portfolio is moving sideways — no clear direction yet, but no warning signs either.",
        "Sideways movement across your holdings — the market is coiling, a directional move may be building.",
        "Your investments are holding flat — this is a waiting period, not a cause for concern.",
    ],
    'Depreciating': [
        "Your investments are showing signs of decline — a downward trend is forming across your holdings.",
        "The data shows a portfolio trending lower — the slope is negative and gradual losses are compounding.",
        "Your portfolio is drifting downward — not a crisis, but a trend worth addressing before it deepens.",
    ],
    'Weak': [
        "Your portfolio is under significant downward pressure — the data points to continued losses without a catalyst.",
        "A strong downtrend is visible across your holdings — this is the highest-risk profile in the direction spectrum.",
        "Your investments are declining sharply — the current trajectory demands attention and a clear response.",
    ],
}


def _font(size: int, bold: bool = True) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    return f


class _VectorArrow(QWidget):
    """
    Arrow spanning its width, tilted by angle degrees.
    Always renders with the app's teal-to-navy gradient — direction
    is read from the angle alone, not colour.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._angle = 0.0
        self.setMinimumHeight(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_angle(self, angle: float) -> None:
        self._angle = max(-70.0, min(70.0, angle))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        pad_x = 20.0
        mid_y = h / 2.0

        angle_rad = math.radians(self._angle)
        dy = math.sin(angle_rad) * (h * 0.58)

        # Centre the path vertically — start half-travel below mid, end half above.
        # This keeps the arrow fully within the widget at any angle.
        x0 = pad_x
        y0 = h / 2.0 + dy / 2.0
        x_end = w - pad_x - 34.0
        y_end = h / 2.0 - dy / 2.0

        # Control point: flat start, steepens toward end
        x_ctrl = x0 + (x_end - x0) * 0.65
        y_ctrl = y0

        path = QPainterPath()
        path.moveTo(x0, y0)
        path.quadTo(x_ctrl, y_ctrl, x_end, y_end)

        # --- glow (soft teal halo) ---
        glow = QColor(_GRAD_END)
        glow.setAlpha(35)
        painter.strokePath(path, QPen(glow, 22, Qt.PenStyle.SolidLine,
                                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

        # --- gradient shaft: 3-key gradient, left to right ---
        grad = QLinearGradient(x0, 0.0, x_end, 0.0)
        c_start = QColor(_GRAD_START)
        c_start.setAlpha(170)
        grad.setColorAt(0.0, c_start)
        grad.setColorAt(0.5, QColor(_GRAD_MID))
        grad.setColorAt(1.0, QColor(_GRAD_END))
        painter.strokePath(path, QPen(grad, 7, Qt.PenStyle.SolidLine,
                                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

        # --- arrowhead aligned to the end tangent ---
        tdx = x_end - x_ctrl
        tdy = y_end - y_ctrl
        tlen = math.hypot(tdx, tdy) or 1.0
        ux, uy = tdx / tlen, tdy / tlen
        px, py = -uy, ux

        head_len, head_half = 26.0, 12.0
        tip = QPointF(x_end + ux * 28.0, y_end + uy * 28.0)
        base_cx = x_end - ux * head_len
        base_cy = y_end - uy * head_len
        poly = QPolygonF([
            tip,
            QPointF(base_cx + px * head_half, base_cy + py * head_half),
            QPointF(base_cx - px * head_half, base_cy - py * head_half),
        ])
        painter.setBrush(QColor(_GRAD_END))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(poly)


class PortfolioVectorWidget(VectorWidget):
    NAME = 'Portfolio Vector'
    DESCRIPTION = 'Directional arrow showing the equity-weighted slope of your portfolio.'
    DEFAULT_ROWSPAN = 3
    DEFAULT_COLSPAN = 6

    def __init__(self, window=None, parent=None) -> None:
        super().__init__(window=window, parent=parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 16)
        outer.setSpacing(0)

        # ── Title ────────────────────────────────────────────────────────
        title_lbl = QLabel('Portfolio Vector')
        title_lbl.setFont(_font(16, bold=True))
        title_lbl.setStyleSheet('color: #e7ebf3; font-size: 16pt; border: none;')
        outer.addWidget(title_lbl)

        outer.addSpacing(2)

        # ── Direction label + slope ──────────────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._dir_lbl = QLabel('—')
        self._dir_lbl.setFont(_font(24))
        self._dir_lbl.setStyleSheet('font-size: 24pt; border: none;')
        stats_row.addWidget(self._dir_lbl)
        self._slope_lbl = QLabel('')
        self._slope_lbl.setFont(_font(24))
        self._slope_lbl.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
        self._slope_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 24pt; border: none;')
        stats_row.addWidget(self._slope_lbl)
        stats_row.addStretch(1)
        outer.addLayout(stats_row)

        outer.addSpacing(4)

        # ── Content row: arrow (left 60%) + verdict (right 40%) ──────────
        content = QHBoxLayout()
        content.setSpacing(24)

        self._arrow = _VectorArrow()
        content.addWidget(self._arrow, stretch=6)

        # Vertical divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet('color: #2a3347; background: #2a3347; border: none;')
        divider.setFixedWidth(1)
        content.addWidget(divider)

        self._verdict_lbl = QLabel('')
        self._verdict_lbl.setFont(_font(12, bold=False))
        self._verdict_lbl.setWordWrap(True)
        self._verdict_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._verdict_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 12pt; border: none;')
        content.addWidget(self._verdict_lbl, stretch=4)

        outer.addLayout(content, stretch=1)

        outer.addSpacing(4)

        # ── Sub-label ────────────────────────────────────────────────────
        self._sub_lbl = QLabel('6-month linear regression · equity-weighted')
        self._sub_lbl.setFont(_font(9, bold=False))
        self._sub_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 9pt; border: none;')
        outer.addWidget(self._sub_lbl)

    def refresh(self) -> None:
        if not self._window:
            return

        positions = self._window.positions or []
        store = self._window.store
        refresh_interval = self._window.settings.get('refresh_interval', '5 min')
        thresholds = self._window.settings.get('direction_thresholds', {
            'strong': 0.08, 'steady': 0.02,
            'neutral_low': -0.02, 'neutral_high': 0.02,
            'depreciating': -0.08,
        })

        if not positions:
            self._dir_lbl.setText('No Data')
            self._dir_lbl.setStyleSheet(f'color: {_MUTED}; font-size: 24pt; border: none;')
            self._slope_lbl.setText('')
            self._arrow.set_angle(0.0)
            self._verdict_lbl.setText('Add positions to see your portfolio direction.')
            return

        total_equity = sum(p.get('equity', 0) for p in positions)
        weighted_slope = 0.0

        for pos in positions:
            equity = pos.get('equity', 0.0)
            weight = equity / total_equity if total_equity else 0.0
            try:
                closes = store.get_history(pos['ticker'], '6mo', refresh_interval)
            except Exception:  # noqa: BLE001
                closes = []
            slope = linear_regression_slope_percent(closes)
            weighted_slope += slope * weight

        direction_label, color, arrow_angle = classify_direction(weighted_slope, thresholds)
        sign = '+' if weighted_slope >= 0 else ''

        # Pick verdict deterministically — stable across refreshes for the same portfolio
        sentences = _VERDICTS.get(direction_label, _VERDICTS['Neutral'])
        verdict = sentences[int(abs(weighted_slope) * 1000) % len(sentences)]

        self._dir_lbl.setText(direction_label)
        self._dir_lbl.setStyleSheet(f'color: {color}; font-size: 24pt; border: none;')
        self._slope_lbl.setText(f'{sign}{weighted_slope:.3f}%')
        self._slope_lbl.setStyleSheet(f'color: {color}; font-size: 24pt; border: none;')
        self._arrow.set_angle(arrow_angle)
        self._verdict_lbl.setText(verdict)
