from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QDoubleValidator, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..constants import APP_NAME, COMPANY_NAME
from ..store import DataStore
from ..widgets import BlurrableStack, CardFrame, DimOverlay, EmptyState, LoadingButton

if TYPE_CHECKING:
    from vector.app import VectorMainWindow


class PositionDialog(QDialog):
    def __init__(self, store: DataStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.position_data: dict[str, Any] | None = None
        self.setModal(True)
        self.setWindowTitle('Add Position')
        self.setMinimumWidth(380)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel('Add a portfolio position')
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet('font-size: 15pt;')
        subtitle = QLabel('Vector will validate the ticker with Yahoo Finance before saving it.')
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet('color: #8d98af;')
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        self.ticker_input = QLineEdit()
        self.ticker_input.setPlaceholderText('AAPL')
        self.ticker_input.textChanged.connect(self._uppercase_ticker)
        self.ticker_input.editingFinished.connect(self._try_update_equity_label)
        self.shares_input = QLineEdit()
        self.shares_input.setValidator(QDoubleValidator(0.0, 10_000_000.0, 4, self))
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
        self.equity_label.setMinimumWidth(120)
        self.equity_label.setStyleSheet('color: #a0c8ff; font-weight: bold;')
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
        """Show an estimated equity from cached price as soon as both fields are filled."""
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
        shares = float(shares_text)
        if shares <= 0:
            self.error_label.setText('Shares must be greater than zero.')
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


class PositionCard(CardFrame):
    def __init__(self, position: dict[str, Any], currency_formatter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(8)
        ticker = QLabel(position['ticker'])
        ticker_font = QFont()
        ticker_font.setPointSize(18)
        ticker_font.setBold(True)
        ticker.setFont(ticker_font)
        ticker.setStyleSheet('font-size: 18pt;')
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
        self.setFixedWidth(220)


_RISK_TIERS = [
    {
        'key': 'low',
        'label': 'Conservative',
        'subtitle': 'Prioritize stability over growth',
        'description': (
            'Tighter guardrails. The Lens will flag smaller dips, lower '
            'volatility, and suggest action sooner. Best if you prefer '
            'steady, predictable returns.'
        ),
        'color': '#4da6ff',
    },
    {
        'key': 'regular',
        'label': 'Moderate',
        'subtitle': 'Balance between growth and safety',
        'description': (
            'Standard thresholds. The Lens gives you room to ride out '
            'normal market swings but flags meaningful risks. Good for '
            'most investors.'
        ),
        'color': '#a256f6',
    },
    {
        'key': 'high',
        'label': 'Aggressive',
        'subtitle': 'Maximize growth potential',
        'description': (
            'Wider guardrails. The Lens tolerates higher volatility and '
            'steeper dips before flagging anything. Best if you\'re '
            'comfortable with big swings for bigger potential upside.'
        ),
        'color': '#fd8a83',
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
        self.setFixedHeight(200)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        label = QLabel(tier['label'])
        label.setStyleSheet('font-size: 16pt; font-weight: 700; background: transparent; border: none;')
        layout.addWidget(label)

        sub = QLabel(tier['subtitle'])
        sub.setStyleSheet('font-size: 11pt; color: #8d98af; background: transparent; border: none;')
        layout.addWidget(sub)

        desc = QLabel(tier['description'])
        desc.setWordWrap(True)
        desc.setStyleSheet('font-size: 10pt; color: #6b7a94; background: transparent; border: none;')
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
        if self._selected:
            self.setStyleSheet(
                f'_RiskTierCard {{ background: #161b26; border: 2px solid {self._accent}; border-radius: 14px; }}'
            )
        else:
            self.setStyleSheet(
                '_RiskTierCard { background: #161b26; border: 1px solid #2a3142; border-radius: 14px; }'
            )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            # Notify parent to update selection
            parent = self.parentWidget()
            while parent and not isinstance(parent, OnboardingPage):
                parent = parent.parentWidget()
            if parent:
                parent._select_risk_tier(self.tier_key)


class OnboardingPage(QWidget):
    def __init__(self, window: 'VectorMainWindow') -> None:
        super().__init__()
        self.window = window
        self.pending_positions: list[dict[str, Any]] = []
        self.cards_layout: QHBoxLayout | None = None
        self.launch_button: QPushButton | None = None
        self.overlay: DimOverlay | None = None
        self.blur_wrapper: BlurrableStack | None = None
        self._selected_risk_tier: str = 'regular'
        self._tier_cards: dict[str, _RiskTierCard] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(16)

        content = QWidget()
        self.blur_wrapper = BlurrableStack(content, self)
        self.overlay = DimOverlay(self)
        outer.addWidget(self.blur_wrapper)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Use a scroll area so content is never clipped on small windows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(20)
        inner_layout.addStretch(1)

        title = QLabel(f'Welcome to {APP_NAME}')
        title_font = QFont()
        title_font.setPointSize(26)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet('font-size: 26pt;')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel(
            f'{COMPANY_NAME} {APP_NAME} needs your first positions to begin tracking portfolio analytics. Add one or more holdings to get started.'
        )
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setMaximumWidth(720)
        subtitle.setMinimumHeight(48)
        subtitle.setStyleSheet('color: #90a0bb;')
        inner_layout.addWidget(title)
        inner_layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)

        add_button = LoadingButton('Add Position  (a)')
        add_button.setProperty('accent', True)
        add_button.setFixedWidth(210)
        add_button.clicked.connect(self.open_add_modal)
        inner_layout.addWidget(add_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        cards_scroll = QScrollArea()
        cards_scroll.setWidgetResizable(True)
        cards_scroll.setMinimumHeight(250)
        self.cards_container = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(8, 8, 8, 8)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addWidget(EmptyState('No positions yet', 'Add at least one validated holding to unlock the portfolio dashboard.'))
        cards_scroll.setWidget(self.cards_container)
        inner_layout.addWidget(cards_scroll)

        # ── Risk tier selection ──
        risk_card = CardFrame()
        risk_layout = QVBoxLayout(risk_card)
        risk_layout.setContentsMargins(24, 24, 24, 24)
        risk_layout.setSpacing(12)

        risk_title = QLabel('How do you want to invest?')
        risk_title_font = QFont()
        risk_title_font.setPointSize(18)
        risk_title_font.setBold(True)
        risk_title.setFont(risk_title_font)
        risk_title.setStyleSheet('font-size: 18pt;')
        risk_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        risk_layout.addWidget(risk_title)

        risk_subtitle = QLabel(
            'This shapes how aggressively the Lens flags risks and suggests actions. '
            'You can change this later in Settings.'
        )
        risk_subtitle.setWordWrap(True)
        risk_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        risk_subtitle.setStyleSheet('color: #8d98af;')
        risk_layout.addWidget(risk_subtitle)

        tier_row = QHBoxLayout()
        tier_row.setSpacing(14)
        for tier in _RISK_TIERS:
            card = _RiskTierCard(tier, selected=(tier['key'] == 'regular'))
            self._tier_cards[tier['key']] = card
            tier_row.addWidget(card)
        risk_layout.addLayout(tier_row)
        inner_layout.addWidget(risk_card)

        self.launch_button = LoadingButton('Launch Portfolio')
        self.launch_button.setProperty('accent', True)
        self.launch_button.setEnabled(False)
        self.launch_button.setFixedWidth(220)
        self.launch_button.clicked.connect(self.launch)
        inner_layout.addWidget(self.launch_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        inner_layout.addStretch(1)

        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_A:
            self.open_add_modal()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        if self.overlay:
            self.overlay.sync_geometry()
        super().resizeEvent(event)

    def open_add_modal(self) -> None:
        if self.blur_wrapper and self.overlay:
            self.blur_wrapper.set_blurred(True)
            self.overlay.show()
        dialog = PositionDialog(self.window.store, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted and dialog.position_data
        if accepted:
            self.pending_positions.append(dialog.position_data)
        if self.blur_wrapper and self.overlay:
            self.blur_wrapper.set_blurred(False)
            self.overlay.hide()
        if accepted:
            self.refresh_cards()

    def refresh_cards(self) -> None:
        if not self.cards_layout or not self.launch_button:
            return
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not self.pending_positions:
            self.cards_layout.addWidget(EmptyState('No positions yet', 'Add at least one validated holding to unlock the portfolio dashboard.'))
        for position in self.pending_positions:
            self.cards_layout.addWidget(PositionCard(position, self.window.format_currency))
        self.cards_layout.addStretch(1)
        self.launch_button.setEnabled(bool(self.pending_positions))
        # Force the container and layout to recalculate geometry
        self.cards_container.adjustSize()
        self.cards_container.updateGeometry()
        self.cards_container.update()

    def _select_risk_tier(self, tier_key: str) -> None:
        self._selected_risk_tier = tier_key
        for key, card in self._tier_cards.items():
            card.set_selected(key == tier_key)

    def launch(self) -> None:
        self.launch_button.start_loading('Launching...')
        QApplication.processEvents()
        self.window.positions = list(self.pending_positions)
        self.window.store.save_positions(self.window.positions)
        # Save risk tier to settings
        self.window.settings['risk_tier'] = self._selected_risk_tier
        self.window.store.save_settings(self.window.settings)
        state = self.window.store.load_app_state()
        state['onboarding_complete'] = True
        state['risk_tier_selected'] = True
        self.window.store.save_app_state(state)
        self.window.load_main_shell()
