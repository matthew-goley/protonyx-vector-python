from __future__ import annotations

from typing import Iterable

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


CARD_BACKGROUND = '#161b26'
BORDER_COLOR = '#2a3142'
TEXT_MUTED = '#7f8aa2'
ACCENT_COLORS = ['#2dd4bf', '#38bdf8', '#1e3a8a', '#FF6B2B', '#54BFFF', '#4ee8d3']


class CardFrame(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('cardFrame')
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)


class GradientBorderFrame(QFrame):
    """Frame with a teal-to-navy gradient border, used for the main header."""

    _RADIUS = 16.0
    _BORDER_W = 1.5

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect())
        r = self._RADIUS
        bw = self._BORDER_W

        app = QApplication.instance()
        is_dark = app is not None and '#0b1020' in (app.styleSheet() or '')
        bg = QColor('#0f1526' if is_dark else '#ffffff')

        bg_path = QPainterPath()
        bg_path.addRoundedRect(rect.adjusted(bw, bw, -bw, -bw), r - bw, r - bw)
        painter.fillPath(bg_path, bg)

        pen = QPen(QColor('#1e3a8a'), bw)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        border_path = QPainterPath()
        border_path.addRoundedRect(
            rect.adjusted(bw / 2, bw / 2, -bw / 2, -bw / 2), r, r
        )
        painter.drawPath(border_path)
        painter.end()


class GradientLine(QWidget):
    """Thin vertical line with a teal-to-navy gradient, used as the sidebar divider."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(2)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(QRectF(self.rect()), QColor('#1e3a8a'))
        painter.end()


class ArrowIndicator(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0.0
        self._color = QColor('#2dd4bf')
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_state(self, angle: float, color: str) -> None:
        self._angle = angle
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(24, 24, -24, -24)
        center = rect.center()
        painter.translate(center)
        painter.rotate(-self._angle)
        shaft_pen = QPen(self._color, 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(shaft_pen)
        painter.drawLine(-80, 0, 60, 0)
        arrow = QPolygonF([QPointF(60, 0), QPointF(25, -26), QPointF(25, 26)])
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(arrow)
        painter.setPen(QPen(QColor('#2a3142'), 2, Qt.PenStyle.DashLine))
        painter.drawArc(QRectF(-92, -92, 184, 184), 0, 180 * 16)


class SparklineWidget(QWidget):
    def __init__(self, values: Iterable[float] | None = None, color: str = '#2dd4bf', parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values = list(values or [])
        self._color = QColor(color)
        self.setMinimumHeight(42)
        self.setMinimumWidth(96)

    def set_values(self, values: Iterable[float], color: str) -> None:
        self._values = list(values)
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        available = self.rect().adjusted(4, 4, -4, -4)
        # Enforce 5:1 width:height aspect ratio cap on the drawing area
        draw_height = available.height()
        max_draw_width = draw_height * 5
        draw_width = min(available.width(), max_draw_width)
        x_offset = available.left() + (available.width() - draw_width) / 2.0
        rect = QRectF(x_offset, float(available.top()), draw_width, float(draw_height))
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        if len(self._values) < 2:
            painter.setPen(QPen(QColor(TEXT_MUTED), 1))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '—')
            return
        low = min(self._values)
        high = max(self._values)
        spread = max(high - low, 1e-6)
        step = rect.width() / max(len(self._values) - 1, 1)
        path = QPainterPath()
        for index, value in enumerate(self._values):
            x = rect.left() + index * step
            ratio = (value - low) / spread
            y = rect.bottom() - ratio * rect.height()
            if index == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.setPen(QPen(self._color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)


class PieChartWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._allocation: list[dict[str, float | str]] = []
        self.setMinimumHeight(220)

    def set_allocation(self, allocation: list[dict[str, float | str]]) -> None:
        self._allocation = allocation
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        chart_rect = QRectF(12, 12, min(self.width() * 0.5, 220), min(self.height() - 24, 220))
        total = sum(float(item['equity']) for item in self._allocation)
        if total <= 0:
            painter.setPen(QPen(QColor(TEXT_MUTED), 1))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'No allocation data yet')
            return
        start_angle = 0.0
        for index, item in enumerate(self._allocation):
            span = 360.0 * float(item['equity']) / total
            painter.setBrush(QColor(ACCENT_COLORS[index % len(ACCENT_COLORS)]))
            painter.setPen(QPen(QColor(CARD_BACKGROUND), 2))
            painter.drawPie(chart_rect, int(start_angle * 16), int(span * 16))
            start_angle += span
        legend_x = chart_rect.right() + 20
        for index, item in enumerate(self._allocation):
            top = 28 + index * 28
            painter.setBrush(QColor(ACCENT_COLORS[index % len(ACCENT_COLORS)]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(legend_x, top, 14, 14), 4, 4)
            painter.setPen(QColor('#e7ebf3'))
            painter.drawText(QRectF(legend_x + 22, top - 2, self.width() - legend_x - 28, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{item['sector']} — {float(item['percent']):.1f}%")


class EmptyState(QWidget):
    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(200)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet('font-size: 16pt;')
        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        subtitle_label.setMinimumHeight(40)
        subtitle_label.setStyleSheet(f'color: {TEXT_MUTED};')
        layout.addStretch(1)
        layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)


class DimOverlay(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._target = parent

    def sync_geometry(self) -> None:
        self.setGeometry(self._target.rect())

    def showEvent(self, event) -> None:  # noqa: N802
        self.sync_geometry()
        super().showEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(4, 8, 16, 165))


class BlurrableStack(QWidget):
    def __init__(self, inner: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.inner = inner
        self.blur = QGraphicsBlurEffect(self)
        self.blur.setBlurRadius(0)
        self.blur.setEnabled(False)
        self.inner.setGraphicsEffect(self.blur)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(inner)

    def set_blurred(self, blurred: bool) -> None:
        self.blur.setBlurRadius(10 if blurred else 0)
        self.blur.setEnabled(blurred)


class SpinnerWidget(QWidget):
    """A small animated spinning circle indicator."""

    def __init__(self, size: int = 18, color: str = '#e7ebf3', parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self._color = QColor(color)
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start(30)
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        if not hasattr(self, '_angle'):
            return
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        if not hasattr(self, '_angle') or not hasattr(self, '_color'):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        pen = QPen(QColor(self._color.red(), self._color.green(), self._color.blue(), 60), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(rect)
        arc_pen = QPen(self._color, 2.5)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(rect, int(self._angle * 16), int(90 * 16))


class LoadingButton(QPushButton):
    """QPushButton that shows an inline spinner while a long-running action executes."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._original_text = text
        self._spinner = SpinnerWidget(16, '#e7ebf3', self)
        self._spinner.hide()
        self._loading = False

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Position spinner to the left of center text area
        sx = 8
        sy = (self.height() - self._spinner.height()) // 2
        self._spinner.move(sx, sy)

    def start_loading(self, message: str = 'Loading...') -> None:
        self._loading = True
        self._original_text = self.text()
        self.setText(f'    {message}')
        self.setProperty('loading', True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setEnabled(False)
        self._spinner.start()

    def stop_loading(self, restore_text: str | None = None) -> None:
        self._loading = False
        self.setText(restore_text or self._original_text)
        self.setProperty('loading', False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setEnabled(True)
        self._spinner.stop()

    def is_loading(self) -> bool:
        return self._loading


class GradientLabel(QWidget):
    """A label that renders text with a horizontal gradient fill matching the Vector logo."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._font = QFont('Segoe UI', 14)
        self._font.setBold(True)
        self._font.setWeight(QFont.Weight.ExtraBold)
        metrics = QFontMetrics(self._font)
        self.setFixedHeight(metrics.height() + 4)
        self.setMinimumWidth(metrics.horizontalAdvance(text) + 8)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self._font)
        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(self._text)
        gradient = QLinearGradient(0, 0, text_width, 0)
        gradient.setColorAt(0.0, QColor('#2dd4bf'))
        gradient.setColorAt(0.5, QColor('#38bdf8'))
        gradient.setColorAt(1.0, QColor('#1e3a8a'))
        painter.setPen(QPen(gradient, 0))
        painter.drawText(0, metrics.ascent(), self._text)
