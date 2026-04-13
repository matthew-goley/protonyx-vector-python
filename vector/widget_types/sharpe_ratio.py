"""
Sharpe Ratio widget — annualized risk-adjusted return vs risk-free rate.

  Sharpe = (annualized_return - risk_free_rate) / annualized_volatility

Risk-free rate default: 4.5% (approximate current US 3-month T-bill).
Lookback: uses the same period configured in Settings → Volatility.

Interpretation guide shown inside the widget:
  > 2.0   Excellent
  1–2     Good
  0–1     Sub-optimal
  < 0     Poor
"""

from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from vector.widget_base import VectorWidget
from vector.analytics import portfolio_daily_returns, sharpe_ratio
from vector.constants import VOLATILITY_LOOKBACK_PERIODS

_MUTED  = '#8d98af'
_GREEN  = '#4ade80'
_YELLOW = '#f3b84b'
_RED    = '#f87171'
_BLUE   = '#54BFFF'

_RISK_FREE_RATE = 0.045  # 4.5% annual


def _title_font(size: int = 22) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(True)
    return f


def _sharpe_color(s: float) -> str:
    if s >= 2.0:
        return _GREEN
    if s >= 1.0:
        return _BLUE
    if s >= 0.0:
        return _YELLOW
    return _RED


def _sharpe_label(s: float) -> str:
    if s >= 2.0:
        return 'Excellent'
    if s >= 1.0:
        return 'Good'
    if s >= 0.0:
        return 'Sub-optimal'
    return 'Poor'


class _TierRow(QLabel):
    def __init__(self, tier: str, desc: str, parent=None) -> None:
        super().__init__(parent)
        self._tier = tier
        self._desc = desc
        self.setStyleSheet('border: none; font-size: 12pt;')
        self.setTextFormat(Qt.TextFormat.RichText)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        is_dark = app is not None and '#0b1020' in (app.styleSheet() or '')
        active_color = '#e7ebf3' if is_dark else '#182233'
        muted_color = '#8d98af' if is_dark else '#536075'
        color = active_color if active else muted_color
        weight = '700' if active else '400'
        self.setText(
            f'<span style="color:{color};font-weight:{weight};">{self._tier}</span>'
            f'<span style="color:{muted_color};font-size:11pt;"> — {self._desc}</span>'
        )


class SharpeRatioWidget(VectorWidget):
    NAME = 'Sharpe Ratio'
    DESCRIPTION = 'Risk-adjusted portfolio return vs the risk-free rate.'
    DEFAULT_ROWSPAN = 2
    DEFAULT_COLSPAN = 3

    def __init__(self, window=None, parent=None) -> None:
        super().__init__(window=window, parent=parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        title_lbl = QLabel('Sharpe Ratio')
        title_lbl.setFont(_title_font(16))
        title_lbl.setStyleSheet('font-size: 16pt; border: none;')
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._period_lbl = QLabel('')
        self._period_lbl.setProperty('role', 'muted')
        self._period_lbl.setStyleSheet('font-size: 10pt; border: none;')
        header.addWidget(self._period_lbl)
        layout.addLayout(header)

        # Score row
        score_row = QHBoxLayout()
        self._score_lbl = QLabel('—')
        self._score_lbl.setFont(_title_font(16))
        self._score_lbl.setStyleSheet('font-size: 16pt; border: none;')
        score_row.addWidget(self._score_lbl)

        self._label_lbl = QLabel('')
        self._label_lbl.setProperty('role', 'muted')
        self._label_lbl.setStyleSheet('font-size: 13pt; font-weight: 700; border: none;')
        self._label_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        score_row.addWidget(self._label_lbl)
        score_row.addStretch(1)
        layout.addLayout(score_row)

        self._rf_lbl = QLabel(f'rf = {_RISK_FREE_RATE * 100:.1f}%')
        self._rf_lbl.setProperty('role', 'muted')
        self._rf_lbl.setStyleSheet('font-size: 10pt; border: none;')
        layout.addWidget(self._rf_lbl)

        layout.addSpacing(8)

        # Interpretation tiers
        self._tiers: list[_TierRow] = []
        for tier, desc in [
            ('> 2.0', 'Excellent — strong risk-adjusted return'),
            ('1 – 2', 'Good — solid performance'),
            ('0 – 1', 'Sub-optimal — low return for the risk'),
            ('< 0',   'Poor — underperforming risk-free assets'),
        ]:
            row = _TierRow(tier, desc)
            self._tiers.append(row)
            layout.addWidget(row)

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

        self._period_lbl.setText(lookback)

        if not positions:
            self._score_lbl.setText('—')
            self._label_lbl.setText('No positions')
            return

        closes_map = {
            pos['ticker']: store.get_history(pos['ticker'], period, refresh_interval)
            for pos in positions
        }
        returns = portfolio_daily_returns(positions, closes_map)

        if not returns:
            self._score_lbl.setText('—')
            self._label_lbl.setText('Insufficient data')
            return

        s = sharpe_ratio(returns, _RISK_FREE_RATE)
        color = _sharpe_color(s)
        label = _sharpe_label(s)

        self._score_lbl.setText(f'{s:.2f}')
        self._score_lbl.setStyleSheet(f'color: {color}; font-size: 16pt; border: none;')
        self._label_lbl.setText(label)
        self._label_lbl.setStyleSheet(
            f'color: {color}; font-size: 13pt; font-weight: 700; border: none;'
        )

        # Highlight the active tier
        tier_index = 3 if s < 0 else (2 if s < 1 else (1 if s < 2 else 0))
        for i, row in enumerate(self._tiers):
            row.set_active(i == tier_index)
