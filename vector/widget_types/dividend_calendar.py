"""
Dividend Calendar widget — estimates next ex-dividend dates from historical dividend data.

Frequency detection: looks at gaps between the last few dividends to infer
monthly (~30d), quarterly (~90d), semi-annual (~180d), or annual (~365d) cadence.
Next ex-div date = last known date + detected frequency (estimate only).
"""

from datetime import date, timedelta
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QWidget, QScrollArea, QFrame,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from vector.widget_base import VectorWidget

_MUTED  = '#8d98af'
_GREEN  = '#4ade80'
_YELLOW = '#f3b84b'
_BLUE   = '#54BFFF'


def _title_font(size: int = 22) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(True)
    return f


def _detect_frequency(dates: list[date]) -> tuple[str, int]:
    """Return (label, approx_days) from the last few dividend gaps."""
    if len(dates) < 2:
        return 'Annual', 365
    gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    avg = sum(gaps[-4:]) / len(gaps[-4:])  # use last 4 gaps
    if avg <= 45:
        return 'Monthly', 30
    if avg <= 120:
        return 'Quarterly', 91
    if avg <= 240:
        return 'Semi-Annual', 182
    return 'Annual', 365


def _days_color(days: int) -> str:
    if days < 0:
        return _MUTED
    if days <= 14:
        return _GREEN
    if days <= 45:
        return _YELLOW
    return _BLUE


class _DivRow(QFrame):
    def __init__(self, ticker: str, next_date: date, amount: float,
                 freq: str, fmt_currency, parent=None) -> None:
        super().__init__(parent)
        self.setProperty('role', 'row-divider')
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 8, 0, 8)
        row.setSpacing(10)

        days = (next_date - date.today()).days

        # Days badge
        days_lbl = QLabel(f'{days:+d}d' if days != 0 else 'Today')
        days_lbl.setFixedWidth(46)
        days_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        days_lbl.setStyleSheet(
            f'color: {_days_color(days)}; font-size: 12pt; font-weight: 700; border: none;'
        )
        row.addWidget(days_lbl)

        # Ticker
        ticker_lbl = QLabel(ticker)
        ticker_lbl.setFont(_title_font(13))
        ticker_lbl.setFixedWidth(56)
        ticker_lbl.setStyleSheet('font-size: 13pt; border: none;')
        row.addWidget(ticker_lbl)

        # Date
        date_lbl = QLabel(next_date.strftime('%b %d, %Y'))
        date_lbl.setProperty('role', 'muted')
        date_lbl.setStyleSheet('font-size: 11pt; border: none;')
        row.addWidget(date_lbl, stretch=2)

        # Frequency
        freq_lbl = QLabel(freq)
        freq_lbl.setProperty('role', 'muted')
        freq_lbl.setStyleSheet('font-size: 11pt; border: none;')
        freq_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(freq_lbl, stretch=1)

        # Amount
        amt_lbl = QLabel(f'~{fmt_currency(amount)}')
        amt_lbl.setStyleSheet('font-size: 12pt; font-weight: 700; border: none;')
        amt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        amt_lbl.setFixedWidth(72)
        row.addWidget(amt_lbl)


class DividendCalendarWidget(VectorWidget):
    NAME = 'Dividend Calendar'
    DESCRIPTION = 'Estimated upcoming ex-dividend dates for held positions.'
    DEFAULT_ROWSPAN = 3
    DEFAULT_COLSPAN = 5

    def __init__(self, window=None, parent=None) -> None:
        super().__init__(window=window, parent=parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title_lbl = QLabel('Dividend Calendar')
        title_lbl.setFont(_title_font(16))
        title_lbl.setStyleSheet('font-size: 16pt; border: none;')
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._note_lbl = QLabel('estimated')
        self._note_lbl.setProperty('role', 'muted')
        self._note_lbl.setStyleSheet('font-size: 10pt; border: none;')
        header.addWidget(self._note_lbl)
        layout.addLayout(header)

        # Column headers
        col_row = QHBoxLayout()
        col_row.setContentsMargins(0, 0, 0, 0)
        col_row.setSpacing(10)
        for text, width, align in [
            ('Due', 46, Qt.AlignmentFlag.AlignCenter),
            ('Ticker', 56, Qt.AlignmentFlag.AlignLeft),
            ('Est. Date', 0, Qt.AlignmentFlag.AlignLeft),
            ('Frequency', 0, Qt.AlignmentFlag.AlignRight),
            ('Per Share', 72, Qt.AlignmentFlag.AlignRight),
        ]:
            lbl = QLabel(text)
            lbl.setProperty('role', 'muted')
            lbl.setStyleSheet('font-size: 10pt; border: none;')
            lbl.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            if width:
                lbl.setFixedWidth(width)
            col_row.addWidget(lbl, stretch=0 if width else 1)
        layout.addLayout(col_row)

        # Scrollable rows
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
        store = self._window.store
        fmt = self._window.format_currency

        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        entries: list[tuple[date, str, float, str]] = []

        for pos in positions:
            ticker = pos['ticker']
            try:
                divs = store.get_dividends(ticker)
            except Exception:  # noqa: BLE001
                continue
            if len(divs) < 2:
                continue  # need at least 2 to detect frequency

            div_dates = sorted(
                date.fromisoformat(d['date']) for d in divs if d.get('date')
            )
            last_amount = divs[-1]['amount'] if divs else 0.0
            freq_label, freq_days = _detect_frequency(div_dates)

            last_date = div_dates[-1]
            # Walk forward from last date until we find a future date
            next_date = last_date + timedelta(days=freq_days)
            today = date.today()
            while next_date < today:
                next_date += timedelta(days=freq_days)

            entries.append((next_date, ticker, last_amount, freq_label))

        if not entries:
            no_data = QLabel('No dividend data available for held positions.')
            no_data.setProperty('role', 'muted')
            no_data.setStyleSheet('font-size: 12pt; border: none;')
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._rows_layout.addWidget(no_data)
        else:
            entries.sort(key=lambda x: x[0])
            for next_date, ticker, amount, freq in entries:
                self._rows_layout.addWidget(
                    _DivRow(ticker, next_date, amount, freq, fmt)
                )

        self._rows_layout.addStretch(1)
