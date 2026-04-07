from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QWidget, QScrollArea, QFrame
from PyQt6.QtGui import QFont, QColor, QPainter
from PyQt6.QtCore import Qt, QRectF

from vector.widget_base import VectorWidget
from vector.analytics import annualized_volatility, score_volatility, classify_volatility
from vector.constants import VOLATILITY_LOOKBACK_PERIODS

_MUTED = '#8d98af'
_GREEN = '#4ade80'
_YELLOW = '#f3b84b'
_RED = '#f87171'


def _title_font(size: int = 22) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(True)
    return f


class _VolBar(QWidget):
    """Single row: ticker | annualized vol% | colored bar"""

    def __init__(self, ticker: str, vol_pct: float, weight_pct: float,
                 color: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        ticker_lbl = QLabel(ticker)
        ticker_lbl.setFont(_title_font(12))
        ticker_lbl.setFixedWidth(52)
        ticker_lbl.setStyleSheet('font-size: 12pt; border: none;')
        row.addWidget(ticker_lbl)

        bar = _MiniBar(vol_pct, color)
        bar.setFixedHeight(8)
        row.addWidget(bar, stretch=3)

        vol_lbl = QLabel(f'{vol_pct:.1f}%')
        vol_lbl.setMinimumWidth(52)
        vol_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        vol_lbl.setStyleSheet(f'color: {color}; font-size: 9pt; font-weight: 700; border: none;')
        row.addWidget(vol_lbl)

        wt_lbl = QLabel(f'{weight_pct:.0f}% wt')
        wt_lbl.setMinimumWidth(46)
        wt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        wt_lbl.setProperty('role', 'muted')
        wt_lbl.setStyleSheet('font-size: 10pt; border: none;')
        row.addWidget(wt_lbl)


class _MiniBar(QWidget):
    def __init__(self, pct: float, color: str, parent=None) -> None:
        super().__init__(parent)
        self._pct = min(pct, 100.0)
        self._color = QColor(color)
        self.setFixedHeight(8)

    def paintEvent(self, _event) -> None:  # noqa: N802
        from PyQt6.QtWidgets import QApplication
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        app = QApplication.instance()
        is_dark = app is not None and '#0b1020' in (app.styleSheet() or '')
        track_color = '#1e2840' if is_dark else '#d8e2f0'
        painter.setBrush(QColor(track_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        fill_w = max(0.0, w * self._pct / 100.0)
        if fill_w > 0:
            painter.setBrush(self._color)
            painter.drawRoundedRect(QRectF(0, 0, fill_w, h), h / 2, h / 2)


def _vol_color(score: int, low: int, high: int) -> str:
    if score < low:
        return _GREEN
    if score <= high:
        return _YELLOW
    return _RED


class PortfolioVolatilityWidget(VectorWidget):
    NAME = 'Volatility'
    DESCRIPTION = 'Equity-weighted portfolio volatility with per-ticker breakdown.'
    DEFAULT_ROWSPAN = 2
    DEFAULT_COLSPAN = 4

    def __init__(self, window=None, parent=None) -> None:
        super().__init__(window=window, parent=parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(4)

        # Header row: title + label badge
        header = QHBoxLayout()
        title_lbl = QLabel('Volatility')
        title_lbl.setFont(_title_font(16))
        title_lbl.setStyleSheet('font-size: 16pt; border: none;')
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._label_lbl = QLabel('')
        self._label_lbl.setProperty('role', 'muted')
        self._label_lbl.setStyleSheet('font-size: 11pt; border: none;')
        header.addWidget(self._label_lbl)
        layout.addLayout(header)

        # Score + description row
        score_row = QHBoxLayout()
        self._score_lbl = QLabel('—')
        self._score_lbl.setFont(_title_font(16))
        self._score_lbl.setStyleSheet('font-size: 16pt; border: none;')
        score_row.addWidget(self._score_lbl)
        self._desc_lbl = QLabel('')
        self._desc_lbl.setProperty('role', 'muted')
        self._desc_lbl.setStyleSheet('font-size: 8pt; border: none;')
        self._desc_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        score_row.addWidget(self._desc_lbl)
        score_row.addStretch(1)
        layout.addLayout(score_row)

        layout.addSpacing(6)

        # Per-ticker bars
        self._bars_widget = QWidget()
        self._bars_widget.setStyleSheet('background: transparent;')
        self._bars_layout = QVBoxLayout(self._bars_widget)
        self._bars_layout.setContentsMargins(0, 0, 0, 0)
        self._bars_layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidget(self._bars_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet('background: transparent; border: none;')
        layout.addWidget(scroll, stretch=1)

    def refresh(self) -> None:
        if not self._window:
            return
        positions = self._window.positions or []
        store = self._window.store
        refresh_interval = self._window.settings.get('refresh_interval', '5 min')
        vol_settings = self._window.settings.get('volatility', {})
        lookback = vol_settings.get('lookback', '6 months')
        period = VOLATILITY_LOOKBACK_PERIODS.get(lookback, '6mo')
        low_cutoff = int(vol_settings.get('low_cutoff', 30))
        high_cutoff = int(vol_settings.get('high_cutoff', 60))

        # Clear bars
        while self._bars_layout.count():
            item = self._bars_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not positions:
            self._score_lbl.setText('—')
            self._label_lbl.setText('')
            self._desc_lbl.setText('No positions')
            self._bars_layout.addStretch(1)
            return

        total_equity = sum(p.get('equity', 0) for p in positions)

        # Compute per-ticker volatility, then equity-weighted average
        ticker_vols: list[tuple[str, float, float]] = []  # (ticker, vol_pct, equity)
        weighted_vol = 0.0
        for pos in positions:
            ticker = pos['ticker']
            equity = pos.get('equity', 0.0)
            try:
                closes = store.get_history(ticker, period, refresh_interval)
            except Exception:  # noqa: BLE001
                closes = []
            raw_vol = annualized_volatility(closes)
            vol_pct = raw_vol * 100  # express as %
            weight = equity / total_equity if total_equity else 0.0
            weighted_vol += raw_vol * weight
            ticker_vols.append((ticker, vol_pct, equity))

        score = score_volatility(weighted_vol)
        label, color = classify_volatility(score, low_cutoff, high_cutoff)

        self._score_lbl.setText(str(score))
        self._score_lbl.setStyleSheet(f'color: {color}; font-size: 16pt; border: none;')
        self._label_lbl.setText(label)
        self._label_lbl.setStyleSheet(f'color: {color}; font-size: 11pt; font-weight: 700; border: none;')
        self._desc_lbl.setText(f'/ 100  ·  {lookback} annualized')

        # Sort by volatility descending
        ticker_vols.sort(key=lambda x: x[1], reverse=True)

        for ticker, vol_pct, equity in ticker_vols:
            weight_pct = (equity / total_equity * 100) if total_equity else 0
            bar_color = _vol_color(score_volatility(vol_pct / 100), low_cutoff, high_cutoff)
            self._bars_layout.addWidget(
                _VolBar(ticker, vol_pct, weight_pct, bar_color)
            )

        self._bars_layout.addStretch(1)
