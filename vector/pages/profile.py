from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..widgets import CardFrame

if TYPE_CHECKING:
    from vector.app import VectorMainWindow


_FALLBACK = '—'


class ProfilePage(QWidget):
    def __init__(self, window: 'VectorMainWindow') -> None:
        super().__init__()
        self.window = window
        self._account_label = QLabel('Protonyx Account')
        self._username_hero = QLabel(_FALLBACK)
        self._member_since_hero = QLabel(_FALLBACK)
        self.total_value = QLabel('$0.00')

        self._username_value = QLabel(_FALLBACK)
        self._email_value = QLabel(_FALLBACK)
        self._plan_value = QLabel(_FALLBACK)
        self._member_since_value = QLabel(_FALLBACK)
        self._beta_value = QLabel(_FALLBACK)
        self._downloads_value = QLabel(_FALLBACK)

        self._build_ui()
        self._populate_user_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(self._build_hero())
        layout.addWidget(self._build_details())

        logout_row = QHBoxLayout()
        logout_row.setContentsMargins(0, 0, 0, 0)
        logout_row.addStretch(1)
        self._logout_button = QPushButton('Logout')
        self._logout_button.setProperty('accent', True)
        self._logout_button.setMinimumWidth(160)
        self._logout_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logout_button.clicked.connect(self._on_logout)
        logout_row.addWidget(self._logout_button)
        layout.addLayout(logout_row)

        layout.addStretch(1)

    def _on_logout(self) -> None:
        self.window.logout()

    def _build_hero(self) -> QWidget:
        hero = CardFrame()
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(24, 24, 24, 24)
        hero_layout.setSpacing(16)

        avatar = QLabel('\U0001F464')
        avatar.setStyleSheet('QLabel { font-size: 42pt; }')
        hero_layout.addWidget(avatar)

        text_container = QVBoxLayout()
        text_container.setContentsMargins(0, 0, 0, 0)
        text_container.setSpacing(2)
        self._account_label.setProperty('role', 'muted')
        self._account_label.setStyleSheet('QLabel { font-size: 10pt; font-weight: 600; }')
        self._username_hero.setStyleSheet('QLabel { font-size: 24pt; font-weight: 700; }')
        self._member_since_hero.setProperty('role', 'muted')
        self._member_since_hero.setStyleSheet('QLabel { font-size: 10pt; }')
        text_container.addWidget(self._account_label)
        text_container.addWidget(self._username_hero)
        text_container.addWidget(self._member_since_hero)
        hero_layout.addLayout(text_container)

        hero_layout.addStretch(1)

        self.total_value.setStyleSheet('QLabel { font-size: 30pt; font-weight: 700; }')
        self.total_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hero_layout.addWidget(self.total_value)
        return hero

    def _build_details(self) -> QWidget:
        details = CardFrame()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(24, 8, 24, 8)
        details_layout.setSpacing(0)

        rows = [
            ('USERNAME', self._username_value),
            ('EMAIL', self._email_value),
            ('PLAN', self._plan_value),
            ('MEMBER SINCE', self._member_since_value),
            ('BETA ACCESS', self._beta_value),
            ('DOWNLOADS', self._downloads_value),
        ]
        for index, (label_text, value_label) in enumerate(rows):
            details_layout.addWidget(self._build_row(label_text, value_label))
            if index < len(rows) - 1:
                divider = QFrame()
                divider.setProperty('role', 'row-divider')
                divider.setFixedHeight(1)
                details_layout.addWidget(divider)
        return details

    @staticmethod
    def _build_row(label_text: str, value_label: QLabel) -> QWidget:
        row = QWidget()
        row.setStyleSheet('QWidget { background: transparent; }')
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 14, 0, 14)
        row_layout.setSpacing(16)

        key = QLabel(label_text)
        key.setProperty('role', 'muted')
        key.setStyleSheet('QLabel { font-size: 9pt; font-weight: 700; }')
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if not value_label.styleSheet():
            value_label.setStyleSheet('QLabel { font-size: 12pt; font-weight: 700; }')

        row_layout.addWidget(key)
        row_layout.addStretch(1)
        row_layout.addWidget(value_label)
        return row

    def _populate_user_data(self, user_data: dict | None = None) -> None:
        if isinstance(user_data, dict):
            envelope = user_data
        else:
            fallback = getattr(self.window, 'user_data', None)
            envelope = fallback if isinstance(fallback, dict) else {}
        data = envelope.get('user', {})
        if not isinstance(data, dict):
            data = {}

        username_raw = data.get('username')
        username = username_raw if isinstance(username_raw, str) and username_raw else _FALLBACK
        email_raw = data.get('email')
        email = email_raw if isinstance(email_raw, str) and email_raw else _FALLBACK
        plan_raw = data.get('plan')
        member_since = self._format_iso_long(data.get('member_since'))
        beta = data.get('beta_access')
        downloads = data.get('download_count')

        self._username_hero.setText(username)
        if member_since != _FALLBACK:
            self._member_since_hero.setText(f'Member since {member_since}')
        else:
            self._member_since_hero.setText(_FALLBACK)

        self._username_value.setText(username)
        self._email_value.setText(email)
        self._member_since_value.setText(member_since)

        if isinstance(plan_raw, str) and plan_raw:
            self._plan_value.setText(plan_raw.capitalize())
            if plan_raw.lower() == 'free':
                self._plan_value.setProperty('role', 'muted')
                self._plan_value.setStyleSheet('QLabel { font-size: 12pt; font-weight: 700; }')
            else:
                self._plan_value.setProperty('role', '')
                self._plan_value.setStyleSheet('QLabel { font-size: 12pt; font-weight: 700; color: #38bdf8; }')
        else:
            self._plan_value.setText(_FALLBACK)
            self._plan_value.setProperty('role', 'muted')
            self._plan_value.setStyleSheet('QLabel { font-size: 12pt; font-weight: 700; }')
        self._plan_value.style().unpolish(self._plan_value)
        self._plan_value.style().polish(self._plan_value)

        if beta is True:
            self._beta_value.setText('Enabled')
        elif beta is False:
            self._beta_value.setText('Not enabled')
        else:
            self._beta_value.setText(_FALLBACK)

        if isinstance(downloads, int):
            self._downloads_value.setText(str(downloads))
        else:
            self._downloads_value.setText(_FALLBACK)

    @staticmethod
    def _format_iso_long(iso_value: Any) -> str:
        if not isinstance(iso_value, str) or not iso_value:
            return _FALLBACK
        candidate = iso_value
        if candidate.endswith('Z'):
            candidate = candidate[:-1] + '+00:00'
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            try:
                parsed = datetime.strptime(iso_value, '%Y-%m-%d')
            except ValueError:
                return _FALLBACK
        formatted = parsed.strftime('%B %d, %Y')
        # Drop leading zero on the day so we get "April 5, 2026" not "April 05, 2026".
        return formatted.replace(' 0', ' ', 1)

    def update_profile(self, state: dict[str, Any], positions: list[dict[str, Any]], analytics: dict[str, Any], user_data: dict | None = None) -> None:
        portfolio_value = analytics.get('portfolio_value', 0.0) if isinstance(analytics, dict) else 0.0
        self.total_value.setText(self.window.format_currency(portfolio_value))
        self._populate_user_data(user_data)
