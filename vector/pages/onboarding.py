from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QDoubleValidator,
    QFont,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..constants import APP_NAME, COMPANY_NAME, EULA_URL
from ..eula_gate import _AcceptWorker
from ..paths import resource_path
from ..scale import sc, scpt
from ..store import DataStore
from ..widgets import BlurrableStack, CardFrame, DimOverlay, EmptyState, LoadingButton

if TYPE_CHECKING:
    from vector.app import VectorMainWindow


# ── Panel geometry ─────────────────────────────────────────────────────────────
# Lazy (function) so it is evaluated after init_scale() runs, like _CONTENT_W.
def _PANEL_W() -> int:
    return sc(640)


# ──────────────────────────────────────────────────────────────────────────────
# PositionDialog
# ──────────────────────────────────────────────────────────────────────────────

class PositionDialog(QDialog):
    def __init__(self, store: DataStore, parent: QWidget | None = None,
                 existing_tickers: 'set[str] | None' = None) -> None:
        super().__init__(parent)
        self.store = store
        self.position_data: dict[str, Any] | None = None
        # Tickers already held — submitting one of these is blocked inline.
        self.existing_tickers = {t.upper() for t in (existing_tickers or set())}
        self.setModal(True)
        self.setWindowTitle('Add Position')
        self.setMinimumWidth(sc(380))
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel('Add a portfolio position')
        title_font = QFont()
        title_font.setPointSize(scpt(15))
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f'font-size: {scpt(15)}pt;')
        subtitle = QLabel('Vector will validate the ticker with Yahoo Finance before saving it.')
        subtitle.setWordWrap(True)
        subtitle.setProperty('role', 'muted')
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        self.ticker_input = QLineEdit()
        self.ticker_input.setPlaceholderText('AAPL')
        self.ticker_input.textChanged.connect(self._uppercase_ticker)
        self.ticker_input.editingFinished.connect(self._try_update_equity_label)
        self.shares_input = QLineEdit()
        shares_validator = QDoubleValidator(0.0, 10_000_000.0, 4, self)
        shares_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.shares_input.setValidator(shares_validator)
        self.shares_input.setPlaceholderText('10')
        self.shares_input.textChanged.connect(lambda _: self._try_update_equity_label())
        form.addRow('Ticker Symbol', self.ticker_input)
        form.addRow('Number of Shares', self.shares_input)
        layout.addLayout(form)

        self.error_label = QLabel('')
        self.error_label.setStyleSheet('color: #ff6b6b;')
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        cancel_button = QPushButton('Cancel')
        cancel_button.clicked.connect(self.reject)
        self.submit_button = LoadingButton('Validate & Add')
        self.submit_button.setProperty('accent', True)
        self.submit_button.setDefault(True)
        self.submit_button.clicked.connect(self.submit)
        self.equity_label = QLabel('')
        self.equity_label.setMinimumWidth(sc(120))
        self.equity_label.setProperty('role', 'accent-info')
        self.equity_label.setStyleSheet('font-weight: bold;')
        btn_row.addWidget(cancel_button)
        btn_row.addStretch(1)
        btn_row.addWidget(self.equity_label)
        btn_row.addWidget(self.submit_button)
        layout.addLayout(btn_row)

    def _uppercase_ticker(self, text: str) -> None:
        cursor = self.ticker_input.cursorPosition()
        self.ticker_input.blockSignals(True)
        self.ticker_input.setText(text.upper())
        self.ticker_input.setCursorPosition(cursor)
        self.ticker_input.blockSignals(False)

    def _try_update_equity_label(self) -> None:
        ticker = self.ticker_input.text().strip().upper()
        shares_text = self.shares_input.text().strip()
        if not ticker or not shares_text:
            return
        try:
            shares = float(shares_text)
            if shares <= 0:
                return
        except ValueError:
            return
        price = self.store.get_quote(ticker).get('price')
        if not price:
            return
        self.equity_label.setText(f'≈ ${shares * price:,.2f}')

    def submit(self) -> None:
        ticker = self.ticker_input.text().strip().upper()
        shares_text = self.shares_input.text().strip()
        if not ticker or not shares_text:
            self.error_label.setText('Please enter a ticker and a share count.')
            return
        try:
            shares = float(shares_text)
        except ValueError:
            self.error_label.setText('Please enter a valid share count — numbers only, no special characters (, # $).')
            return
        if shares <= 0:
            self.error_label.setText('Shares must be greater than zero.')
            return
        if ticker in self.existing_tickers:
            self.error_label.setText(
                f"{ticker} is already in your portfolio — use 'Edit Selected' to change its share count."
            )
            return
        self.submit_button.start_loading('Validating...')
        self.error_label.setText('')
        QApplication.processEvents()
        try:
            snapshot = self.store.validate_ticker(ticker)
        except Exception as exc:  # noqa: BLE001
            self.submit_button.stop_loading('Validate & Add')
            self.error_label.setText(str(exc))
            return
        equity = shares * snapshot['price']
        self.position_data = {
            'ticker': snapshot['ticker'],
            'shares': shares,
            'current_price': snapshot['price'],
            'equity': equity,
            'sector': snapshot['sector'],
            'name': snapshot['name'],
        }
        self.equity_label.setText(f'≈ ${equity:,.2f}')
        QTimer.singleShot(700, self.accept)


# ──────────────────────────────────────────────────────────────────────────────
# EditPositionDialog
# ──────────────────────────────────────────────────────────────────────────────

class EditPositionDialog(QDialog):
    """Edit the share count of an existing holding. Same styling as PositionDialog."""

    def __init__(self, store: DataStore, position: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.position = position
        self.new_shares: float | None = None
        self.setModal(True)
        self.setWindowTitle('Edit Holding')
        self.setMinimumWidth(sc(380))
        self._build_ui()

    def _build_ui(self) -> None:
        ticker = self.position['ticker']
        layout = QVBoxLayout(self)
        title = QLabel(f'Edit {ticker} holding')
        title_font = QFont()
        title_font.setPointSize(scpt(15))
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f'font-size: {scpt(15)}pt;')
        subtitle = QLabel(f'How many total shares of {ticker} do you own?')
        subtitle.setWordWrap(True)
        subtitle.setProperty('role', 'muted')
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        self.shares_input = QLineEdit()
        shares_validator = QDoubleValidator(0.0, 10_000_000.0, 4, self)
        shares_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.shares_input.setValidator(shares_validator)
        self.shares_input.setPlaceholderText('10')
        current_shares = float(self.position.get('shares', 0) or 0)
        if current_shares > 0:
            self.shares_input.setText(f'{current_shares:.4f}'.rstrip('0').rstrip('.'))
        self.shares_input.textChanged.connect(lambda _: self._update_equity_label())
        form.addRow('Number of Shares', self.shares_input)
        layout.addLayout(form)

        self.error_label = QLabel('')
        self.error_label.setStyleSheet('color: #ff6b6b;')
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        cancel_button = QPushButton('Cancel')
        cancel_button.clicked.connect(self.reject)
        self.submit_button = LoadingButton('Save')
        self.submit_button.setProperty('accent', True)
        self.submit_button.setDefault(True)
        self.submit_button.clicked.connect(self.submit)
        self.equity_label = QLabel('')
        self.equity_label.setMinimumWidth(sc(120))
        self.equity_label.setProperty('role', 'accent-info')
        self.equity_label.setStyleSheet('font-weight: bold;')
        btn_row.addWidget(cancel_button)
        btn_row.addStretch(1)
        btn_row.addWidget(self.equity_label)
        btn_row.addWidget(self.submit_button)
        layout.addLayout(btn_row)
        self._update_equity_label()

    def _price_per_share(self) -> float | None:
        price = self.position.get('current_price') or self.position.get('price')
        if not price:
            price = self.store.get_quote(self.position['ticker']).get('price')
        return price or None

    def _update_equity_label(self) -> None:
        shares_text = self.shares_input.text().strip()
        if not shares_text:
            self.equity_label.setText('')
            return
        try:
            shares = float(shares_text)
        except ValueError:
            return
        if shares <= 0:
            return
        price = self._price_per_share()
        if not price:
            return
        self.equity_label.setText(f'≈ ${shares * price:,.2f}')

    def submit(self) -> None:
        shares_text = self.shares_input.text().strip()
        if not shares_text:
            self.error_label.setText('Please enter a share count.')
            return
        try:
            shares = float(shares_text)
        except ValueError:
            self.error_label.setText('Please enter a valid share count — numbers only, no special characters (, # $).')
            return
        if shares <= 0:
            self.error_label.setText('Shares must be greater than zero.')
            return
        self.new_shares = shares
        self.accept()


# ──────────────────────────────────────────────────────────────────────────────
# PositionCard
# ──────────────────────────────────────────────────────────────────────────────

class PositionCard(CardFrame):
    def __init__(self, position: dict[str, Any], currency_formatter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(sc(18), sc(18), sc(18), sc(18))
        layout.setSpacing(sc(8))
        ticker = QLabel(position['ticker'])
        ticker_font = QFont()
        ticker_font.setPointSize(scpt(18))
        ticker_font.setBold(True)
        ticker.setFont(ticker_font)
        ticker.setStyleSheet(f'font-size: {scpt(18)}pt;')
        layout.addWidget(ticker)
        for label, value in (
            ('Shares', f"{position['shares']:.4f}".rstrip('0').rstrip('.')),
            ('Current Price', currency_formatter(position['current_price'])),
            ('Equity', currency_formatter(position['equity'])),
            ('Sector', position.get('sector', 'Unknown')),
        ):
            row = QLabel(f'<b>{label}:</b> {value}')
            row.setWordWrap(True)
            layout.addWidget(row)
        layout.addStretch(1)
        self.setFixedWidth(sc(220))


# ──────────────────────────────────────────────────────────────────────────────
# Risk tier data & card
# ──────────────────────────────────────────────────────────────────────────────

_RISK_TIERS = [
    {
        'key': 'low',
        'label': 'Conservative',
        'subtitle': 'Stability first',
        'description': 'Flags risks early. Tighter thresholds, quicker action suggestions.',
        'color': '#2dd4bf',
    },
    {
        'key': 'regular',
        'label': 'Moderate',
        'subtitle': 'Balanced approach',
        'description': 'Standard thresholds. Flags meaningful risks while riding out normal swings.',
        'color': '#38bdf8',
    },
    {
        'key': 'high',
        'label': 'Aggressive',
        'subtitle': 'Growth focused',
        'description': 'Wide tolerance. Only flags serious risks — suited for high-swing portfolios.',
        'color': '#1e3a8a',
    },
]


class _RiskTierCard(QFrame):
    """Clickable card representing a single risk tier option."""

    def __init__(self, tier: dict, selected: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tier_key = tier['key']
        self._accent = tier['color']
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(sc(200))

        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(sc(20), sc(20), sc(20), sc(20))
        layout.setSpacing(sc(8))

        label = QLabel(tier['label'])
        label.setStyleSheet(f'font-size: {scpt(16)}pt; font-weight: 700; background: transparent; border: none;')
        layout.addWidget(label)

        sub = QLabel(tier['subtitle'])
        sub.setStyleSheet(f'font-size: {scpt(11)}pt; color: #8d98af; background: transparent; border: none;')
        layout.addWidget(sub)

        desc = QLabel(tier['description'])
        desc.setWordWrap(True)
        desc.setStyleSheet(f'font-size: {scpt(10)}pt; color: #6b7a94; background: transparent; border: none;')
        layout.addWidget(desc)
        layout.addStretch(1)

        if selected:
            self.set_selected(True)
        else:
            self._apply_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_style()

    def _apply_style(self) -> None:
        app = QApplication.instance()
        is_dark = app is not None and '#0b1020' in (app.styleSheet() or '')
        bg = '#161b26' if is_dark else '#ffffff'
        border_idle = '#2a3142' if is_dark else '#d0d8e8'
        if self._selected:
            self.setStyleSheet(
                f'QFrame {{ background: {bg}; border: 2px solid {self._accent}; border-radius: 14px; }}'
            )
        else:
            self.setStyleSheet(
                f'QFrame {{ background: {bg}; border: 1px solid {border_idle}; border-radius: 14px; }}'
            )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            parent = self.parentWidget()
            while parent and not isinstance(parent, OnboardingPage):
                parent = parent.parentWidget()
            if parent:
                parent._select_risk_tier(self.tier_key)


# ──────────────────────────────────────────────────────────────────────────────
# Shared QSS helpers
# ──────────────────────────────────────────────────────────────────────────────

_CARD_QSS = '''
    QFrame {{
        background-color: #151b26;
        border: 1px solid #1e3a8a;
        border-radius: 10px;
    }}
'''

_BACK_BTN_QSS = '''
    QPushButton {
        background: transparent;
        border: 1px solid #1e3a8a;
        border-radius: 10px;
        color: #8d98af;
        padding: 8px 16px;
        font-size: 12px;
    }
    QPushButton:hover {
        background: #1a2233;
        color: #c0cce0;
    }
    QPushButton:pressed {
        background: #111a2c;
    }
'''

_NEXT_BTN_QSS = '''
    QPushButton {
        background: transparent;
        border: 1px solid #38bdf8;
        border-radius: 10px;
        color: #38bdf8;
        padding: 8px 20px;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: #0d1e30;
        border-color: #5dd1ff;
        color: #5dd1ff;
    }
    QPushButton:pressed {
        background: #081624;
    }
    QPushButton:disabled {
        border-color: #2a3a4a;
        color: #3a5060;
    }
'''

_ADD_BTN_QSS = '''
    QPushButton {
        background: transparent;
        border: 1px solid #2dd4bf;
        border-radius: 10px;
        color: #2dd4bf;
        padding: 8px 20px;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: #0d1f1e;
        border-color: #4ee8d3;
        color: #4ee8d3;
    }
    QPushButton:pressed {
        background: #071412;
    }
'''


# ──────────────────────────────────────────────────────────────────────────────
# OnboardingPage
# ──────────────────────────────────────────────────────────────────────────────

class OnboardingPage(QWidget):
    def __init__(self, window: 'VectorMainWindow') -> None:
        super().__init__()
        self.window = window
        self.pending_positions: list[dict[str, Any]] = []
        self.cards_layout: QHBoxLayout | None = None
        self.launch_button: LoadingButton | None = None   # aliased to _next_btn after build
        self.overlay: DimOverlay | None = None
        self.blur_wrapper: BlurrableStack | None = None
        self._selected_risk_tier: str = 'regular'
        self._tier_cards: dict[str, _RiskTierCard] = {}
        self._current_step: int = 0
        self._dots: list[QLabel] = []
        self._connectors: list[QFrame] = []
        self._back_btn: QPushButton | None = None
        self._next_btn: LoadingButton | None = None
        self.cards_container: QWidget | None = None
        self._cards_scroll: QScrollArea | None = None
        # EULA step state. When the EULA is already accepted server-side (or no
        # backend session / a failed network check), the EULA step is left in the
        # stack but is never shown — onboarding starts on the Risk Profile step.
        self._eula_error: QLabel | None = None
        self._eula_worker: _AcceptWorker | None = None
        self._eula_required: bool = self._check_eula_required()
        self._min_step: int = 0 if self._eula_required else 1
        self._build_ui()

    # ── EULA gating ──────────────────────────────────────────────────────────

    def _check_eula_required(self) -> bool:
        """Return True only when the backend explicitly reports the EULA as not
        accepted. Fails open (returns False) for the demo bypass, a missing
        session token, or any network/parse failure — never blocks onboarding
        over a failed check."""
        token = getattr(self.window, 'token', None)
        if not token:
            return False

        # DEMO BYPASS - the demo session has no real backend token, so the legal
        # status check would always fail. Skip it and start past the EULA step.
        try:
            from auth.login_window import _DEMO_BYPASS_ENABLED, _DEMO_TOKEN
            if _DEMO_BYPASS_ENABLED and token == _DEMO_TOKEN:
                return False
        except Exception:  # noqa: BLE001
            pass
        # END DEMO BYPASS

        from auth.auth import check_eula_status
        status = check_eula_status(token)
        if status is None:
            return False  # network/parse failure — fail open
        return status.get('eula_accepted') is False

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setObjectName('onboardingPage')

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Blurrable wrapper covers entire page content
        content = QWidget()
        content.setStyleSheet('background: transparent;')
        self.blur_wrapper = BlurrableStack(content, self)
        self.overlay = DimOverlay(self)
        outer.addWidget(self.blur_wrapper)

        # Centering layout inside the blurrable content
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(sc(40), sc(40), sc(40), sc(40))
        content_layout.addStretch(1)

        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.addStretch(1)

        # ── Panel frame ───────────────────────────────────────────────────
        panel = QFrame()
        panel.setObjectName('onboardingPanel')
        panel.setFixedWidth(_PANEL_W())

        h_layout.addWidget(panel)
        h_layout.addStretch(1)
        content_layout.addLayout(h_layout)
        content_layout.addStretch(1)

        # Panel inner layout
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(sc(32), sc(28), sc(32), sc(28))
        panel_layout.setSpacing(sc(18))

        # Logo
        panel_layout.addWidget(self._build_logo(), alignment=Qt.AlignmentFlag.AlignHCenter)

        # Stepper
        panel_layout.addWidget(self._build_stepper())

        # Divider
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setProperty('role', 'divider')
        panel_layout.addWidget(sep)

        # Pages
        self._stack = QStackedWidget()
        self._stack.setMinimumHeight(sc(340))
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._stack.addWidget(self._build_step_eula())
        self._stack.addWidget(self._build_step_risk())
        self._stack.addWidget(self._build_step_portfolio())
        panel_layout.addWidget(self._stack, stretch=1)

        # Navigation footer
        panel_layout.addLayout(self._build_nav())

        # Alias so existing internal callers of launch_button still work
        self.launch_button = self._next_btn

        # Spacebar advances the flow (works regardless of focused child)
        space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        space_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        space_shortcut.activated.connect(self._on_space_shortcut)

        # Initialise to the first navigable step (skips EULA when already accepted)
        self._go_to(self._min_step)

    def _on_space_shortcut(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit):
            return
        if self._next_btn is not None and self._next_btn.isEnabled():
            self._on_next()

    def _build_logo(self) -> QLabel:
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet('border: none; background: transparent;')
        try:
            px = QPixmap(str(resource_path('assets', 'vector_full.png')))
            if not px.isNull():
                px = px.scaledToHeight(sc(44), Qt.TransformationMode.SmoothTransformation)
                lbl.setPixmap(px)
                return lbl
        except Exception:  # noqa: BLE001
            pass
        lbl.setText(APP_NAME)
        f = QFont()
        f.setPointSize(scpt(18))
        f.setBold(True)
        lbl.setFont(f)
        return lbl

    def _build_stepper(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet('background: transparent;')
        row = QHBoxLayout(container)
        row.setContentsMargins(sc(8), sc(4), sc(8), sc(4))
        row.setSpacing(0)

        step_names = ['EULA', 'Risk Profile', 'Portfolio Setup']

        for i, name in enumerate(step_names):
            # Column: dot above, label below
            col_widget = QWidget()
            col_widget.setStyleSheet('background: transparent;')
            col = QVBoxLayout(col_widget)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(sc(5))
            col.setAlignment(Qt.AlignmentFlag.AlignHCenter)

            dot = QLabel(str(i + 1))
            dot.setFixedSize(sc(28), sc(28))
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            f = QFont()
            f.setPointSize(scpt(10))
            f.setBold(True)
            dot.setFont(f)
            self._dots.append(dot)
            col.addWidget(dot, alignment=Qt.AlignmentFlag.AlignHCenter)

            name_lbl = QLabel(name)
            nf = QFont()
            nf.setPointSize(scpt(8))
            name_lbl.setFont(nf)
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            name_lbl.setProperty('role', 'muted')
            name_lbl.setStyleSheet('background: transparent; border: none;')
            col.addWidget(name_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

            row.addWidget(col_widget, 0, Qt.AlignmentFlag.AlignVCenter)

            if i < len(step_names) - 1:
                # Connector — sits at the same vertical level as the dot centres
                line_wrap = QWidget()
                line_wrap.setStyleSheet('background: transparent;')
                lw_layout = QVBoxLayout(line_wrap)
                lw_layout.setContentsMargins(0, 0, 0, 0)
                lw_layout.setSpacing(0)
                # Push line down by half a dot to align with dot centre
                lw_layout.addSpacing(sc(14))
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFixedHeight(2)
                self._connectors.append(line)
                lw_layout.addWidget(line)
                lw_layout.addStretch(1)
                row.addWidget(line_wrap, 1)   # stretch=1 fills space between dots

        return container

    def _build_nav(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(sc(12))

        self._back_btn = QPushButton('← Back')
        self._back_btn.setFixedWidth(sc(110))
        self._back_btn.setStyleSheet(_BACK_BTN_QSS)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(lambda: self._go_to(self._current_step - 1))
        layout.addWidget(self._back_btn)

        layout.addStretch(1)

        self._next_btn = LoadingButton('Skip for now')
        self._next_btn.setStyleSheet(_NEXT_BTN_QSS)
        self._next_btn.setMinimumWidth(sc(170))
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self._on_next)
        layout.addWidget(self._next_btn)

        return layout

    # ── Step pages ────────────────────────────────────────────────────────

    def _build_step_eula(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet('background: transparent;')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, sc(4), 0, sc(4))
        layout.setSpacing(sc(6))

        title = QLabel('End User License Agreement')
        tf = QFont(); tf.setPointSize(scpt(17)); tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet('color: #e8eaf0; border: none;')
        layout.addWidget(title)

        subtitle = QLabel('Please review and accept our End User License Agreement to continue.')
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f'color: #6b7280; font-size: {sc(12)}px; border: none;')
        layout.addWidget(subtitle)

        layout.addSpacing(sc(12))

        card = QFrame()
        card.setStyleSheet(_CARD_QSS)
        card.setMinimumHeight(sc(200))
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(sc(24), sc(24), sc(24), sc(24))
        card_layout.setSpacing(sc(14))

        body = QLabel(
            'By continuing you agree to the terms of the Vector End User License '
            'Agreement. Please read the full agreement before accepting.'
        )
        body.setWordWrap(True)
        body.setStyleSheet(
            f'color: #c0cce0; font-size: {sc(13)}px; border: none; background: transparent;'
        )
        card_layout.addWidget(body)

        # Flat text link that opens the EULA in the system browser.
        link = QPushButton('Read the End User License Agreement')
        link.setObjectName('eulaLink')
        link.setFlat(True)
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        link.setStyleSheet(
            'QPushButton#eulaLink {'
            ' background: transparent;'
            ' border: none;'
            ' color: #2dd4bf;'
            f' font-size: {scpt(12)}pt;'
            ' text-align: left;'
            ' padding: 0px;'
            ' }'
            'QPushButton#eulaLink:hover { color: #4ee8d3; }'
        )
        link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(EULA_URL)))
        card_layout.addWidget(link, alignment=Qt.AlignmentFlag.AlignLeft)

        self._eula_error = QLabel('')
        self._eula_error.setWordWrap(True)
        self._eula_error.setStyleSheet(
            f'color: #ff6b6b; font-size: {sc(12)}px; border: none; background: transparent;'
        )
        self._eula_error.hide()
        card_layout.addWidget(self._eula_error)

        card_layout.addStretch(1)
        layout.addWidget(card, stretch=1)

        return page

    def _build_step_risk(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet('background: transparent;')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, sc(4), 0, sc(4))
        layout.setSpacing(sc(6))

        title = QLabel('How do you want to invest?')
        tf = QFont(); tf.setPointSize(scpt(17)); tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet('color: #e8eaf0; border: none;')
        layout.addWidget(title)

        subtitle = QLabel(
            'This shapes how aggressively the Lens flags risks and suggests '
            'actions. You can change this later in Settings.'
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f'color: #6b7280; font-size: {sc(12)}px; border: none;')
        layout.addWidget(subtitle)

        layout.addSpacing(sc(12))

        tier_frame = QFrame()
        tier_frame.setStyleSheet(_CARD_QSS)
        tier_inner = QHBoxLayout(tier_frame)
        tier_inner.setContentsMargins(sc(16), sc(16), sc(16), sc(16))
        tier_inner.setSpacing(sc(12))

        for tier in _RISK_TIERS:
            card = _RiskTierCard(tier, selected=(tier['key'] == 'regular'))
            self._tier_cards[tier['key']] = card
            tier_inner.addWidget(card)

        layout.addWidget(tier_frame, stretch=1)

        return page

    def _build_step_portfolio(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet('background: transparent;')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, sc(4), 0, sc(4))
        layout.setSpacing(sc(6))

        title = QLabel('Add Your Positions')
        tf = QFont(); tf.setPointSize(scpt(17)); tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet('color: #e8eaf0; border: none;')
        layout.addWidget(title)

        subtitle = QLabel(
            'Add one or more holdings to get started. '
            'Vector validates each ticker with Yahoo Finance.'
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f'color: #6b7280; font-size: {sc(12)}px; border: none;')
        layout.addWidget(subtitle)

        layout.addSpacing(sc(8))

        add_btn = QPushButton('Add Position  (a)')
        add_btn.setStyleSheet(_ADD_BTN_QSS)
        add_btn.setFixedWidth(sc(200))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self.open_add_modal)
        layout.addWidget(add_btn)

        layout.addSpacing(sc(6))

        # Cards scroll area inside a styled frame — horizontal scroll only
        cards_frame = QFrame()
        cards_frame.setStyleSheet(_CARD_QSS)
        cards_frame.setMinimumHeight(sc(170))
        cards_frame.setMaximumHeight(sc(230))
        cf_layout = QVBoxLayout(cards_frame)
        cf_layout.setContentsMargins(sc(6), sc(6), sc(6), sc(6))
        cf_layout.setSpacing(0)

        cards_scroll = QScrollArea()
        cards_scroll.setWidgetResizable(True)    # fills height; minWidth drives hscroll
        cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        cards_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        cards_scroll.setStyleSheet('background: transparent;')

        # Route mouse wheel to the horizontal scrollbar so the user can scroll
        # the horizontally-laid-out position cards with the wheel.
        def _horizontal_wheel(event, scroll=cards_scroll):
            bar = scroll.horizontalScrollBar()
            if bar.maximum() == 0:
                event.ignore()
                return
            delta = event.angleDelta().y() or event.angleDelta().x()
            if delta == 0:
                event.ignore()
                return
            # Qt: 120 units per notch; scroll by roughly one card per notch
            step = int(-delta / 120 * 80)
            bar.setValue(bar.value() + step)
            event.accept()
        cards_scroll.wheelEvent = _horizontal_wheel

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet('background: transparent;')
        self.cards_layout = QHBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(sc(8), sc(8), sc(8), sc(8))
        self.cards_layout.setSpacing(sc(12))
        self.cards_layout.addWidget(
            EmptyState(
                'No positions yet',
                'Add at least one validated holding to unlock the portfolio dashboard.',
            )
        )

        cards_scroll.setWidget(self.cards_container)
        self._cards_scroll = cards_scroll
        cf_layout.addWidget(cards_scroll)
        layout.addWidget(cards_frame, stretch=1)

        return page

    # ── Navigation logic ───────────────────────────────────────────────────

    def _go_to(self, step: int) -> None:
        # Clamp the lower bound to _min_step so an already-accepted EULA step
        # (left in the stack but skipped) can never be navigated back to.
        self._current_step = max(self._min_step, min(self._stack.count() - 1, step))
        self._stack.setCurrentIndex(self._current_step)
        self._refresh_stepper()
        self._refresh_nav()

    def _refresh_stepper(self) -> None:
        # Each dot samples the app gradient at an evenly spaced position:
        # Dot 1 -> 0% (#2dd4bf), Dot 2 -> 50% (#38bdf8), Dot 3 -> 100% (#1e3a8a)
        _dot_colors = ['#2dd4bf', '#38bdf8', '#1e3a8a']
        _lit_tpl = 'background: {color}; color: #ffffff; border: none; border-radius: 14px;'
        _idle = (
            'background: #1e2a3a;'
            ' border: none;'
            ' color: #4b5563;'
            ' border-radius: 14px;'
        )

        for i, dot in enumerate(self._dots):
            if i <= self._current_step:
                dot.setStyleSheet(_lit_tpl.format(color=_dot_colors[i]))
            else:
                dot.setStyleSheet(_idle)

        _app = QApplication.instance()
        _is_dark = _app is not None and '#0b1020' in (_app.styleSheet() or '')
        _active_line = '#38bdf8' if _is_dark else '#2dd4bf'
        _idle_line = '#2a3040' if _is_dark else '#d0d8e8'
        for i, connector in enumerate(self._connectors):
            if i < self._current_step:
                connector.setStyleSheet(f'background: {_active_line};')
            else:
                connector.setStyleSheet(f'background: {_idle_line};')

    def _refresh_nav(self) -> None:
        if not self._back_btn or not self._next_btn:
            return

        self._back_btn.setVisible(self._current_step > self._min_step)

        last = self._stack.count() - 1
        if self._current_step == 0 and self._eula_required:
            # EULA step (only ever shown when acceptance is required).
            self._next_btn.setText('I Accept')
            self._next_btn.setEnabled(True)
        elif self._current_step == last:
            self._next_btn.setText('Launch Portfolio')
            self._next_btn.setEnabled(bool(self.pending_positions))
        elif self._current_step == last - 1:
            self._next_btn.setText('Continue')
            self._next_btn.setEnabled(True)
        else:
            self._next_btn.setText('Skip for now')
            self._next_btn.setEnabled(True)

    def _on_next(self) -> None:
        # On the EULA step, "I Accept" records acceptance server-side before
        # advancing — the step is only navigable when _eula_required is True.
        if self._current_step == 0 and self._eula_required:
            self._accept_eula()
            return
        if self._current_step < self._stack.count() - 1:
            self._go_to(self._current_step + 1)
        else:
            self.launch()

    # ── EULA acceptance ─────────────────────────────────────────────────────

    def _accept_eula(self) -> None:
        if self._eula_worker is not None:
            return
        token = getattr(self.window, 'token', None)
        if not token:
            # No backend session to record against — advance without blocking.
            self._eula_required = False
            self._min_step = 1
            self._go_to(1)
            return
        if self._eula_error is not None:
            self._eula_error.hide()
        self._next_btn.start_loading('Accepting...')
        QApplication.processEvents()
        worker = _AcceptWorker(token, 'eula')
        worker.done.connect(self._on_eula_accept_done)
        worker.finished.connect(worker.deleteLater)
        self._eula_worker = worker
        worker.start()

    def _on_eula_accept_done(self, status: str) -> None:
        self._eula_worker = None
        if status == 'ok':
            # Accepted server-side: lock the EULA step behind us and advance.
            self._eula_required = False
            self._min_step = 1
            self._next_btn.stop_loading('Continue')
            self._go_to(1)
        elif status == 'unauthorized':
            # Session expired mid-run: drop the token and quit so the user
            # re-authenticates on the next launch (mirrors the legal gate).
            from auth.auth import clear_token
            try:
                clear_token()
            except Exception:  # noqa: BLE001
                pass
            QApplication.quit()
        else:
            self._next_btn.stop_loading('I Accept')
            if self._eula_error is not None:
                self._eula_error.setText(
                    'Unable to connect. Please check your internet connection and try again.'
                )
                self._eula_error.show()

    # ── Event overrides ────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._current_step == self._stack.count() - 1 and event.key() == Qt.Key.Key_A:
            self.open_add_modal()
            return
        if event.key() == Qt.Key.Key_Space:
            if self._next_btn is not None and self._next_btn.isEnabled():
                self._on_next()
                return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        if self.overlay:
            self.overlay.sync_geometry()
        super().resizeEvent(event)

    # ── Position management ────────────────────────────────────────────────

    def open_add_modal(self) -> None:
        if self.blur_wrapper and self.overlay:
            self.blur_wrapper.set_blurred(True)
            self.overlay.show()
        existing = {p['ticker'].upper() for p in self.pending_positions}
        dialog = PositionDialog(self.window.store, self, existing_tickers=existing)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted and dialog.position_data
        if accepted:
            self.pending_positions.append(dialog.position_data)
        if self.blur_wrapper and self.overlay:
            self.blur_wrapper.set_blurred(False)
            self.overlay.hide()
        if accepted:
            self.refresh_cards()

    def refresh_cards(self) -> None:
        if not self.cards_layout or not self.cards_container or not self._next_btn:
            return
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not self.pending_positions:
            self.cards_layout.addWidget(
                EmptyState(
                    'No positions yet',
                    'Add at least one validated holding to unlock the portfolio dashboard.',
                )
            )
        for position in self.pending_positions:
            self.cards_layout.addWidget(PositionCard(position, self.window.format_currency))
        self.cards_layout.addStretch(1)
        # Drive horizontal scrolling: set the container's minimum width to the
        # real (scaled) content width so the scroll area exposes a scrollbar and
        # the cards keep their gaps. Must use sc() — the cards are sc(220) wide
        # with sc(12) spacing inside sc(8) margins, so a raw-pixel sum under-sizes
        # the container at any scale != 1 and the gaps/scroll collapse.
        n = len(self.pending_positions)
        if n > 0:
            natural_w = 2 * sc(8) + n * sc(220) + (n - 1) * sc(12)
            self.cards_container.setMinimumWidth(natural_w)
        else:
            self.cards_container.setMinimumWidth(0)
        if self._current_step == self._stack.count() - 1:
            self._next_btn.setEnabled(bool(self.pending_positions))
        # Settle the layout now so the scroll area recomputes its scrollbar range
        # immediately instead of waiting for an incidental repaint — this keeps
        # the keyboard-add ("a") and click-add paths visually identical.
        self.cards_layout.activate()
        self.cards_container.adjustSize()
        self.cards_container.updateGeometry()
        if self._cards_scroll is not None:
            self._cards_scroll.updateGeometry()
        self.cards_container.update()

    def _select_risk_tier(self, tier_key: str) -> None:
        self._selected_risk_tier = tier_key
        for key, card in self._tier_cards.items():
            card.set_selected(key == tier_key)

    # ── Launch ─────────────────────────────────────────────────────────────

    def launch(self) -> None:
        self._next_btn.start_loading('Launching...')
        QApplication.processEvents()
        self.window.positions = list(self.pending_positions)
        self.window.store.save_positions(self.window.positions)
        self.window.settings['risk_tier'] = self._selected_risk_tier
        self.window.store.save_settings(self.window.settings)
        state = self.window.store.load_app_state()
        state['onboarding_complete'] = True
        state['risk_tier_selected'] = True
        self.window.store.save_app_state(state)
        self.window.load_main_shell()
