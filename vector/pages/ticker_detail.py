from __future__ import annotations

from datetime import date
from functools import partial
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
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
from ..analytics import annualized_volatility, linear_regression_slope_percent
from ..scale import sc, scpt

if TYPE_CHECKING:
    from vector.app import VectorMainWindow


# Time period buttons -> yfinance period codes
_PERIODS: list[tuple[str, str]] = [
    ('1M', '1mo'),
    ('3M', '3mo'),
    ('6M', '6mo'),
    ('1Y', '1y'),
    ('2Y', '2y'),
]
_DEFAULT_PERIOD = '6mo'

_GREEN = '#4ade80'
_RED = '#f87171'
_MUTED = '#8d98af'
_ACCENT = '#2dd4bf'


def _is_dark() -> bool:
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    return app is not None and '#0b1020' in (app.styleSheet() or '')


def _card_shadow(widget: QFrame) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(32)
    shadow.setOffset(0, 10)
    shadow.setColor(QColor(0, 0, 0, 80))
    widget.setGraphicsEffect(shadow)


def _style_period_btn(btn: QPushButton, active: bool) -> None:
    border = '#2c364a' if _is_dark() else '#ccd5e5'
    if active:
        btn.setStyleSheet(
            'QPushButton {'
            ' background: qlineargradient(x1:0, y1:0, x2:1, y2:0,'
            ' stop:0 #2dd4bf, stop:0.5 #38bdf8, stop:1 #1e3a8a);'
            ' color: #ffffff; border: none;'
            f' border-radius: {sc(12)}px; padding: {sc(4)}px {sc(12)}px;'
            f' font-size: {scpt(10)}pt; font-weight: 700;'
            ' }'
        )
    else:
        btn.setStyleSheet(
            'QPushButton {'
            ' background: transparent; color: #8d98af;'
            f' border: 1px solid {border};'
            f' border-radius: {sc(12)}px; padding: {sc(4)}px {sc(12)}px;'
            f' font-size: {scpt(10)}pt; font-weight: 600;'
            ' }'
            'QPushButton:hover { color: #e7ebf3; }'
        )


class _InfoCard(QFrame):
    """Left-column card holding the label/value readout for a single ticker."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('cardFrame')
        _card_shadow(self)
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(sc(20), sc(20), sc(20), sc(20))
        self._v.setSpacing(sc(4))

    def clear(self) -> None:
        while self._v.count():
            item = self._v.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def add_price(self, text: str) -> None:
        lbl = QLabel(text)
        f = QFont()
        f.setPointSize(scpt(24))
        f.setBold(True)
        lbl.setFont(f)
        lbl.setStyleSheet(f'font-size: {scpt(24)}pt; font-weight: 700; border: none;')
        self._v.addWidget(lbl)

    def add_change(self, text: str, color: str) -> None:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f'font-size: {scpt(13)}pt; font-weight: 700; color: {color}; border: none;'
        )
        self._v.addWidget(lbl)

    def add_divider(self) -> None:
        line = QFrame()
        line.setProperty('role', 'divider')
        line.setFixedHeight(sc(1))
        wrap = QWidget()
        wrap.setStyleSheet('background: transparent;')
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, sc(8), 0, sc(8))
        wl.addWidget(line)
        self._v.addWidget(wrap)

    def add_row(self, label: str, value: str, value_color: str | None = None) -> None:
        row = QWidget()
        row.setStyleSheet('background: transparent;')
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, sc(3), 0, sc(3))
        rl.setSpacing(sc(8))

        lbl = QLabel(label)
        lbl.setProperty('role', 'muted')
        lbl.setStyleSheet(f'font-size: {scpt(12)}pt; border: none;')
        rl.addWidget(lbl)
        rl.addStretch(1)

        val = QLabel(value)
        color_css = f' color: {value_color};' if value_color else ''
        val.setStyleSheet(
            f'font-size: {scpt(13)}pt; font-weight: 600;{color_css} border: none;'
        )
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rl.addWidget(val)

        self._v.addWidget(row)

    def finish(self) -> None:
        self._v.addStretch(1)


class _PriceChartCard(QFrame):
    """Right-column card: period selector buttons + a lazy matplotlib price chart."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('cardFrame')
        _card_shadow(self)
        self.on_period = None  # callback(period_code) set by the page

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(sc(16), sc(16), sc(16), sc(12))
        self._outer.setSpacing(sc(10))

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(sc(6))
        title = QLabel('Price History')
        f = QFont()
        f.setPointSize(scpt(12))
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f'font-size: {scpt(12)}pt; font-weight: 700;')
        header.addWidget(title)
        header.addStretch(1)

        self._period_btns: dict[str, QPushButton] = {}
        for label, code in _PERIODS:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(partial(self._on_btn, code))
            self._period_btns[code] = btn
            header.addWidget(btn)
        self._outer.addLayout(header)

        self._placeholder = QLabel('Loading chart...')
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setProperty('role', 'muted')
        self._placeholder.setStyleSheet(f'font-size: {scpt(11)}pt;')
        self._placeholder.setMinimumHeight(sc(320))
        self._outer.addWidget(self._placeholder, stretch=1)

        self._canvas = None
        self._ax = None
        self._fig = None
        self._is_dark = True

        self.set_active_period(_DEFAULT_PERIOD)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def _on_btn(self, code: str) -> None:
        self.set_active_period(code)
        if callable(self.on_period):
            self.on_period(code)

    def set_active_period(self, code: str) -> None:
        for c, btn in self._period_btns.items():
            _style_period_btn(btn, c == code)

    def _ensure_canvas(self) -> None:
        if self._canvas is not None:
            return
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        self._is_dark = _is_dark()
        self._fig = Figure(facecolor='#161b26' if self._is_dark else '#f8faff')
        self._fig.subplots_adjust(left=0.06, right=0.88, top=0.90, bottom=0.22)
        self._ax = self._fig.add_subplot(111)
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._canvas.setMinimumHeight(sc(320))
        # Let scroll events bubble up to the outer page scroll area.
        self._canvas.wheelEvent = lambda event: event.ignore()
        self._outer.addWidget(self._canvas, stretch=1)

    def show_no_data(self, msg: str = 'No data available.') -> None:
        self._placeholder.setText(msg)
        self._placeholder.show()
        if self._canvas is not None:
            self._canvas.hide()

    def plot(self, closes: list[float]) -> None:
        import numpy as np
        from matplotlib.ticker import FuncFormatter

        self._ensure_canvas()
        self._canvas.show()
        self._placeholder.hide()

        ax = self._ax
        ax.clear()

        is_dark = self._is_dark
        ax_bg = '#121828' if is_dark else '#f0f4fb'
        muted = '#8d98af' if is_dark else '#536075'
        grid = '#2a3142' if is_dark else '#dde4f0'

        ax.set_facecolor(ax_bg)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(axis='both', colors=muted, labelsize=8)
        ax.grid(True, color=grid, alpha=0.5, linewidth=0.5, zorder=0)
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position('right')

        x = list(range(len(closes)))
        y = np.asarray(closes, dtype=float)
        ax.plot(x, y, color=_ACCENT, lw=1.6, zorder=3)
        ax.fill_between(x, y, float(y.min()), color=_ACCENT, alpha=0.08, zorder=1)

        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f'${v:,.0f}'))
        # Price history is a plain close-series (no date axis from get_history);
        # hide the x ticks so the chart reads cleanly across periods.
        ax.set_xticks([])
        ax.margins(x=0.01)

        self._canvas.draw()


class TickerDetailPage(QWidget):
    """Single-ticker detail view: info readout on the left, price chart on the right.

    Reachable only by clicking a ticker (no sidebar entry). ``set_ticker`` loads
    all data and renders; ``refresh`` re-renders the current ticker in place.
    """

    def __init__(self, window: 'VectorMainWindow') -> None:
        super().__init__()
        self.window = window
        self._ticker: str | None = None
        self._period = _DEFAULT_PERIOD
        self._build_ui()

    def _build_ui(self) -> None:
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
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, sc(8), 0, sc(24))
        cl.setSpacing(sc(16))

        # Back button (left-aligned)
        back_row = QHBoxLayout()
        back_row.setContentsMargins(0, 0, 0, 0)
        self._back_btn = QPushButton('‹  Back')
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setFixedHeight(sc(32))
        self._back_btn.setStyleSheet(
            f'QPushButton {{ padding: {sc(4)}px {sc(14)}px;'
            f' border-radius: {sc(10)}px; font-size: {scpt(10)}pt; }}'
        )
        self._back_btn.clicked.connect(self._on_back)
        back_row.addWidget(self._back_btn)
        back_row.addStretch(1)
        cl.addLayout(back_row)

        # Header: ticker symbol + company name
        self._ticker_lbl = QLabel('')
        tf = QFont()
        tf.setPointSize(scpt(24))
        tf.setBold(True)
        self._ticker_lbl.setFont(tf)
        self._ticker_lbl.setStyleSheet(f'font-size: {scpt(24)}pt; font-weight: 700;')
        self._name_lbl = QLabel('')
        self._name_lbl.setProperty('role', 'muted')
        self._name_lbl.setStyleSheet(f'font-size: {scpt(13)}pt;')
        header_col = QVBoxLayout()
        header_col.setSpacing(sc(2))
        header_col.addWidget(self._ticker_lbl)
        header_col.addWidget(self._name_lbl)
        cl.addLayout(header_col)

        # Two-column row: info card (left, fixed) + chart card (right, expanding)
        body = QWidget()
        body_l = QHBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, 0)
        body_l.setSpacing(sc(16))

        self._info_card = _InfoCard()
        self._info_card.setFixedWidth(sc(340))
        self._chart_card = _PriceChartCard()
        self._chart_card.on_period = self._on_period_selected

        body_l.addWidget(self._info_card, 0, Qt.AlignmentFlag.AlignTop)
        body_l.addWidget(self._chart_card, 1)
        cl.addWidget(body)

        cl.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll, stretch=1)

    # ── Public API ────────────────────────────────────────────────────────

    def set_ticker(self, ticker: str) -> None:
        """Load and render all data for ``ticker``; reset the chart to 6M."""
        if ticker == self._ticker:
            return
        self._ticker = ticker
        self._period = _DEFAULT_PERIOD
        self._chart_card.set_active_period(self._period)
        self._render()

    def refresh(self) -> None:
        """Re-render the current ticker (used by global auto-refresh)."""
        if self._ticker:
            self._render()

    # ── Navigation ────────────────────────────────────────────────────────

    def _on_back(self) -> None:
        if self.window.shell is not None:
            self.window.shell.go_back()

    # ── Rendering ─────────────────────────────────────────────────────────

    def _render(self) -> None:
        self._populate_info()
        self._reload_chart()

    def _position(self) -> dict | None:
        for p in (self.window.positions or []):
            if p.get('ticker') == self._ticker:
                return p
        return None

    def _populate_info(self) -> None:
        ticker = self._ticker
        if not ticker:
            return
        store = self.window.store
        ri = self.window.settings.get('refresh_interval', '5 min')
        fmt = self.window.format_currency

        position = self._position()
        quote = store.get_quote(ticker) or {}
        meta = store.get_meta(ticker) or {}

        name = (
            meta.get('long_name')
            or meta.get('name')
            or (position.get('name') if position else None)
            or ticker
        )
        sector = (
            (position.get('sector') if position else None)
            or meta.get('sector')
            or 'Unknown'
        )
        price = (
            quote.get('price')
            or (position.get('current_price') if position else None)
            or 0.0
        )

        self._ticker_lbl.setText(ticker)
        self._name_lbl.setText(name)

        card = self._info_card
        card.clear()

        # Price + daily change
        card.add_price(fmt(price))
        change = quote.get('change')
        change_pct = quote.get('change_pct')
        if change is not None and change_pct is not None:
            up = change >= 0
            color = _GREEN if up else _RED
            sign = '+' if up else '-'
            card.add_change(
                f'{sign}{fmt(abs(change))} ({change_pct:+.2f}%)', color,
            )

        card.add_divider()

        # Holding
        if position is not None:
            shares = position.get('shares', 0.0)
            card.add_row('Shares held', f'{shares:,.4g}')
            equity = position.get('equity', 0.0) or shares * price
            card.add_row('Equity', fmt(equity))
        card.add_row('Sector', sector)

        # Beta
        beta = quote.get('beta')
        if beta is not None and beta != 0:
            card.add_row('Beta', f'{beta:.2f}')

        # Volatility + slope (prefer values computed during refresh_data)
        vol = position.get('volatility') if position else None
        slope = position.get('slope_percent') if position else None
        if vol is None or slope is None:
            try:
                six_mo = store.get_history(ticker, '6mo', ri) or []
            except Exception:  # noqa: BLE001
                six_mo = []
            if vol is None:
                vol = annualized_volatility(six_mo)
            if slope is None:
                slope = linear_regression_slope_percent(six_mo)
        if vol:
            card.add_row('Annualized volatility', f'{vol * 100:.1f}%')
        if slope is not None:
            scolor = _GREEN if slope >= 0 else _RED
            card.add_row('Trend (slope)', f'{slope:+.2f}%', scolor)

        # Dividend yield (already a percent in the stored quote)
        div_yield = quote.get('dividend_yield')
        if div_yield:
            card.add_row('Dividend yield', f'{div_yield:.2f}%')

        # Next earnings date (hidden when unavailable)
        next_earn = self._next_earnings_date(store, ticker)
        if next_earn is not None:
            card.add_row('Next earnings', self.window.format_date(next_earn.isoformat()))

        # Next ex-dividend date (hidden when unavailable)
        next_exdiv = self._next_ex_dividend_date(store, ticker, quote)
        if next_exdiv is not None:
            card.add_row('Next ex-dividend', self.window.format_date(next_exdiv.isoformat()))

        # Cost basis + unrealized P&L (only when held)
        if position is not None:
            shares = position.get('shares', 0.0)
            entry_price = position.get('price') or price
            cost_basis = shares * entry_price
            current_value = position.get('equity', 0.0) or shares * price
            if cost_basis > 0:
                card.add_divider()
                card.add_row('Cost basis', fmt(cost_basis))
                pnl = current_value - cost_basis
                pnl_pct = pnl / cost_basis * 100
                up = pnl >= 0
                color = _GREEN if up else _RED
                sign = '+' if up else '-'
                card.add_row(
                    'Unrealized P&L',
                    f'{sign}{fmt(abs(pnl))} ({pnl_pct:+.2f}%)',
                    color,
                )

        card.finish()

    def _next_earnings_date(self, store, ticker: str):
        try:
            earnings = store.get_earnings(ticker) or []
        except Exception:  # noqa: BLE001
            return None
        today = date.today()
        upcoming: list[date] = []
        for entry in earnings:
            raw = str(entry.get('date', ''))[:10]
            try:
                d = date.fromisoformat(raw)
            except ValueError:
                continue
            if d >= today:
                upcoming.append(d)
        return min(upcoming) if upcoming else None

    def _next_ex_dividend_date(self, store, ticker: str, quote: dict):
        """Best-effort forward ex-dividend date. The store does not currently
        cache a forward date, so this returns None (the row is hidden) unless a
        future-dated ex-dividend turns up in the quote/dividend data."""
        raw = quote.get('ex_dividend_date')
        if raw:
            try:
                d = date.fromisoformat(str(raw)[:10])
                if d >= date.today():
                    return d
            except ValueError:
                pass
        today = date.today()
        try:
            divs = store.get_dividends(ticker) or []
        except Exception:  # noqa: BLE001
            return None
        upcoming: list[date] = []
        for entry in divs:
            try:
                d = date.fromisoformat(str(entry.get('date', ''))[:10])
            except ValueError:
                continue
            if d >= today:
                upcoming.append(d)
        return min(upcoming) if upcoming else None

    # ── Chart ─────────────────────────────────────────────────────────────

    def _on_period_selected(self, code: str) -> None:
        self._period = code
        self._reload_chart()

    def _reload_chart(self) -> None:
        if not self._ticker:
            return
        store = self.window.store
        ri = self.window.settings.get('refresh_interval', '5 min')
        try:
            closes = store.get_history(self._ticker, self._period, ri) or []
        except Exception:  # noqa: BLE001
            closes = []
        if len(closes) < 2:
            self._chart_card.show_no_data('No data available for this period.')
        else:
            self._chart_card.plot(closes)
