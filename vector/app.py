from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
from functools import partial
from typing import Any

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSplashScreen,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .analytics import compute_portfolio_analytics
from .constants import APP_NAME, APP_VERSION, COMMON_TICKERS, COMPANY_NAME, LOGO_PATH, TASKBAR_LOGO_PATH, VOLATILITY_LOOKBACK_PERIODS
from .paths import resource_path
from .scale import init_scale
from .pages.dashboard import DashboardPage
from .pages.lens_page import VectorLensPage
from .pages.onboarding import OnboardingPage, PositionDialog
from .pages.profile import ProfilePage
from .pages.settings import SettingsPage
from .store import DataStore
from .widgets import GradientBorderFrame, GradientLine


DARK_STYLESHEET = """
QWidget {
    background-color: #0b1020;
    color: #e7ebf3;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #0b1020;
}
QPushButton {
    background: #1a2334;
    border: 1px solid #2c364a;
    border-radius: 12px;
    padding: 10px 16px;
}
QPushButton:hover { background: #202b41; }
QPushButton:pressed { background: #121929; }
QPushButton[accent='true'] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2dd4bf, stop:0.5 #38bdf8, stop:1 #1e3a8a);
    color: #ffffff;
    border: none;
    font-weight: 600;
}
QPushButton[accent='true']:disabled {
    background: #1e3a6e;
    color: #6a8fc4;
}
QPushButton[accent='true'][loading='true']:disabled {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2dd4bf, stop:0.5 #38bdf8, stop:1 #1e3a8a);
    color: rgba(255, 255, 255, 180);
}
QLineEdit, QComboBox, QListWidget, QSpinBox, QTableWidget {
    background: #121828;
    border: 1px solid #2c364a;
    border-radius: 10px;
    padding: 8px;
}
QHeaderView::section {
    background: #121828;
    color: #9aa7be;
    border: none;
    padding: 8px;
}
QTableWidget {
    gridline-color: #243046;
}
QScrollArea { border: none; }
QScrollBar:vertical {
    background: transparent;
    border: none;
    width: 8px;
    margin: 0;
}
QScrollBar::groove:vertical {
    background: transparent;
    border: none;
}
QScrollBar::handle:vertical {
    background: rgba(74, 85, 104, 77);
    border-radius: 4px;
    min-height: 32px;
}
QScrollBar::handle:vertical:hover { background: rgba(74, 85, 104, 140); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
    border: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    border: none;
}
QScrollBar:horizontal {
    background: transparent;
    border: none;
    height: 8px;
    margin: 0;
}
QScrollBar::groove:horizontal {
    background: transparent;
    border: none;
}
QScrollBar::handle:horizontal {
    background: rgba(74, 85, 104, 77);
    border-radius: 4px;
    min-width: 32px;
}
QScrollBar::handle:horizontal:hover { background: rgba(74, 85, 104, 140); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
    border: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
    border: none;
}
QLabel { background: transparent; }
QFrame#cardFrame {
    background: #161b26;
    border: 1px solid #2a3142;
    border-radius: 16px;
}
QFrame#sidebarFrame {
    background: #0f1526;
    border: none;
}
QFrame#vectorWidget {
    background: #121828;
    border: 1px solid #2c364a;
    border-radius: 12px;
}
QFrame#vectorWidget[editing="true"] { border-color: #2dd4bf; }
QPushButton#navButton {
    background: transparent;
    border: 1px solid transparent;
    text-align: left;
    padding-left: 16px;
}
QPushButton#navButton:hover { background: #1a2336; border-color: transparent; }
QPushButton#navButton[active="true"] {
    background: #151e30;
    border: 1px solid #2d3c58;
}
QLabel#headerBreadcrumb { color: #90a0bb; }
QWidget#onboardingPage { background-color: #0d1117; }
QFrame#onboardingPanel { background-color: #151b26; border: 1px solid #1e3a8a; border-radius: 12px; }
QFrame#settingsFooter { background: #0b1020; border-top: 1px solid #1e2a3a; }
QLabel[role="muted"] { color: #8d98af; }
QLabel[role="accent-info"] { color: #a0c8ff; }
QFrame[role="divider"] { background: #2a3347; border: none; }
QFrame[role="row-divider"] { border: none; border-bottom: 1px solid #1e2840; background: transparent; }
QMenu { background: #151e30; border: 1px solid #2c364a; border-radius: 8px; padding: 4px; color: #e7ebf3; }
QMenu::item { padding: 8px 20px; border-radius: 4px; color: #e7ebf3; }
QMenu::item:selected { background: #1e2840; }
"""

LIGHT_STYLESHEET = """
QWidget {
    background-color: #f4f7fb;
    color: #182233;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog { background-color: #f4f7fb; }
QPushButton {
    background: white;
    border: 1px solid #ccd5e5;
    border-radius: 12px;
    padding: 10px 16px;
}
QPushButton[accent='true'] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2dd4bf, stop:0.5 #38bdf8, stop:1 #1e3a8a);
    color: #ffffff;
    border: none;
    font-weight: 600;
}
QPushButton[accent='true'][loading='true']:disabled {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2dd4bf, stop:0.5 #38bdf8, stop:1 #1e3a8a);
    color: rgba(255, 255, 255, 180);
}
QLineEdit, QComboBox, QListWidget, QSpinBox, QTableWidget {
    background: white;
    border: 1px solid #ccd5e5;
    border-radius: 10px;
    padding: 8px;
}
QHeaderView::section {
    background: white;
    color: #536075;
    border: none;
    padding: 8px;
}
QTableWidget {
    gridline-color: #dde4f0;
}
QScrollArea { border: none; }
QScrollBar:vertical {
    background: transparent;
    border: none;
    width: 8px;
    margin: 0;
}
QScrollBar::groove:vertical {
    background: transparent;
    border: none;
}
QScrollBar::handle:vertical {
    background: rgba(141, 153, 172, 77);
    border-radius: 4px;
    min-height: 32px;
}
QScrollBar::handle:vertical:hover { background: rgba(141, 153, 172, 140); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
    border: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    border: none;
}
QScrollBar:horizontal {
    background: transparent;
    border: none;
    height: 8px;
    margin: 0;
}
QScrollBar::groove:horizontal {
    background: transparent;
    border: none;
}
QScrollBar::handle:horizontal {
    background: rgba(141, 153, 172, 77);
    border-radius: 4px;
    min-width: 32px;
}
QScrollBar::handle:horizontal:hover { background: rgba(141, 153, 172, 140); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
    border: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
    border: none;
}
QLabel { background: transparent; }
QFrame#cardFrame {
    background: #ffffff;
    border: 1px solid #e2e8f4;
    border-radius: 16px;
}
QFrame#sidebarFrame {
    background: #ffffff;
    border: none;
}
QFrame#vectorWidget {
    background: #f8faff;
    border: 1px solid #ccd5e5;
    border-radius: 12px;
}
QFrame#vectorWidget[editing="true"] { border-color: #2dd4bf; }
QPushButton#navButton {
    background: transparent;
    border: 1px solid transparent;
    text-align: left;
    padding-left: 16px;
}
QPushButton#navButton:hover { background: #edf0f8; border-color: transparent; }
QPushButton#navButton[active="true"] {
    background: #e8edf7;
    border: 1px solid #c5d0e8;
}
QLabel#headerBreadcrumb { color: #536075; }
QWidget#onboardingPage { background-color: #eef1f8; }
QFrame#onboardingPanel { background-color: #ffffff; border: 1px solid #b8ccec; border-radius: 12px; }
QFrame#settingsFooter { background: #f4f7fb; border-top: 1px solid #d0d8e8; }
QLabel[role="muted"] { color: #536075; }
QLabel[role="accent-info"] { color: #1e6fad; }
QFrame[role="divider"] { background: #d0d8e8; border: none; }
QFrame[role="row-divider"] { border: none; border-bottom: 1px solid #d0d8e8; background: transparent; }
QMenu { background: #ffffff; border: 1px solid #ccd5e5; border-radius: 8px; padding: 4px; color: #182233; }
QMenu::item { padding: 8px 20px; border-radius: 4px; color: #182233; }
QMenu::item:selected { background: #e8edf7; }
"""


class MainShell(QWidget):
    def __init__(self, window: 'VectorMainWindow') -> None:
        super().__init__()
        self.window = window
        self.sidebar_buttons: dict[str, QPushButton] = {}
        self.page_stack = QStackedWidget()
        self.header_title = QLabel('Dashboard')
        self.header_breadcrumb = QLabel('Vector / Dashboard')
        self.dashboard_page = DashboardPage(window)
        self.lens_page = VectorLensPage(window)
        self.profile_page = ProfilePage(window)
        self.settings_page = SettingsPage(window)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName('sidebarFrame')
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(20, 24, 20, 24)
        sidebar_layout.setSpacing(12)
        sidebar_layout.addWidget(self.window.make_logo_label(44))
        for name in ('Dashboard', 'Vector Lens', 'Profile', 'Settings'):
            is_lens_gated = name == 'Vector Lens' and self._is_gated()
            label = f'{name}  \U0001F512' if is_lens_gated else name
            button = QPushButton(label)
            button.setObjectName('navButton')
            if is_lens_gated:
                opacity = QGraphicsOpacityEffect(button)
                opacity.setOpacity(0.35)
                button.setGraphicsEffect(opacity)
                button.setCursor(Qt.CursorShape.ArrowCursor)
                button.setStyleSheet('QPushButton#navButton { color: #4a5568; }')
            else:
                button.clicked.connect(partial(self.set_page, name))
                button.setCursor(Qt.CursorShape.PointingHandCursor)
            sidebar_layout.addWidget(button)
            self.sidebar_buttons[name] = button
        sidebar_layout.addStretch(1)
        root.addWidget(sidebar)
        root.addWidget(GradientLine())

        content = QVBoxLayout()
        content.setContentsMargins(24, 24, 24, 24)
        content.setSpacing(18)

        header = GradientBorderFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 18, 20, 18)
        text_col = QVBoxLayout()
        self.header_title.setStyleSheet('font-size: 22pt; font-weight: 700;')
        self.header_breadcrumb.setObjectName('headerBreadcrumb')
        text_col.addWidget(self.header_title)
        text_col.addWidget(self.header_breadcrumb)
        header_layout.addLayout(text_col)
        header_layout.addStretch(1)

        self._help_btn = QPushButton('?')
        self._help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._help_btn.setFixedSize(48, 48)
        self._help_btn.setToolTip('Keyboard shortcuts')
        self._help_btn.setStyleSheet(
            'QPushButton {'
            '  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,'
            '    stop:0 #2dd4bf, stop:0.5 #38bdf8, stop:1 #1e3a8a);'
            '  color: #ffffff; border: none; border-radius: 24px;'
            '  padding: 0px; font-size: 16pt; font-weight: 700;'
            '}'
            'QPushButton:hover {'
            '  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,'
            '    stop:0 #4ee8d3, stop:0.5 #5dd1ff, stop:1 #2d52b2);'
            '}'
        )
        self._help_btn.clicked.connect(self.window.show_shortcuts_modal)
        header_layout.addWidget(self._help_btn)

        content.addWidget(header)

        self.page_stack.addWidget(self.dashboard_page)
        self.page_stack.addWidget(self.lens_page)
        self.page_stack.addWidget(self.profile_page)
        self.page_stack.addWidget(self.settings_page)
        content.addWidget(self.page_stack, stretch=1)
        content_wrapper = QWidget()
        content_wrapper.setLayout(content)
        root.addWidget(content_wrapper, stretch=1)
        self.set_page('Dashboard')
        self.dashboard_page.apply_lens_gate(self._is_gated())

    def _is_gated(self) -> bool:
        user_data = getattr(self.window, 'user_data', None)
        if not isinstance(user_data, dict):
            return True
        user = user_data.get('user', {})
        if not isinstance(user, dict):
            return True
        return user.get('plan', 'free') != 'pro'

    def set_page(self, page_name: str) -> None:
        if page_name == 'Vector Lens' and self._is_gated():
            return
        mapping = {'Dashboard': 0, 'Vector Lens': 1, 'Profile': 2, 'Settings': 3}
        self.page_stack.setCurrentIndex(mapping[page_name])
        self.header_title.setText(page_name)
        self.header_breadcrumb.setText(f'Vector / {page_name}')
        for name, button in self.sidebar_buttons.items():
            button.setProperty('active', 'true' if name == page_name else 'false')
            button.style().unpolish(button)
            button.style().polish(button)
        if page_name == 'Dashboard':
            self.dashboard_page._lens.refresh()
        elif page_name == 'Vector Lens':
            self.lens_page.refresh()


class _ShortcutsDialog(QDialog):
    """Modal listing all keyboard shortcuts."""

    _ROWS = [
        ('R',   'Refresh market data'),
        ('L',   'Open Vector Lens'),
        ('D',   'Open Dashboard'),
        ('S',   'Open Settings'),
        ('A',   'Add new position'),
        ('?',   'Show this menu'),
        ('Esc', 'Close dialog'),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle('Keyboard Shortcuts')
        self.setMinimumWidth(360)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel('Keyboard Shortcuts')
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet('font-size: 15pt; font-weight: 700;')
        layout.addWidget(title)

        for key, description in self._ROWS:
            row = QHBoxLayout()
            row.setSpacing(16)
            k = QLabel(key)
            k.setFixedWidth(64)
            k.setStyleSheet(
                'padding: 4px 10px; border: 1px solid #2c364a;'
                ' border-radius: 6px; font-weight: 700; font-size: 11pt;'
                ' background: #151e30;'
            )
            k.setAlignment(Qt.AlignmentFlag.AlignCenter)
            d = QLabel(description)
            d.setStyleSheet('font-size: 11pt;')
            row.addWidget(k)
            row.addWidget(d, stretch=1)
            layout.addLayout(row)

        got_it = QPushButton('Got it')
        got_it.setProperty('accent', 'true')
        got_it.clicked.connect(self.accept)
        got_it.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(got_it, alignment=Qt.AlignmentFlag.AlignRight)


class VectorMainWindow(QMainWindow):
    def __init__(
        self,
        token: str | None = None,
        user_data: dict | None = None,
    ) -> None:
        super().__init__()
        self.token = token
        self.user_data = user_data
        self.store = DataStore()
        self.settings = self.store.load_settings()
        self.settings['volatility']['lookback_period'] = VOLATILITY_LOOKBACK_PERIODS.get(self.settings['volatility'].get('lookback', '6 months'), '6mo')
        self.state = self.store.load_app_state()
        self.positions = self.store.load_positions()
        self.shell: MainShell | None = None
        self.setWindowTitle(f'{COMPANY_NAME} {APP_NAME}')
        self.setMinimumSize(1360, 860)
        self.apply_theme()
        self._build_menu()
        if self.state.get('onboarding_complete') and self.positions:
            self.load_main_shell()
        else:
            self.setCentralWidget(OnboardingPage(self))

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.shell:
            self.shell.dashboard_page.save_layout()
        super().closeEvent(event)

    def _build_menu(self) -> None:
        refresh_action = QAction('Refresh Market Data', self)
        refresh_action.triggered.connect(self.refresh_data)
        self.addAction(refresh_action)

    def apply_theme(self) -> None:
        QApplication.instance().setStyleSheet(DARK_STYLESHEET if self.settings.get('theme', 'Dark') == 'Dark' else LIGHT_STYLESHEET)

    def format_currency(self, value: float) -> str:
        symbols = {'USD': '$', 'EUR': '€', 'GBP': '£'}
        code = self.settings.get('currency', 'USD')
        return f"{symbols.get(code, '$')}{value:,.2f}"

    def format_date(self, iso_date: str | None) -> str:
        if not iso_date:
            return '—'
        try:
            parsed = datetime.fromisoformat(iso_date).date()
        except ValueError:
            return iso_date
        if self.settings.get('date_format') == 'DD/MM/YYYY':
            return parsed.strftime('%d/%m/%Y')
        return parsed.strftime('%m/%d/%Y')

    def make_logo_label(self, size: int) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet('background: transparent;')
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        icon_label = QLabel()
        pixmap = QPixmap(str(LOGO_PATH))
        if not pixmap.isNull():
            scaled = pixmap.scaledToHeight(size, Qt.TransformationMode.SmoothTransformation)
            icon_label.setPixmap(scaled)
            icon_label.setFixedSize(scaled.size())
            layout.addWidget(icon_label)
        else:
            icon_label.setPixmap(self.create_placeholder_logo(size))
            layout.addWidget(icon_label)
            text = QLabel(APP_NAME)
            text.setStyleSheet('font-size: 20pt; font-weight: 700;')
            layout.addWidget(text)
        wrapper.setFixedHeight(size + 4)
        return wrapper

    @staticmethod
    def create_placeholder_logo(size: int) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor('#111827'))
        painter.setPen(QColor('#253147'))
        painter.drawRoundedRect(1, 1, size - 2, size - 2, 12, 12)
        path = QPainterPath()
        path.moveTo(size * 0.22, size * 0.24)
        path.lineTo(size * 0.50, size * 0.76)
        path.lineTo(size * 0.78, size * 0.24)
        accent_pen = QPen(QColor('#2dd4bf'))
        accent_pen.setWidth(max(3, size // 12))
        accent_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        accent_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.strokePath(path, accent_pen)
        painter.end()
        return pixmap

    def load_main_shell(self) -> None:
        self.shell = MainShell(self)
        self.setCentralWidget(self.shell)
        self._register_shortcuts()
        self.refresh_data()
        self._setup_auto_refresh()

    def _register_shortcuts(self) -> None:
        if getattr(self, '_shortcuts_registered', False):
            return
        self._shortcuts_registered = True
        QShortcut(QKeySequence('R'), self, activated=self.refresh_data)
        QShortcut(QKeySequence('L'), self, activated=lambda: self._switch_page('Vector Lens'))
        QShortcut(QKeySequence('D'), self, activated=lambda: self._switch_page('Dashboard'))
        QShortcut(QKeySequence('S'), self, activated=lambda: self._switch_page('Settings'))
        QShortcut(QKeySequence('A'), self, activated=self.add_position_from_settings)
        QShortcut(QKeySequence('?'), self, activated=self.show_shortcuts_modal)
        QShortcut(QKeySequence('Shift+/'), self, activated=self.show_shortcuts_modal)

    def _switch_page(self, page_name: str) -> None:
        if self.shell is not None:
            self.shell.set_page(page_name)

    def show_shortcuts_modal(self) -> None:
        dialog = _ShortcutsDialog(self)
        dialog.exec()

    def _setup_auto_refresh(self) -> None:
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
        self.refresh_timer = QTimer(self)
        interval = self.settings.get('refresh_interval', '5 min')
        mapping = {'1 min': 60_000, '5 min': 300_000, '15 min': 900_000}
        if interval in mapping:
            self.refresh_timer.timeout.connect(self.refresh_data)
            self.refresh_timer.start(mapping[interval])

    def refresh_data(self) -> None:
        if not self.positions or not self.shell:
            return
        refresh_interval = self.settings.get('refresh_interval', '5 min')
        for position in self.positions:
            try:
                snapshot = self.store.get_snapshot(position['ticker'], refresh_interval)
                position['current_price'] = snapshot['price']
                position['sector'] = snapshot['sector']
                position['equity'] = position['shares'] * position['current_price']
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, 'Refresh Warning', f"Could not refresh {position['ticker']}: {exc}")
        self.store.save_positions(self.positions)
        try:
            histories = self.store.build_histories(
                [position['ticker'] for position in self.positions],
                refresh_interval,
                self.settings['volatility']['lookback'],
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, 'Refresh Warning', f'Could not refresh price history: {exc}')
            histories = {position['ticker']: {'6mo': [], '1mo': [], self.settings['volatility']['lookback_period']: []} for position in self.positions}
        analytics = compute_portfolio_analytics(
            self.positions,
            histories,
            self.settings['direction_thresholds'],
            self.settings['volatility'],
        )
        self.state = self.store.load_app_state()
        self.shell.dashboard_page.update_dashboard(self.positions, analytics)
        self.shell.lens_page.refresh()
        self.shell.profile_page.update_profile(self.state, self.positions, analytics, self.user_data)
        self.shell.settings_page.load_from_settings(self.settings, self.positions)
        self._setup_auto_refresh()

    def add_position_from_settings(self) -> None:
        dialog = PositionDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.position_data:
            self.positions.append(dialog.position_data)
            self.store.save_positions(self.positions)
            self.refresh_data()

    def clear_cache(self) -> None:
        self.store.clear_market_cache()
        QMessageBox.information(self, 'Cache Cleared', 'Cached Yahoo Finance data has been cleared.')

    def reset_all_data(self) -> None:
        confirm = QMessageBox.question(
            self,
            'Reset Vector',
            'This will erase positions, settings, cached data, and show onboarding on next launch. Continue?',
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.store.reset_all_data()
        self.settings = self.store.load_settings()
        self.settings['volatility']['lookback_period'] = VOLATILITY_LOOKBACK_PERIODS.get(self.settings['volatility'].get('lookback', '6 months'), '6mo')
        self.state = self.store.load_app_state()
        self.positions = []
        self.apply_theme()
        self.setCentralWidget(OnboardingPage(self))

    def logout(self) -> None:
        confirm = QMessageBox.question(
            self,
            'Sign out of Vector',
            'You\'ll need to log in again to continue. Continue?',
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        if self.shell is not None:
            try:
                self.shell.dashboard_page.save_layout()
            except Exception:  # noqa: BLE001 — restart should not be blocked by save errors
                pass
        try:
            from auth.auth import clear_token
            clear_token()
        except Exception:  # noqa: BLE001 — even if delete fails, still relaunch
            pass
        import subprocess
        relaunch_args = [sys.executable] + (sys.argv[1:] if getattr(sys, 'frozen', False) else sys.argv)
        try:
            subprocess.Popen(relaunch_args, close_fds=True)
        except OSError:
            pass
        QApplication.instance().quit()


def main(
    app: 'QApplication | None' = None,
    splash: 'QSplashScreen | None' = None,
    t_start: 'float | None' = None,
    token: 'str | None' = None,
    user_data: 'dict | None' = None,
) -> int:
    """
    Main entry point.

    When called from main.py the bootstrapper has already created the
    QApplication, run the auth gate, and painted the splash screen.  Accepts
    those objects so we don't create duplicates.  Falls back to creating them
    here when invoked directly (e.g. during development without going through
    main.py) — including the auth gate, which always runs before the splash.
    """
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    init_scale(app)
    taskbar_icon = QIcon(str(TASKBAR_LOGO_PATH))
    app.setWindowIcon(
        taskbar_icon if not taskbar_icon.isNull()
        else QIcon(VectorMainWindow.create_placeholder_logo(128))
    )

    # Auth gate — always runs before the splash sequence. main.py normally
    # handles this and passes token/user_data in; this fallback covers direct
    # invocations of vector.app.main().
    if token is None or user_data is None:
        from auth.auth import clear_token, get_me, load_token
        from auth.login_window import LoginWindow

        saved = load_token()
        if saved:
            try:
                user_data = get_me(saved)
                token = saved
            except Exception:  # noqa: BLE001
                clear_token()

        if token is None or user_data is None:
            dialog = LoginWindow()
            dialog.exec()
            if not dialog.token or not dialog.user_data:
                return 0
            token = dialog.token
            user_data = dialog.user_data

    if splash is None:
        # Fallback: bootstrapper didn't run — show splash here instead.
        sw = app.primaryScreen().size().width()
        splash_w = min(int(sw * 0.55), 900)
        splash_h = splash_w * 800 // 1400
        splash_pixmap = QPixmap(str(resource_path('assets', 'splashboard.png')))
        if not splash_pixmap.isNull():
            splash_pixmap = splash_pixmap.scaled(
                splash_w, splash_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        splash = QSplashScreen(splash_pixmap, Qt.WindowType.WindowStaysOnTopHint)
        splash.setFixedSize(splash_w, splash_h)
        screen_geo = app.primaryScreen().geometry()
        splash.move(screen_geo.center().x() - splash_w // 2,
                    screen_geo.center().y() - splash_h // 2)
        splash.show()
        app.processEvents()
        t_start = time.monotonic()

    if t_start is None:
        t_start = time.monotonic()

    # Heavy UI construction — splash already visible
    window = VectorMainWindow(token=token, user_data=user_data)

    # Prefetch prices for common tickers so Add Position shows instant estimates
    threading.Thread(
        target=lambda: window.store.prefetch_common_prices(COMMON_TICKERS),
        daemon=True,
        name='vector-price-prefetch',
    ).start()

    # Ensure splash is visible for at least 2 seconds from when it first appeared
    elapsed_ms = int((time.monotonic() - t_start) * 1000)
    remaining_ms = max(0, 2000 - elapsed_ms)

    def _finish() -> None:
        window.show()
        splash.finish(window)

    QTimer.singleShot(remaining_ms, _finish)
    return app.exec()
