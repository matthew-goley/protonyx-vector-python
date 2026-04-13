import re

from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
from PyQt6.QtGui import QFont, QColor, QFontMetrics, QLinearGradient, QPainter, QPen
from PyQt6.QtCore import Qt, QRect, QRectF, QTimer, pyqtSignal

from vector.lens_engine import generate_lens

_MUTED      = '#8d98af'
_BG         = '#121828'
_GRAD_START = '#2dd4bf'
_GRAD_MID   = '#38bdf8'
_GRAD_END   = '#1e3a8a'

# Sector names → mid gradient
_SECTORS = {
    'Technology', 'Healthcare', 'Financial Services', 'Financials',
    'Consumer Cyclical', 'Consumer Defensive', 'Energy', 'Industrials',
    'Communication Services', 'Utilities', 'Real Estate', 'Basic Materials', 'ETF',
}

# Financial/portfolio terms → mid gradient
_FINANCIAL_TERMS = {
    'earnings', 'volatility', 'momentum', 'compounding', 'downtrend', 'uptrend',
    'rebalance', 'rebalancing', 'diversify', 'diversification', 'concentration',
    'drawdown', 'correction', 'rally', 'selloff', 'pullback', 'rotation',
    'allocation', 'exposure', 'risk', 'gains', 'losses', 'returns',
    'appreciation', 'depreciation', 'correlation', 'trajectory', 'performance',
    'trend', 'momentum', 'thesis', 'catalyst',
}

# Multi-word action phrases → blue gradient (processed before tokenizing)
_ACTION_PHRASES = [
    'next deposit', 'next buy', 'new money', 'new cash',
    'future deposits', 'next paycheck', 'regular deposits',
    'consistent deposits', 'next move',
]


def _wrap(text: str, color: str) -> str:
    return f'<span style="color:{color};">{text}</span>'


def _apply_to_text(s: str, fn) -> str:
    """Apply fn only to text nodes — skip existing HTML tags."""
    parts = re.split(r'(<[^>]*>)', s)
    return ''.join(fn(p) if not p.startswith('<') else p for p in parts)


def _highlight_html(text: str) -> str:
    """
    Return HTML where important parts are gradient-colored:
      - ticker symbols (ALL-CAPS 2-5 letters)  → teal  #2dd4bf
      - known sector names                      → mid   #38bdf8
      - financial / portfolio terms             → mid   #38bdf8
      - action phrases ("next deposit" etc.)    → teal  #2dd4bf
      - numbers / percentages / $ amounts       → navy  #1e3a8a
      - everything else                         → white #e7ebf3
    """
    s = (text
         .replace('&', '&amp;')
         .replace('<', '&lt;')
         .replace('>', '&gt;'))

    # 1. Multi-word action phrases → blue (before word-level processing)
    for phrase in sorted(_ACTION_PHRASES, key=len, reverse=True):
        s = _apply_to_text(s, lambda chunk, p=phrase: re.sub(
            rf'\b({re.escape(p)})\b',
            lambda m: _wrap(m.group(), _GRAD_START),
            chunk, flags=re.IGNORECASE,
        ))

    # 2. Numbers, percentages, dollar amounts → sky-blue
    s = _apply_to_text(s, lambda chunk: re.sub(
        r'([+\-]?\$?[\d,]+\.?\d*\s*%|[+\-]?\$[\d,]+\.?\d*|\b\d+\.?\d*\b)',
        lambda m: _wrap(m.group(), _GRAD_MID) if re.search(r'\d', m.group()) else m.group(),
        chunk,
    ))

    # 3. Sector names → mid (longest first to avoid partial matches)
    for sector in sorted(_SECTORS, key=len, reverse=True):
        s = _apply_to_text(s, lambda chunk, sec=sector: re.sub(
            rf'\b({re.escape(sec)})\b',
            lambda m: _wrap(m.group(), _GRAD_MID),
            chunk,
        ))

    # 4. Financial terms → mid
    if _FINANCIAL_TERMS:
        pattern = '|'.join(re.escape(t) for t in sorted(_FINANCIAL_TERMS, key=len, reverse=True))
        s = _apply_to_text(s, lambda chunk: re.sub(
            rf'\b({pattern})\b',
            lambda m: _wrap(m.group(), _GRAD_MID),
            chunk, flags=re.IGNORECASE,
        ))

    # 5. ALL-CAPS tickers (2–5 letters, optional hyphenated suffix like BRK-B) → blue
    s = _apply_to_text(s, lambda chunk: re.sub(
        r'\b([A-Z]{2,5}(?:-[A-Z]{1,2})?)\b',
        lambda m: _wrap(m.group(), _GRAD_START),
        chunk,
    ))

    return s


def _font(size: int, bold: bool = True) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    return f


class _AccentFrame(QFrame):
    """Card with a teal→navy gradient left accent bar and border."""

    def paintEvent(self, _event) -> None:  # noqa: N802
        from PyQt6.QtWidgets import QApplication
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        app = QApplication.instance()
        is_dark = app is not None and '#0b1020' in (app.styleSheet() or '')
        bg = _BG if is_dark else '#f8faff'
        painter.setBrush(QColor(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(self.rect()), 12, 12)
        bar_grad = QLinearGradient(0, 16, 0, h - 16)
        bar_grad.setColorAt(0.0, QColor(_GRAD_START))
        bar_grad.setColorAt(0.5, QColor(_GRAD_MID))
        bar_grad.setColorAt(1.0, QColor(_GRAD_END))
        painter.setBrush(bar_grad)
        painter.drawRoundedRect(QRectF(0, 16, 4, h - 32), 2, 2)
        border_grad = QLinearGradient(0, 0, 0, h)
        c0 = QColor(_GRAD_START); c0.setAlpha(80)
        c1 = QColor(_GRAD_END);   c1.setAlpha(80)
        border_grad.setColorAt(0.0, c0)
        border_grad.setColorAt(0.5, QColor(_GRAD_MID))
        border_grad.setColorAt(1.0, c1)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(border_grad, 1))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, h - 1), 12, 12)


class LensDisplay(QFrame):
    """Reusable lens readout — used on both the dashboard and the Vector Lens page."""

    open_lens_clicked = pyqtSignal()

    def __init__(self, window=None, show_button: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._window = window
        self._show_button = show_button

        self._tw_timer = QTimer(self)
        self._tw_timer.setInterval(5)
        self._tw_timer.timeout.connect(self._tw_step)
        self._tw_plain = ''
        self._tw_html  = ''
        self._tw_pos   = 0
        self._recommended_tickers: list[str] = []
        self._deposit_amount: float = 0.0
        self._underweight_sector: str = ''
        self._action_type: str = 'hold'
        self._caution_score: int = 0

        self.setStyleSheet('background: transparent; border: none;')

        self._card = _AccentFrame(self)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(10)

        title_lbl = QLabel('Lens Brief')
        title_lbl.setFont(_font(16, bold=True))
        title_lbl.setStyleSheet('font-size: 16pt; border: none;')
        card_layout.addWidget(title_lbl)

        self._text_lbl = QLabel('')
        self._text_lbl.setWordWrap(True)
        self._text_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._text_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._text_lbl.setStyleSheet(
            'border: none; font-size: 18pt; font-weight: 700;'
        )
        card_layout.addWidget(self._text_lbl, stretch=1)

        if show_button:
            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            self._open_btn = QPushButton('Vector Lens  \u203a')
            self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._open_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #2dd4bf, stop:0.5 #38bdf8, stop:1 #1e3a8a);
                    color: #ffffff;
                    border: none;
                    border-radius: 10px;
                    padding: 8px 18px;
                    font-size: 11pt;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #4ee8d3, stop:0.5 #5dd1ff, stop:1 #2d52b2);
                }
            """)
            self._open_btn.clicked.connect(self.open_lens_clicked.emit)
            btn_row.addWidget(self._open_btn)
            card_layout.addLayout(btn_row)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)

    def _available_size(self) -> tuple[int, int]:
        """Return (width, height) available for text, using the best source."""
        w = self._text_lbl.width()
        h = self._text_lbl.height()
        if w >= 20 and h >= 20:
            return w, h
        cw = max(self._card.width(), self.width())
        ch = max(self._card.height(), self.height())
        return max(cw - 56, 200), max(ch - 88, 60)

    def _fit_pt(self, text: str) -> int:
        """Find the largest pt size where wrapped text fully fits with no clipping."""
        w, h = self._available_size()

        for pt in range(28, 9, -1):
            fm = QFontMetrics(_font(pt))
            br = fm.boundingRect(
                QRect(0, 0, w, 10000),
                Qt.TextFlag.TextWordWrap,
                text,
            )
            if br.height() <= int(h * 0.80):
                return pt
        return 10

    def _apply_font(self, pt: int) -> None:
        self._text_lbl.setStyleSheet(
            f'border: none; font-size: {pt}pt; font-weight: 700;'
        )

    def _refit(self) -> None:
        """Recalculate font size and update displayed text."""
        if not self._tw_plain:
            return
        pt = self._fit_pt(self._tw_plain)
        self._apply_font(pt)
        if not self._tw_timer.isActive():
            self._text_lbl.setTextFormat(Qt.TextFormat.RichText)
            self._text_lbl.setText(self._tw_html)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._card.setGeometry(self.rect())
        self._refit()
        super().resizeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        """Refit on first show — layout is now finalized so dimensions are accurate."""
        super().showEvent(event)
        self._card.setGeometry(self.rect())
        QTimer.singleShot(0, self._refit)

    @staticmethod
    def _truncate_html(html: str, visible_chars: int) -> str:
        """Truncate HTML to show only the first N visible characters, preserving tags."""
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

    def _ensure_tw_timer(self) -> None:
        """Recreate _tw_timer if its underlying C++ object has been deleted."""
        try:
            self._tw_timer.isActive()
        except RuntimeError:
            self._tw_timer = QTimer(self)
            self._tw_timer.setInterval(5)
            self._tw_timer.timeout.connect(self._tw_step)

    def _tw_step(self) -> None:
        self._tw_pos += 1
        truncated = self._truncate_html(self._tw_html, self._tw_pos)
        try:
            self._text_lbl.setTextFormat(Qt.TextFormat.RichText)
            self._text_lbl.setText(truncated)
        except RuntimeError:
            self._ensure_tw_timer()
            self._tw_timer.stop()
            return
        if self._tw_pos >= len(self._tw_plain):
            self._ensure_tw_timer()
            self._tw_timer.stop()

    def _start_typewrite(self, plain: str) -> None:
        self._ensure_tw_timer()
        self._tw_timer.stop()
        self._tw_plain = plain
        self._tw_html  = _highlight_html(plain)
        self._tw_pos   = 0
        pt = self._fit_pt(plain)
        self._text_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._apply_font(pt)
        self._text_lbl.setText('')
        self._tw_timer.start()

    def refresh(self) -> None:
        if not self._window:
            return

        positions = self._window.positions or []
        store     = self._window.store
        settings  = self._window.settings

        try:
            result = generate_lens(positions, store, settings)
            if len(result) == 7:
                text, _color, self._recommended_tickers, self._deposit_amount, self._underweight_sector, self._action_type, self._caution_score = result
            elif len(result) == 6:
                text, _color, self._recommended_tickers, self._deposit_amount, self._underweight_sector, self._action_type = result
                self._caution_score = 0
            elif len(result) == 5:
                text, _color, self._recommended_tickers, self._deposit_amount, self._underweight_sector = result
                self._action_type = 'hold'
            elif len(result) == 4:
                text, _color, self._recommended_tickers, self._deposit_amount = result
                self._underweight_sector = ''
                self._action_type = 'hold'
            elif len(result) == 3:
                text, _color, self._recommended_tickers = result
                self._deposit_amount = 0.0
                self._underweight_sector = ''
                self._action_type = 'hold'
            else:
                text, _color = result
                self._recommended_tickers = []
                self._deposit_amount = 0.0
                self._underweight_sector = ''
                self._action_type = 'hold'
        except Exception:  # noqa: BLE001
            text = "Unable to generate a lens insight right now. Check your positions and try refreshing."
            self._recommended_tickers = []
            self._deposit_amount = 0.0
            self._underweight_sector = ''
            self._action_type = 'hold'

        self._start_typewrite(text)
