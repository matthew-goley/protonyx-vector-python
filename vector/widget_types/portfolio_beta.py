"""
Portfolio Beta widget — sensitivity of your portfolio to the S&P 500 (SPY).

  Beta > 1.0  → amplifies market moves (more volatile than market)
  Beta = 1.0  → moves with the market
  Beta < 1.0  → defensive (less sensitive than market)
  Beta < 0.0  → inverse (moves opposite to market)

Also shows R² (correlation²) — how much of portfolio variance is explained by the market.
"""

from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QWidget
from PyQt6.QtGui import QFont, QColor, QPainter
from PyQt6.QtCore import Qt, QRectF

from vector.widget_base import VectorWidget
from vector.analytics import portfolio_daily_returns, portfolio_beta
from vector.constants import VOLATILITY_LOOKBACK_PERIODS

import numpy as np

_MUTED  = '#8d98af'
_GREEN  = '#4ade80'
_YELLOW = '#f3b84b'
_RED    = '#f87171'
_BLUE   = '#54BFFF'
_PURPLE = '#8B3FCF'

_BENCHMARK = 'SPY'


def _title_font(size: int = 22) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(True)
    return f


def _beta_color(b: float) -> str:
    if b < 0:
        return _PURPLE
    if b < 0.8:
        return _GREEN
    if b <= 1.5:
        return _YELLOW
    return _RED


def _beta_label(b: float) -> str:
    if b < 0:
        return 'Inverse'
    if b < 0.8:
        return 'Defensive'
    if b <= 1.0:
        return 'Below Market'
    if b <= 1.5:
        return 'Market-Like'
    return 'Aggressive'


class _BetaGauge(QWidget):
    """Simple horizontal gauge from -1 to +2, with a marker at beta value."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._beta = 1.0
        self._color = QColor(_YELLOW)
        self.setFixedHeight(12)

    def set_beta(self, beta: float, color: str) -> None:
        self._beta = beta
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        from PyQt6.QtWidgets import QApplication
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())

        # Track
        app = QApplication.instance()
        is_dark = app is not None and '#0b1020' in (app.styleSheet() or '')
        track_color = '#1e2840' if is_dark else '#d8e2f0'
        painter.setBrush(QColor(track_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(0, 2, w, h - 4), 3, 3)

        # Scale: -1 at left, +2 at right
        lo, hi = -1.0, 2.0
        t = max(0.0, min(1.0, (self._beta - lo) / (hi - lo)))
        marker_x = t * w

        # Filled portion from 0 to marker
        zero_x = (0.0 - lo) / (hi - lo) * w
        left = min(zero_x, marker_x)
        right = max(zero_x, marker_x)
        fill_w = right - left
        if fill_w > 0:
            painter.setBrush(self._color)
            painter.drawRoundedRect(QRectF(left, 2, fill_w, h - 4), 3, 3)

        # Marker dot
        painter.setBrush(QColor('#ffffff'))
        r = h / 2
        painter.drawEllipse(QRectF(marker_x - r, 0, h, h))


class PortfolioBetaWidget(VectorWidget):
    NAME = 'Beta'
    DESCRIPTION = 'Portfolio sensitivity to the S&P 500 (SPY).'
    DEFAULT_ROWSPAN = 2
    DEFAULT_COLSPAN = 3

    def __init__(self, window=None, parent=None) -> None:
        super().__init__(window=window, parent=parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        title_lbl = QLabel('Beta')
        title_lbl.setFont(_title_font(16))
        title_lbl.setStyleSheet('font-size: 16pt; border: none;')
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._benchmark_lbl = QLabel(f'vs {_BENCHMARK}')
        self._benchmark_lbl.setProperty('role', 'muted')
        self._benchmark_lbl.setStyleSheet('font-size: 10pt; border: none;')
        header.addWidget(self._benchmark_lbl)
        layout.addLayout(header)

        # Beta value + label
        score_row = QHBoxLayout()
        self._beta_lbl = QLabel('—')
        self._beta_lbl.setFont(_title_font(16))
        self._beta_lbl.setStyleSheet('font-size: 16pt; border: none;')
        score_row.addWidget(self._beta_lbl)
        self._label_lbl = QLabel('')
        self._label_lbl.setProperty('role', 'muted')
        self._label_lbl.setStyleSheet('font-size: 13pt; font-weight: 700; border: none;')
        self._label_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        score_row.addWidget(self._label_lbl)
        score_row.addStretch(1)
        layout.addLayout(score_row)

        layout.addSpacing(8)

        # Gauge
        self._gauge = _BetaGauge()
        layout.addWidget(self._gauge)

        layout.addSpacing(6)

        # Interpretation
        self._interp_lbl = QLabel('')
        self._interp_lbl.setWordWrap(True)
        self._interp_lbl.setProperty('role', 'muted')
        self._interp_lbl.setStyleSheet('font-size: 11pt; border: none;')
        layout.addWidget(self._interp_lbl)

        layout.addStretch(1)

    def refresh(self) -> None:
        if not self._window:
            return

        positions = self._window.positions or []
        store = self._window.store
        refresh_interval = self._window.settings.get('refresh_interval', '5 min')
        vol_settings = self._window.settings.get('volatility', {})
        lookback = vol_settings.get('lookback', '6 months')
        period = VOLATILITY_LOOKBACK_PERIODS.get(lookback, '6mo')

        self._benchmark_lbl.setText(f'vs {_BENCHMARK}  ·  {lookback}')

        if not positions:
            self._beta_lbl.setText('—')
            self._label_lbl.setText('No positions')
            return

        # Portfolio returns
        closes_map = {
            pos['ticker']: store.get_history(pos['ticker'], period, refresh_interval)
            for pos in positions
        }
        port_returns = portfolio_daily_returns(positions, closes_map)

        # Benchmark returns
        try:
            spy_closes = store.get_history(_BENCHMARK, period, refresh_interval)
        except Exception:  # noqa: BLE001
            spy_closes = []

        if len(spy_closes) < 3:
            arr_spy = np.array([])
        else:
            arr_spy = np.array(spy_closes, dtype=float)
            spy_returns = (np.diff(arr_spy) / arr_spy[:-1]).tolist()

        if not port_returns or len(spy_closes) < 3:
            self._beta_lbl.setText('—')
            self._label_lbl.setText('Insufficient data')
            return

        b = portfolio_beta(port_returns, spy_returns)
        color = _beta_color(b)
        label = _beta_label(b)

        self._beta_lbl.setText(f'{b:.2f}')
        self._beta_lbl.setStyleSheet(f'color: {color}; font-size: 16pt; border: none;')
        self._label_lbl.setText(label)
        self._label_lbl.setStyleSheet(
            f'color: {color}; font-size: 13pt; font-weight: 700; border: none;'
        )
        self._gauge.set_beta(b, color)

        if b > 1.5:
            interp = f'Your portfolio swings harder than the market — bigger gains, but bigger dips too.'
        elif b > 1.0:
            interp = f'Moves a bit more than the market. Slightly more risk, slightly more reward.'
        elif b >= 0.8:
            interp = f'Tracks closely with the overall market.'
        elif b >= 0.0:
            interp = f'Less sensitive to market swings — a more stable, defensive mix.'
        else:
            interp = f'Tends to move opposite the market — uncommon, but can help balance a portfolio.'
        self._interp_lbl.setText(interp)
