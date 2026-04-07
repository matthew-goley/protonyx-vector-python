from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget, QFrame,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from vector.widget_base import VectorWidget

_MUTED = '#8d98af'
_GREEN = '#4ade80'
_RED   = '#f87171'


def _title_font(size: int = 22) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(True)
    return f


class _PositionRow(QFrame):
    def __init__(self, pos: dict, fmt_currency, fmt_pct, parent=None) -> None:
        super().__init__(parent)
        self.setProperty('role', 'row-divider')
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 8, 0, 8)
        row.setSpacing(8)

        # Ticker + name
        id_col = QVBoxLayout()
        id_col.setSpacing(2)
        ticker_lbl = QLabel(pos.get('ticker', ''))
        ticker_lbl.setFont(_title_font(13))
        ticker_lbl.setStyleSheet('font-size: 13pt; border: none;')
        name_lbl = QLabel(pos.get('name') or pos.get('sector') or '—')
        name_lbl.setProperty('role', 'muted')
        name_lbl.setStyleSheet('font-size: 11pt; border: none;')
        name_lbl.setMaximumWidth(130)
        name_lbl.setTextFormat(Qt.TextFormat.PlainText)
        fm = name_lbl.fontMetrics()
        elided = fm.elidedText(name_lbl.text(), Qt.TextElideMode.ElideRight, 130)
        name_lbl.setText(elided)
        id_col.addWidget(ticker_lbl)
        id_col.addWidget(name_lbl)
        row.addLayout(id_col, stretch=2)

        # Shares
        shares_lbl = QLabel(f"{pos.get('shares', 0):,.4g} sh")
        shares_lbl.setProperty('role', 'muted')
        shares_lbl.setStyleSheet('font-size: 11pt; border: none;')
        shares_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(shares_lbl, stretch=1)

        # Current price
        price = pos.get('current_price') or pos.get('price', 0)
        price_lbl = QLabel(fmt_currency(price))
        price_lbl.setStyleSheet('font-size: 12pt; border: none;')
        price_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(price_lbl, stretch=1)

        # Equity
        equity_lbl = QLabel(fmt_currency(pos.get('equity', 0)))
        equity_font = QFont()
        equity_font.setPointSize(12)
        equity_font.setBold(True)
        equity_lbl.setFont(equity_font)
        equity_lbl.setStyleSheet('font-size: 12pt; border: none;')
        equity_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(equity_lbl, stretch=2)

        # 5d change % (from slope_percent if available, else '—')
        slope = pos.get('slope_percent')
        if slope is not None:
            sign = '+' if slope >= 0 else ''
            color = _GREEN if slope >= 0 else _RED
            change_text = f'{sign}{slope:.2f}%'
        else:
            color = _MUTED
            change_text = '—'
        change_lbl = QLabel(change_text)
        change_lbl.setStyleSheet(f'color: {color}; font-size: 12pt; font-weight: 700; border: none;')
        change_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(change_lbl, stretch=1)


class PositionsListWidget(VectorWidget):
    NAME = 'Positions'
    DESCRIPTION = 'All held positions with price, equity, and trend.'
    DEFAULT_ROWSPAN = 3
    DEFAULT_COLSPAN = 5

    def __init__(self, window=None, parent=None) -> None:
        super().__init__(window=window, parent=parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(8)

        # Header row
        header = QHBoxLayout()
        title_lbl = QLabel('Positions')
        title_lbl.setFont(_title_font(16))
        title_lbl.setStyleSheet('font-size: 16pt; border: none;')
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._count_lbl = QLabel('')
        self._count_lbl.setProperty('role', 'muted')
        self._count_lbl.setStyleSheet('font-size: 11pt; border: none;')
        header.addWidget(self._count_lbl)
        layout.addLayout(header)

        # Column headers
        col_row = QHBoxLayout()
        col_row.setContentsMargins(0, 0, 0, 0)
        col_row.setSpacing(8)
        for label, stretch, align in [
            ('Ticker / Name', 2, Qt.AlignmentFlag.AlignLeft),
            ('Shares', 1, Qt.AlignmentFlag.AlignRight),
            ('Price', 1, Qt.AlignmentFlag.AlignRight),
            ('Equity', 2, Qt.AlignmentFlag.AlignRight),
            ('6mo Trend', 1, Qt.AlignmentFlag.AlignRight),
        ]:
            lbl = QLabel(label)
            lbl.setProperty('role', 'muted')
            lbl.setStyleSheet('font-size: 10pt; border: none;')
            lbl.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            col_row.addWidget(lbl, stretch=stretch)
        layout.addLayout(col_row)

        # Scrollable rows container
        self._rows_widget = QWidget()
        self._rows_widget.setStyleSheet('background: transparent;')
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidget(self._rows_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet('background: transparent; border: none;')
        layout.addWidget(scroll, stretch=1)

    def refresh(self) -> None:
        if not self._window:
            return
        positions = self._window.positions or []
        fmt = self._window.format_currency

        # Clear existing rows
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._count_lbl.setText(f'{len(positions)} position{"s" if len(positions) != 1 else ""}')

        for pos in positions:
            self._rows_layout.addWidget(_PositionRow(pos, fmt, None))

        self._rows_layout.addStretch(1)
