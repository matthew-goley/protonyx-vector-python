from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt, QRect, QRectF, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .dashboard import _CONTENT_W

if TYPE_CHECKING:
    from vector.app import VectorMainWindow


_CAUTION_TIERS = [
    (25,  '#4ade80', 'Well balanced'),
    (50,  '#facc15', 'Manageable'),
    (75,  '#fb923c', 'Elevated risk'),
    (99,  '#ef4444', 'High caution'),
]

# Action type → indicator color
_ACTION_INDICATOR_COLORS: dict[str, str] = {
    'sell':      '#ff4d4d',
    'rebalance': '#ff9f43',
    'buy_new':   '#38bdf8',
    'buy_more':  '#38bdf8',
    'hold':      '#8d98af',
}


def _caution_color(score: int) -> str:
    for threshold, color, _ in _CAUTION_TIERS:
        if score <= threshold:
            return color
    return '#ef4444'


def _caution_label(score: int) -> str:
    for threshold, _, label in _CAUTION_TIERS:
        if score <= threshold:
            return label
    return 'High caution'


class _GaugeWidget(QWidget):
    """Semi-circular arc gauge displaying a score from 1–99."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._score = 0
        self.setMinimumSize(140, 110)

    def set_score(self, score: int) -> None:
        self._score = max(1, min(99, score))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        bottom_y = h - 12.0
        r = min(cx - 18.0, bottom_y - 8.0)
        if r < 20:
            painter.end()
            return

        rect = QRectF(cx - r, bottom_y - r, r * 2.0, r * 2.0)
        pen_w = max(8, int(r * 0.13))

        # Background arc — full semi-circle (left → top → right), clockwise
        from PyQt6.QtWidgets import QApplication as _QApp
        _app = _QApp.instance()
        _is_dark = _app is not None and '#0b1020' in (_app.styleSheet() or '')
        arc_bg = '#2a3142' if _is_dark else '#d8e2f0'
        bg_pen = QPen(QColor(arc_bg), pen_w, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 180 * 16, -180 * 16)

        # Fill arc — proportional to score
        if self._score > 0:
            span = int(-180 * (self._score / 100.0) * 16)
            fg_pen = QPen(QColor(_caution_color(self._score)), pen_w,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin)
            painter.setPen(fg_pen)
            painter.drawArc(rect, 180 * 16, span)

        # Score number inside arc
        f = QFont()
        f.setPointSize(max(16, int(r * 0.36)))
        f.setBold(True)
        painter.setFont(f)
        muted_gauge = '#8d98af' if _is_dark else '#536075'
        painter.setPen(QColor(_caution_color(self._score) if self._score > 0 else muted_gauge))
        text_rect = QRectF(cx - r * 0.85, bottom_y - r * 0.85, r * 1.7, r * 0.75)
        label = str(self._score) if self._score > 0 else '—'
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()


class _CautionCard(QFrame):
    """Left insight card — portfolio caution score gauge."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('cardFrame')
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)

        title = QLabel('Caution Score')
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet('font-size: 12pt; font-weight: 700;')
        layout.addWidget(title)

        self._gauge = _GaugeWidget()
        layout.addWidget(self._gauge, stretch=1)

        self._tier_lbl = QLabel('—')
        self._tier_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tier_lbl.setStyleSheet('font-size: 13pt; font-weight: 700;')
        layout.addWidget(self._tier_lbl)

        self._sub_lbl = QLabel('Based on current portfolio state')
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_lbl.setProperty('role', 'muted')
        self._sub_lbl.setStyleSheet('font-size: 9pt;')
        layout.addWidget(self._sub_lbl)

    def set_score(self, score: int) -> None:
        self._gauge.set_score(score)
        label = _caution_label(score) if score > 0 else '—'
        from PyQt6.QtWidgets import QApplication as _QApp
        _app = _QApp.instance()
        _muted = '#8d98af' if (_app and '#0b1020' in (_app.styleSheet() or '')) else '#536075'
        color = _caution_color(score) if score > 0 else _muted
        self._tier_lbl.setText(label)
        self._tier_lbl.setStyleSheet(f'font-size: 13pt; font-weight: 700; color: {color};')


class _MCContextCard(QFrame):
    """
    Right insight card — explains what the projected graph represents.
    Uses the same typewriter animation and auto-sizing font as LensDisplay.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('cardFrame')
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        # Typewriter state
        self._tw_timer = QTimer(self)
        self._tw_timer.setInterval(5)
        self._tw_timer.timeout.connect(self._tw_step)
        self._tw_plain = ''
        self._tw_html  = ''
        self._tw_pos   = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = QLabel('What the Lens Projection shows')
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet('font-size: 12pt; font-weight: 700;')
        layout.addWidget(title)

        self._body = QLabel('')
        self._body.setWordWrap(True)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._body.setProperty('role', 'muted')
        self._body.setStyleSheet('font-size: 13pt; border: none;')
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._body, stretch=1)

    # ── Size helpers ──────────────────────────────────────────────────────

    def _available_size(self) -> tuple[int, int]:
        w = self._body.width()
        h = self._body.height()
        if w >= 20 and h >= 20:
            return w, h
        return max(self.width() - 40, 200), max(self.height() - 60, 60)

    def _make_font(self, pt: int) -> QFont:
        f = QFont()
        f.setPointSize(pt)
        f.setBold(False)
        return f

    def _fit_pt(self, text: str) -> int:
        """Largest pt size where the plain text fits without clipping."""
        w, h = self._available_size()
        for pt in range(24, 9, -1):
            fm = QFontMetrics(self._make_font(pt))
            br = fm.boundingRect(
                QRect(0, 0, w, 10000),
                Qt.TextFlag.TextWordWrap,
                text,
            )
            if br.height() <= int(h * 0.85):
                return pt
        return 10

    def _apply_font(self, pt: int) -> None:
        self._body.setStyleSheet(
            f'font-size: {pt}pt; border: none;'
        )

    def _refit(self) -> None:
        if not self._tw_plain:
            return
        pt = self._fit_pt(self._tw_plain)
        self._apply_font(pt)
        if not self._tw_timer.isActive():
            self._body.setTextFormat(Qt.TextFormat.RichText)
            self._body.setText(self._tw_html)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._refit()
        super().resizeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._refit)

    # ── Typewriter machinery ──────────────────────────────────────────────

    @staticmethod
    def _truncate_html(html: str, visible_chars: int) -> str:
        """Truncate HTML to the first N visible characters, preserving open tags."""
        import re
        result: list[str] = []
        shown = 0
        i = 0
        open_tags: list[str] = []
        while i < len(html) and shown < visible_chars:
            if html[i] == '<':
                end = html.find('>', i)
                if end == -1:
                    break
                tag = html[i:end + 1]
                result.append(tag)
                if not tag.startswith('</'):
                    m = re.match(r'<(\w+)', tag)
                    if m:
                        open_tags.append(m.group(1))
                else:
                    if open_tags:
                        open_tags.pop()
                i = end + 1
            elif html[i] == '&':
                end = html.find(';', i)
                if end == -1:
                    result.append(html[i])
                    shown += 1
                    i += 1
                else:
                    result.append(html[i:end + 1])
                    shown += 1
                    i = end + 1
            else:
                result.append(html[i])
                shown += 1
                i += 1
        for tag in reversed(open_tags):
            result.append(f'</{tag}>')
        return ''.join(result)

    def _tw_step(self) -> None:
        self._tw_pos += 1
        truncated = self._truncate_html(self._tw_html, self._tw_pos)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setText(truncated)
        if self._tw_pos >= len(self._tw_plain):
            self._tw_timer.stop()

    def _start_typewrite(self, text: str) -> None:
        from vector.widget_types.lens import _highlight_html
        self._tw_timer.stop()
        self._tw_plain = text
        self._tw_html  = _highlight_html(text)
        self._tw_pos   = 0
        pt = self._fit_pt(text)
        self._apply_font(pt)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setText('')
        self._tw_timer.start()

    # ── Public API ────────────────────────────────────────────────────────

    def set_multi_cta_context(
        self,
        ctas: list[dict],
        net_delta: float,
        fan_spread_a: float | None = None,
        fan_spread_b: float | None = None,
    ) -> None:
        actionable = [c for c in ctas if c.get('action') != 'hold']
        if not actionable:
            self._start_typewrite(
                'No active projections right now. Both graphs use '
                'your current portfolio composition.'
            )
            return

        sell_dollars = sum(
            c['dollars'] for c in actionable if c['action'] in ('sell', 'rebalance')
        )
        buy_dollars = sum(
            c['dollars'] for c in actionable if c['action'] in ('buy_new', 'buy_more')
        )
        n = len(actionable)
        parts: list[str] = []

        if sell_dollars > 0 and buy_dollars > 0:
            parts.append(
                f'Graph B applies {n} projection{"s" if n != 1 else ""} '
                f'— selling ${sell_dollars:,.0f} and adding ${buy_dollars:,.0f} '
                f'— for a net {"deposit" if net_delta >= 0 else "reduction"} '
                f'of ${abs(net_delta):,.0f}.'
            )
        elif sell_dollars > 0:
            parts.append(
                f'Graph B reflects trimming ${sell_dollars:,.0f} from the '
                f'portfolio across {n} projection{"s" if n != 1 else ""}. '
                f'The projection starts from a lower base but with a '
                f'potentially more stable composition.'
            )
        else:
            parts.append(
                f'Graph B adds ${buy_dollars:,.0f} across {n} '
                f'projection{"s" if n != 1 else ""}. '
                f'The wider or narrower fan reflects how the new composition '
                f'changes the portfolio\'s volatility profile.'
            )

        # Fan-width comparison: call out tighter B if meaningful
        if (
            fan_spread_a is not None
            and fan_spread_b is not None
            and fan_spread_a > 0
            and fan_spread_b < fan_spread_a * 0.95
        ):
            reduction_pct = (fan_spread_a - fan_spread_b) / fan_spread_a * 100
            parts.append(
                f'Graph B\'s projection fan is {reduction_pct:.0f}% tighter than Graph A '
                f'— the lens projections reduce portfolio risk by approximately {reduction_pct:.0f}%.'
            )

        self._start_typewrite(' '.join(parts))

    def clear(self) -> None:
        self._start_typewrite(
            'The projection fan above reflects this portfolio\'s historical volatility profile.'
        )


class _GraphCard(QFrame):
    """
    Card widget containing a title label and a lazy matplotlib projection graph.
    The canvas is created on first call to plot() to avoid importing matplotlib
    at startup.
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('cardFrame')
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(16, 16, 16, 12)
        self._outer.setSpacing(10)

        self._title_lbl = QLabel(title)
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        self._title_lbl.setFont(f)
        self._title_lbl.setStyleSheet('font-size: 12pt; font-weight: 700;')
        self._title_lbl.setWordWrap(True)
        self._outer.addWidget(self._title_lbl)

        self._placeholder = QLabel('Loading projection…')
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setProperty('role', 'muted')
        self._placeholder.setStyleSheet('font-size: 11pt;')
        self._placeholder.setMinimumHeight(280)
        self._outer.addWidget(self._placeholder, stretch=1)

        self._canvas = None
        self._ax = None
        self._fig = None

    def set_title(self, title: str) -> None:
        self._title_lbl.setText(title)

    def _ensure_canvas(self) -> None:
        if self._canvas is not None:
            return
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        from PyQt6.QtWidgets import QApplication as _QApp
        _app = _QApp.instance()
        _is_dark = _app is not None and '#0b1020' in (_app.styleSheet() or '')
        self._is_dark = _is_dark
        self._fig = Figure(facecolor='#161b26' if _is_dark else '#f8faff')
        self._fig.subplots_adjust(left=0.06, right=0.88, top=0.90, bottom=0.22)
        self._ax = self._fig.add_subplot(111)
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._canvas.setMinimumHeight(320)
        # Pass scroll events up to the parent QScrollArea instead of consuming them
        self._canvas.wheelEvent = lambda event: event.ignore()
        self._placeholder.hide()
        self._outer.addWidget(self._canvas, stretch=1)

    def show_no_data(self, msg: str = 'Insufficient data for projection') -> None:
        self._placeholder.setText(msg)
        self._placeholder.show()
        if self._canvas is not None:
            self._canvas.hide()

    def plot(
        self,
        hist_days: list[int],
        hist_values: list[float],
        future_days: list[int],
        bands: dict,
        median: Any,
        fan_color: str = '#2dd4bf',
        ylim: tuple[float, float] | None = None,
    ) -> None:
        """Draw historical curve + Monte Carlo fan on the embedded axes."""
        import numpy as np
        from matplotlib.ticker import FuncFormatter

        self._ensure_canvas()
        if self._canvas is not None:
            self._canvas.show()
        self._placeholder.hide()

        ax = self._ax
        ax.clear()

        # --- Normalisation base: today = 0% ---
        today_value = float(median[0]) if median is not None and len(median) else (
            hist_values[-1] if hist_values else 1.0
        )
        if today_value <= 0:
            today_value = 1.0

        def to_pct(v: float | np.ndarray) -> float | np.ndarray:
            return (np.asarray(v, dtype=float) / today_value - 1.0) * 100.0

        _is_dark = getattr(self, '_is_dark', True)
        _ax_bg     = '#121828' if _is_dark else '#f0f4fb'
        _muted_ch  = '#8d98af' if _is_dark else '#536075'
        _grid_ch   = '#2a3142' if _is_dark else '#dde4f0'
        ax.set_facecolor(_ax_bg)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(axis='both', colors=_muted_ch, labelsize=8)
        ax.grid(True, color=_grid_ch, alpha=0.5, linewidth=0.5, zorder=0)

        ax.yaxis.tick_right()
        ax.yaxis.set_label_position('right')

        if hist_days and hist_values:
            ax.plot(
                list(hist_days) + [0],
                list(to_pct(np.array(hist_values))) + [0.0],
                color='#2dd4bf', lw=1.5, zorder=3,
            )

        ax.axvline(x=0, color=_muted_ch, lw=1.0, ls='--', alpha=0.55, zorder=2)

        if bands and future_days:
            alphas = {(10, 90): 0.12, (25, 75): 0.22, (40, 60): 0.35}
            fd = np.array(future_days)
            for band_key in [(10, 90), (25, 75), (40, 60)]:
                if band_key in bands:
                    lo_arr, hi_arr = bands[band_key]
                    ax.fill_between(
                        fd, to_pct(lo_arr), to_pct(hi_arr),
                        alpha=alphas[band_key], color=fan_color, zorder=1,
                        linewidth=0,
                    )
            if median is not None:
                ax.plot(
                    fd, to_pct(np.asarray(median, dtype=float)),
                    color=fan_color, lw=1.5, ls='--', alpha=0.9, zorder=3,
                )

        def _fmt(v: float, _pos: int) -> str:
            return f'{v:+.1f}%' if v != 0 else '0%'

        ax.yaxis.set_major_formatter(FuncFormatter(_fmt))

        xticks = [0, 21, 42, 63, 84, 105]
        xlabels = ['Today', '1m', '2m', '3m', '4m', '5m']
        ax.set_xticks(xticks)
        ax.set_xticklabels(xlabels, color=_muted_ch, fontsize=8)

        if ylim is not None:
            ax.set_ylim(*ylim)

        self._canvas.draw()


class _PieCard(QFrame):
    """Card widget containing a title label and a donut pie chart with legend."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('cardFrame')
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(16, 16, 16, 12)
        self._outer.setSpacing(10)

        self._title_lbl = QLabel(title)
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        self._title_lbl.setFont(f)
        self._title_lbl.setStyleSheet('font-size: 12pt; font-weight: 700;')
        self._title_lbl.setWordWrap(True)
        self._outer.addWidget(self._title_lbl)

        self._placeholder = QLabel('Add positions to see allocation.')
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setProperty('role', 'muted')
        self._placeholder.setStyleSheet('font-size: 11pt;')
        self._placeholder.setMinimumHeight(240)
        self._outer.addWidget(self._placeholder, stretch=1)

        self._content = QWidget()
        self._content.setStyleSheet('background: transparent;')
        content_layout = QHBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        from vector.widget_types.portfolio_diversification import _DonutChart
        self._donut = _DonutChart()
        self._donut.setMinimumHeight(220)
        content_layout.addWidget(self._donut, stretch=3)

        self._legend_widget = QWidget()
        self._legend_widget.setStyleSheet('background: transparent;')
        self._legend_layout = QVBoxLayout(self._legend_widget)
        self._legend_layout.setContentsMargins(0, 0, 0, 0)
        self._legend_layout.setSpacing(2)
        content_layout.addWidget(self._legend_widget, stretch=2)

        self._outer.addWidget(self._content, stretch=1)
        self._content.hide()

    def set_title(self, title: str) -> None:
        self._title_lbl.setText(title)

    def show_empty(self, msg: str = 'No data.') -> None:
        self._content.hide()
        self._placeholder.setText(msg)
        self._placeholder.show()

    def refresh(self, sector_map: dict) -> None:
        from vector.widget_types.portfolio_diversification import _LegendRow, _PIE_COLORS

        while self._legend_layout.count():
            item = self._legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not sector_map:
            self.show_empty()
            return

        self._placeholder.hide()
        self._content.show()

        total = sum(sector_map.values()) or 1.0
        allocation = sorted(sector_map.items(), key=lambda x: x[1], reverse=True)

        slices: list[tuple[float, str]] = []
        for i, (sector, equity) in enumerate(allocation):
            pct = equity / total * 100
            color = _PIE_COLORS[i % len(_PIE_COLORS)]
            slices.append((pct, color))
            self._legend_layout.addWidget(_LegendRow(sector, pct, color))

        self._legend_layout.addStretch(1)
        self._donut.set_slices(slices)


class _CTAReportCard(QFrame):
    """Card displaying all CTA recommendations with action-type indicators."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('cardFrame')
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(20, 16, 20, 16)
        self._outer.setSpacing(10)

        title = QLabel('All Projections')
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet('font-size: 12pt; font-weight: 700;')
        self._outer.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')

        # Wheel handler: only consume wheel when there is actually something
        # to scroll; otherwise let the event bubble up to the outer page.
        def _wheel(event, scroll=self._scroll):
            if scroll.verticalScrollBar().maximum() == 0:
                event.ignore()
            else:
                QScrollArea.wheelEvent(scroll, event)
        self._scroll.wheelEvent = _wheel

        self._items_container = QWidget()
        self._items_container.setStyleSheet('background: transparent;')
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setContentsMargins(0, 0, 0, 4)
        self._items_layout.setSpacing(4)
        self._scroll.setWidget(self._items_container)
        self._outer.addWidget(self._scroll)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # Default minimal height until first refresh
        self._scroll.setFixedHeight(80)

    def set_report(self, full_report: list[str], ctas: list[dict]) -> None:
        # Clear existing items
        while self._items_layout.count():
            item = self._items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not full_report:
            lbl = QLabel('No projections at this time.')
            lbl.setProperty('role', 'muted')
            lbl.setStyleSheet('font-size: 10pt;')
            self._items_layout.addWidget(lbl)
            self._scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            self._scroll.setFixedHeight(lbl.sizeHint().height() + 24)
            return

        _ACTION_LABELS: dict[str, str] = {
            'sell': 'SELL',
            'rebalance': 'REBALANCE',
            'buy_new': 'BUY',
            'buy_more': 'BUY MORE',
            'hold': 'HOLD',
        }

        cards: list[QFrame] = []
        for i, sentence in enumerate(full_report):
            cta = ctas[i] if i < len(ctas) else {}
            action = cta.get('action', 'hold')
            color = _ACTION_INDICATOR_COLORS.get(action, '#8d98af')
            action_label = _ACTION_LABELS.get(action, 'HOLD')

            # Build tag text with dollar amount
            dollars = cta.get('dollars', 0.0)
            if dollars and action in ('sell', 'rebalance'):
                tag_text = f'{action_label}  -${dollars:,.0f}'
            elif dollars and action in ('buy_new', 'buy_more'):
                tag_text = f'{action_label}  +${dollars:,.0f}'
            else:
                tag_text = action_label

            card = QFrame()
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            card.setStyleSheet(
                'QFrame {'
                ' background-color: #1a2035;'
                f' border: 1px solid {color}40;'
                f' border-left: 3px solid {color};'
                ' border-radius: 6px;'
                ' }'
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 4, 10, 4)
            card_layout.setSpacing(2)

            tag = QLabel(tag_text)
            tag.setContentsMargins(0, 0, 0, 0)
            tag.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
            tag.setStyleSheet(
                'QLabel {'
                ' font-size: 10pt;'
                ' font-weight: 700;'
                f' color: {color};'
                ' background: transparent;'
                ' border: none;'
                ' }'
            )
            tag_fm = QFontMetrics(tag.font())
            tag.setFixedHeight(tag_fm.ascent() + 2)
            card_layout.addWidget(tag)

            text = QLabel(sentence)
            text.setWordWrap(True)
            text.setContentsMargins(0, 0, 0, 0)
            text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            text.setStyleSheet(
                'QLabel {'
                ' font-size: 20pt;'
                ' color: #e7ebf3;'
                ' background: transparent;'
                ' border: none;'
                ' }'
            )
            card_layout.addWidget(text)

            self._items_layout.addWidget(card, 0)
            cards.append(card)

        self._items_layout.addStretch(1)

        # Recompute height after layout settles (word-wrap needs a real width).
        QTimer.singleShot(0, lambda: self._resize_for_cards(cards))

    def _resize_for_cards(self, cards: list[QFrame]) -> None:
        if not cards:
            return

        MAX_HEIGHT = 750
        PADDING = 24

        self._items_container.adjustSize()
        self._items_layout.activate()
        self._items_container.layout().activate()

        actual_content_height = self._items_container.sizeHint().height()

        if actual_content_height + PADDING <= MAX_HEIGHT:
            self._scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            self._scroll.setFixedHeight(actual_content_height + PADDING)
        else:
            self._scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded,
            )
            self._scroll.setFixedHeight(MAX_HEIGHT)


class _LensHistoryDialog(QDialog):
    """Modal showing the rolling Lens snapshot history (most recent first)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle('Lens History')
        self.resize(700, 600)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel('Lens History')
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet('font-size: 15pt; font-weight: 700;')
        layout.addWidget(title)

        sub = QLabel(
            'Rolling record of your last 50 Lens readings, newest first.'
        )
        sub.setStyleSheet('color: #8d98af;')
        sub.setWordWrap(True)
        layout.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')

        items_container = QWidget()
        items_container.setStyleSheet('background: transparent;')
        items_layout = QVBoxLayout(items_container)
        items_layout.setContentsMargins(0, 0, 0, 0)
        items_layout.setSpacing(10)

        snapshots = _load_history_snapshots()
        if not snapshots:
            empty = QLabel(
                'No snapshots yet — the Lens will save its readings as you '
                'use the app.'
            )
            empty.setStyleSheet('color: #8d98af; font-size: 11pt;')
            empty.setWordWrap(True)
            items_layout.addWidget(empty)
        else:
            for snap in reversed(snapshots):
                items_layout.addWidget(_LensHistoryCard(snap))

        items_layout.addStretch(1)
        scroll.setWidget(items_container)
        layout.addWidget(scroll, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        clear_btn = QPushButton('Clear History')
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._on_clear_history)
        btn_row.addWidget(clear_btn)

        btn_row.addStretch(1)

        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _on_clear_history(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        import json
        from vector.paths import user_file

        confirm = QMessageBox.question(
            self,
            'Clear Lens History',
            'Delete all saved Lens snapshots? This cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        path = user_file('lens_history.json')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'snapshots': []}, f)
        except Exception:
            pass

        self.accept()


class _LensHistoryCard(QFrame):
    """Single snapshot card inside the history modal."""

    def __init__(self, snapshot: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('cardFrame')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)

        score = int(snapshot.get('caution_score', 0) or 0)
        badge = _CautionBadge(score)
        header.addWidget(badge)

        ts_text = _format_relative_timestamp(snapshot.get('timestamp', ''))
        ts_lbl = QLabel(ts_text)
        ts_f = QFont()
        ts_f.setBold(True)
        ts_lbl.setFont(ts_f)
        ts_lbl.setStyleSheet('font-size: 10pt; font-weight: 700;')
        header.addWidget(ts_lbl)
        header.addStretch(1)
        layout.addLayout(header)

        brief = QLabel(snapshot.get('brief', '') or '—')
        brief.setWordWrap(True)
        brief.setStyleSheet('font-size: 10pt; line-height: 1.3;')
        layout.addWidget(brief)

        cta_count = int(snapshot.get('cta_count', 0) or 0)
        total_eq = float(snapshot.get('total_equity', 0) or 0)
        foot = QLabel(
            f'{cta_count} projection{"s" if cta_count != 1 else ""} • '
            f'portfolio ${total_eq:,.0f}'
        )
        foot.setStyleSheet('font-size: 9pt; color: #8d98af;')
        layout.addWidget(foot)


class _CautionBadge(QWidget):
    """Small colored circle showing the caution score."""

    def __init__(self, score: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._score = max(1, min(99, score)) if score else 0
        self.setFixedSize(32, 32)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = _caution_color(self._score) if self._score > 0 else '#8d98af'
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self.width(), self.height())
        painter.setPen(QColor('#ffffff'))
        f = QFont()
        f.setPointSize(9)
        f.setBold(True)
        painter.setFont(f)
        label = str(self._score) if self._score > 0 else '—'
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, label)
        painter.end()


def _load_history_snapshots() -> list[dict]:
    import json
    from vector.paths import user_file
    path = user_file('lens_history.json')
    if not path.exists():
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('snapshots', []) or []
    except Exception:
        return []


def _format_relative_timestamp(iso_ts: str) -> str:
    from datetime import datetime
    if not iso_ts:
        return 'Unknown time'
    try:
        when = datetime.fromisoformat(iso_ts)
    except ValueError:
        return iso_ts
    delta = datetime.now() - when
    secs = int(delta.total_seconds())
    if secs < 60:
        return 'Just now'
    if secs < 3600:
        m = secs // 60
        return f'{m} minute{"s" if m != 1 else ""} ago'
    if secs < 86400:
        h = secs // 3600
        return f'{h} hour{"s" if h != 1 else ""} ago'
    if secs < 7 * 86400:
        d = secs // 86400
        return f'{d} day{"s" if d != 1 else ""} ago'
    return when.strftime('%b %d, %Y — %I:%M %p').lstrip('0').replace(' 0', ' ')


class VectorLensPage(QWidget):
    """Dedicated page for Vector Lens — projection graphs and pie charts."""

    def __init__(self, window: 'VectorMainWindow') -> None:
        super().__init__()
        self.window = window
        self._lens_result: dict[str, Any] = {}
        self._fan_spread_a: float | None = None
        self._fan_spread_b: float | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        from vector.widget_types.lens import LensDisplay

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setFixedWidth(_CONTENT_W())
        self._container_layout = QVBoxLayout(container)
        self._container_layout.setContentsMargins(0, 8, 0, 24)
        self._container_layout.setSpacing(16)

        history_row = QHBoxLayout()
        history_row.setContentsMargins(0, 0, 0, 0)
        history_row.addStretch(1)
        history_btn = QPushButton('History')
        history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        history_btn.setFixedHeight(32)
        history_btn.setStyleSheet(
            'QPushButton { padding: 4px 14px; border-radius: 10px; font-size: 10pt; }'
        )
        history_btn.clicked.connect(self._open_history)
        history_row.addWidget(history_btn)
        self._container_layout.addLayout(history_row)

        self._lens = LensDisplay(window=self.window, show_button=False)
        self._lens.setFixedHeight(200)
        self._container_layout.addWidget(self._lens)

        # Row 2: Caution Score (left, narrow) + All Projections (right, wide)
        self._cta_report = _CTAReportCard()
        self._cta_report.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred,
        )
        self._caution_card = _CautionCard()
        self._caution_card.setMinimumHeight(210)
        self._caution_card.setFixedWidth(340)

        caution_projections_row = QWidget()
        caution_projections_layout = QHBoxLayout(caution_projections_row)
        caution_projections_layout.setContentsMargins(0, 0, 0, 0)
        caution_projections_layout.setSpacing(16)
        caution_projections_layout.addWidget(
            self._caution_card, 0, Qt.AlignmentFlag.AlignTop,
        )
        caution_projections_layout.addWidget(self._cta_report, 1)
        self._container_layout.addWidget(caution_projections_row)

        # Row 3: Graph A + Graph B
        graphs_row = QWidget()
        graphs_layout = QHBoxLayout(graphs_row)
        graphs_layout.setContentsMargins(0, 0, 0, 0)
        graphs_layout.setSpacing(16)
        self._graph_a = _GraphCard('Current Portfolio')
        self._graph_b = _GraphCard('With All Lens Projections')
        graphs_layout.addWidget(self._graph_a)
        graphs_layout.addWidget(self._graph_b)
        self._container_layout.addWidget(graphs_row)

        # Row 4: MC context card — full width, alone
        self._mc_context_card = _MCContextCard()
        self._mc_context_card.setMinimumHeight(210)
        self._container_layout.addWidget(self._mc_context_card)

        pies_row = QWidget()
        pies_layout = QHBoxLayout(pies_row)
        pies_layout.setContentsMargins(0, 0, 0, 0)
        pies_layout.setSpacing(16)
        self._pie_a = _PieCard('Current Allocation')
        self._pie_b = _PieCard('Projected Allocation')
        pies_layout.addWidget(self._pie_a)
        pies_layout.addWidget(self._pie_b)
        self._container_layout.addWidget(pies_row)

        self._container_layout.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll, stretch=1)

    def _open_history(self) -> None:
        dialog = _LensHistoryDialog(self)
        dialog.exec()

    def refresh(self) -> None:
        from vector.lens_engine import generate_lens_full

        # Run the full Lens pipeline once
        positions = self.window.positions or []
        store = self.window.store
        settings = self.window.settings

        self._lens_result = generate_lens_full(positions, store, settings)

        # Refresh the brief display (still uses the 7-tuple path internally)
        self._lens.refresh()

        # Update all sections from the full result
        self._update_cta_report()
        self._update_graphs()
        self._update_insights()
        self._update_pies()

    def _update_cta_report(self) -> None:
        full_report = self._lens_result.get('full_report', [])
        ctas = self._lens_result.get('ctas', [])
        self._cta_report.set_report(full_report, ctas)

    def _update_insights(self) -> None:
        caution = self._lens_result.get('caution_score', 0)
        self._caution_card.set_score(caution)

        ctas = self._lens_result.get('ctas', [])
        net_delta = self._lens_result.get('net_cta_delta', 0.0)
        self._mc_context_card.set_multi_cta_context(
            ctas, net_delta,
            fan_spread_a=self._fan_spread_a,
            fan_spread_b=self._fan_spread_b,
        )

    def _update_graphs(self) -> None:
        from vector.monte_carlo import build_historical_curve, run_projection

        positions = self.window.positions or []
        store = self.window.store
        settings = self.window.settings
        refresh_interval = settings.get('refresh_interval', '5 min')

        if not positions:
            self._graph_a.show_no_data('Add positions to see projections.')
            self._graph_b.show_no_data('Add positions to see projections.')
            return

        total_equity = sum(p.get('equity', 0.0) for p in positions) or 1.0
        tickers = [p['ticker'] for p in positions]
        weights = [p.get('equity', 0.0) / total_equity for p in positions]

        hist_days, hist_values = build_historical_curve(
            positions, store, refresh_interval, num_days=60,
        )

        # Graph A — current portfolio
        try:
            result_a = run_projection(tickers, weights, total_equity, store, refresh_interval)
        except Exception:  # noqa: BLE001
            result_a = None

        # Graph B — projected portfolio with ALL CTAs applied
        projected = self._lens_result.get('projected_positions', [])
        net_delta = self._lens_result.get('net_cta_delta', 0.0)
        result_b = None

        if projected:
            new_total = total_equity + net_delta
            if new_total > 0:
                b_tickers = [p['ticker'] for p in projected]
                b_equity = [p.get('equity', 0.0) for p in projected]
                b_total = sum(b_equity) or 1.0
                b_weights = [e / b_total for e in b_equity]

                try:
                    result_b = run_projection(
                        b_tickers, b_weights, total_equity, store, refresh_interval,
                    )
                except Exception:  # noqa: BLE001
                    result_b = None

        display_b = result_b if result_b is not None else result_a

        import numpy as np

        def _fan_spread(res: tuple | None) -> float | None:
            """Mean 10–90 percentile band width as a % of the opening value."""
            if res is None:
                return None
            _, bands, med = res
            if (10, 90) not in bands or med is None or len(med) == 0:
                return None
            lo, hi = bands[(10, 90)]
            base = float(med[0])
            if base <= 0:
                return None
            return float(np.mean((np.asarray(hi) - np.asarray(lo)) / base * 100))

        self._fan_spread_a = _fan_spread(result_a)
        self._fan_spread_b = _fan_spread(result_b)

        def _pct_extremes(res: tuple | None) -> list[float]:
            if res is None:
                return []
            _, bands, med = res
            base = float(med[0]) if med is not None and len(med) else 1.0
            if base <= 0:
                return []
            lo, hi = bands.get((10, 90), (np.array([]), np.array([])))
            hist_pct = [((v / base) - 1) * 100 for v in (hist_values or [])]
            band_pct = (((np.asarray(lo) / base) - 1) * 100).tolist() + \
                       (((np.asarray(hi) / base) - 1) * 100).tolist()
            return hist_pct + band_pct

        all_pct = _pct_extremes(result_a) + _pct_extremes(display_b)
        if all_pct:
            pad = (max(all_pct) - min(all_pct)) * 0.10
            shared_ylim: tuple[float, float] | None = (min(all_pct) - pad, max(all_pct) + pad)
        else:
            shared_ylim = None

        if result_a is not None:
            future_days, bands_a, median_a = result_a
            self._graph_a.plot(hist_days, hist_values, future_days, bands_a, median_a,
                               fan_color='#2dd4bf', ylim=shared_ylim)
        else:
            self._graph_a.show_no_data('Insufficient history for projection.')

        if display_b is not None:
            future_days_b, bands_b, median_b = display_b

            # Build descriptive title
            ctas = self._lens_result.get('ctas', [])
            actionable = [c for c in ctas if c.get('action') != 'hold']
            if actionable and result_b is not None:
                net = self._lens_result.get('net_cta_delta', 0.0)
                sign = '+' if net >= 0 else '-'
                b_title = f'With All Lens Projections  —  {sign}${abs(net):,.0f}'
            else:
                b_title = 'With All Lens Projections'

            self._graph_b.set_title(b_title)
            self._graph_b.plot(hist_days, hist_values, future_days_b, bands_b, median_b,
                               fan_color='#38bdf8', ylim=shared_ylim)
        else:
            self._graph_b.show_no_data('No lens guidance available.')

    def _update_pies(self) -> None:
        positions = self.window.positions or []

        if not positions:
            self._pie_a.show_empty('Add positions to see allocation.')
            self._pie_b.show_empty('Add positions to see allocation.')
            return

        # Pie A — current allocation
        current_sector_map: dict[str, float] = {}
        for p in positions:
            sector = p.get('sector') or 'Unknown'
            current_sector_map[sector] = current_sector_map.get(sector, 0.0) + p.get('equity', 0.0)
        self._pie_a.refresh(current_sector_map)

        # Pie B — projected allocation from all CTAs
        projected = self._lens_result.get('projected_positions', [])
        if projected:
            projected_sector_map: dict[str, float] = {}
            for p in projected:
                sector = p.get('sector') or 'Unknown'
                projected_sector_map[sector] = (
                    projected_sector_map.get(sector, 0.0) + p.get('equity', 0.0)
                )
            self._pie_b.refresh(projected_sector_map)

            # Check if allocation is identical (all hold)
            if projected_sector_map == current_sector_map:
                self._pie_b.set_title('Projected Allocation — No changes suggested')
            else:
                self._pie_b.set_title('Projected Allocation')
        else:
            self._pie_b.refresh(current_sector_map)
            self._pie_b.set_title('Projected Allocation — No changes suggested')
