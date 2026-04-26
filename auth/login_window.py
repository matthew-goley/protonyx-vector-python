"""Pre-startup auth dialog for Vector.

Self-contained: only depends on PyQt6, ``auth.auth`` for the API surface, and
``vector.paths.resource_path`` for asset resolution. The dialog applies its own
dark stylesheet so it can render before ``VectorMainWindow`` (which owns the
global theme) has been constructed.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .auth import get_me, login, save_token, signup


_DIALOG_STYLESHEET = """
QDialog {
    background-color: #0b1020;
    color: #e7ebf3;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}
QWidget {
    background-color: #0b1020;
    color: #e7ebf3;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}
QLabel { background: transparent; color: #e7ebf3; }
QLabel#brand { color: #e7ebf3; font-size: 22pt; font-weight: 700; }
QLabel#tagline { color: #8d98af; font-size: 11pt; }
QLabel#status { font-size: 10pt; }
QLabel#statusError { color: #ff6b6b; font-size: 10pt; }
QLabel#statusOk { color: #2dd4bf; font-size: 10pt; }
QLabel#fieldLabel { color: #9aa7be; font-size: 10pt; font-weight: 600; }
QLineEdit {
    background: #121828;
    border: 1px solid #2c364a;
    border-radius: 10px;
    padding: 10px;
    color: #e7ebf3;
    selection-background-color: #1e3a8a;
}
QLineEdit:focus { border: 1px solid #38bdf8; }
QPushButton {
    background: #1a2334;
    border: 1px solid #2c364a;
    border-radius: 12px;
    padding: 10px 16px;
    color: #e7ebf3;
}
QPushButton:hover { background: #202b41; }
QPushButton:pressed { background: #121929; }
QPushButton:disabled { color: #6a7892; }
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
QCheckBox { color: #9aa7be; spacing: 8px; background: transparent; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #2c364a;
    border-radius: 4px;
    background: #121828;
}
QCheckBox::indicator:checked { background: #2dd4bf; border: 1px solid #2dd4bf; }
QTabWidget::pane {
    border: 1px solid #2a3142;
    border-radius: 12px;
    background: #161b26;
    top: -1px;
}
QTabWidget::tab-bar { left: 18px; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: #121828;
    color: #9aa7be;
    border: 1px solid #2c364a;
    border-bottom: none;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    padding: 8px 22px;
    margin-right: 4px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #161b26;
    color: #e7ebf3;
    border: 1px solid #2a3142;
    border-bottom: none;
}
QTabBar::tab:hover:!selected { color: #cbd5e1; }
QFrame#dialogPanel {
    background: #161b26;
    border: 1px solid #2a3142;
    border-radius: 16px;
}
"""


def _login_flow(username_or_email: str, password: str) -> dict:
    token = login(username_or_email, password)
    user_data = get_me(token)
    return {'token': token, 'user_data': user_data}


def _signup_flow(username: str, email: str, password: str) -> dict:
    signup(username, email, password)
    return {'success': True}


class _ApiWorker(QThread):
    """Run a synchronous API callable on a background thread.

    Per spec: emits ``result`` with a dict payload on success, or ``error``
    with a string on failure. Non-dict return values are wrapped in
    ``{'value': ...}`` so the signal contract stays consistent.
    """

    result = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, fn: Callable[..., Any], *args: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self) -> None:  # noqa: D401 — QThread API
        try:
            payload = self._fn(*self._args)
        except Exception as exc:  # noqa: BLE001 — surface server / network errors verbatim
            self.error.emit(str(exc) or exc.__class__.__name__)
            return
        if isinstance(payload, dict):
            self.result.emit(payload)
        else:
            self.result.emit({'value': payload})


class LoginWindow(QDialog):
    """Modal sign-in / sign-up dialog shown before the main window loads."""

    login_successful = pyqtSignal(str, dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.token: Optional[str] = None
        self.user_data: Optional[dict] = None
        self._active_worker: Optional[_ApiWorker] = None

        self.setWindowTitle('Vector — Sign In')
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(_DIALOG_STYLESHEET)

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(18)

        root.addLayout(self._build_header())

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_login_tab(), 'Login')
        self._tabs.addTab(self._build_signup_tab(), 'Sign Up')
        root.addWidget(self._tabs, stretch=1)

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(14)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = self._load_logo_pixmap(56)
        if pixmap is not None and not pixmap.isNull():
            logo_label.setPixmap(pixmap)
            logo_label.setFixedSize(pixmap.size())
            header.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        else:
            logo_label.setObjectName('brand')
            logo_label.setText('Vector')
            header.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        title = QLabel('Welcome back')
        title.setObjectName('brand')
        tagline = QLabel('Sign in to access your portfolio analytics.')
        tagline.setObjectName('tagline')
        text_col.addWidget(title)
        text_col.addWidget(tagline)
        header.addLayout(text_col, stretch=1)

        return header

    def _build_login_tab(self) -> QWidget:
        page = QFrame()
        page.setObjectName('dialogPanel')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        layout.addWidget(self._field_label('Username or email'))
        self._login_user = QLineEdit()
        self._login_user.setPlaceholderText('you@example.com')
        layout.addWidget(self._login_user)

        layout.addWidget(self._field_label('Password'))
        self._login_pw = QLineEdit()
        self._login_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._login_pw.setPlaceholderText('••••••••')
        layout.addWidget(self._login_pw)

        self._stay_signed_in = QCheckBox('Stay signed in')
        layout.addWidget(self._stay_signed_in)

        self._login_button = QPushButton('Login')
        self._login_button.setProperty('accent', 'true')
        self._login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_button.clicked.connect(self._on_login_clicked)
        layout.addWidget(self._login_button)

        self._login_status = QLabel('')
        self._login_status.setObjectName('status')
        self._login_status.setWordWrap(True)
        layout.addWidget(self._login_status)

        layout.addStretch(1)

        self._login_pw.returnPressed.connect(self._on_login_clicked)
        self._login_user.returnPressed.connect(self._login_pw.setFocus)
        return page

    def _build_signup_tab(self) -> QWidget:
        page = QFrame()
        page.setObjectName('dialogPanel')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        layout.addWidget(self._field_label('Username'))
        self._signup_user = QLineEdit()
        self._signup_user.setPlaceholderText('vector_user')
        layout.addWidget(self._signup_user)

        layout.addWidget(self._field_label('Email'))
        self._signup_email = QLineEdit()
        self._signup_email.setPlaceholderText('you@example.com')
        layout.addWidget(self._signup_email)

        layout.addWidget(self._field_label('Password'))
        self._signup_pw = QLineEdit()
        self._signup_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._signup_pw.setPlaceholderText('Choose a strong password')
        layout.addWidget(self._signup_pw)

        self._signup_button = QPushButton('Sign Up')
        self._signup_button.setProperty('accent', 'true')
        self._signup_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._signup_button.clicked.connect(self._on_signup_clicked)
        layout.addWidget(self._signup_button)

        self._signup_status = QLabel('')
        self._signup_status.setObjectName('status')
        self._signup_status.setWordWrap(True)
        layout.addWidget(self._signup_status)

        layout.addStretch(1)

        self._signup_pw.returnPressed.connect(self._on_signup_clicked)
        self._signup_user.returnPressed.connect(self._signup_email.setFocus)
        self._signup_email.returnPressed.connect(self._signup_pw.setFocus)
        return page

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName('fieldLabel')
        return label

    @staticmethod
    def _load_logo_pixmap(size: int) -> Optional[QPixmap]:
        try:
            from vector.paths import resource_path
        except Exception:  # noqa: BLE001
            return None
        try:
            asset_path = resource_path('assets', 'vector_full.png')
        except Exception:  # noqa: BLE001
            return None
        pixmap = QPixmap(str(asset_path))
        if pixmap.isNull():
            return None
        return pixmap.scaledToHeight(size, Qt.TransformationMode.SmoothTransformation)

    # ----------------------------------------------------------------- Login

    def _on_login_clicked(self) -> None:
        if self._active_worker is not None:
            return
        user = self._login_user.text().strip()
        password = self._login_pw.text()
        if not user or not password:
            self._set_status(self._login_status, 'Enter your username/email and password.', error=True)
            return
        self._set_status(self._login_status, 'Signing in…')
        self._set_inputs_enabled(False)
        self._login_button.setText('Signing in…')

        worker = _ApiWorker(_login_flow, user, password)
        worker.result.connect(self._on_login_success)
        worker.error.connect(self._on_login_error)
        worker.finished.connect(worker.deleteLater)
        self._active_worker = worker
        worker.start()

    def _on_login_success(self, payload: dict) -> None:
        self._active_worker = None
        token = payload.get('token')
        user_data = payload.get('user_data')
        if not isinstance(token, str) or not isinstance(user_data, dict):
            self._on_login_error('Server returned an unexpected response.')
            return
        self.token = token
        self.user_data = user_data
        if self._stay_signed_in.isChecked():
            try:
                save_token(token)
            except OSError as exc:
                # Token still usable for this session even if persistence fails.
                self._set_status(
                    self._login_status,
                    f'Logged in (could not persist session: {exc}).',
                    error=False,
                )
        self.login_successful.emit(token, user_data)
        self.accept()

    def _on_login_error(self, message: str) -> None:
        self._active_worker = None
        self._set_inputs_enabled(True)
        self._login_button.setText('Login')
        self._set_status(self._login_status, message or 'Login failed.', error=True)

    # ---------------------------------------------------------------- Signup

    def _on_signup_clicked(self) -> None:
        if self._active_worker is not None:
            return
        username = self._signup_user.text().strip()
        email = self._signup_email.text().strip()
        password = self._signup_pw.text()
        if not username or not email or not password:
            self._set_status(self._signup_status, 'Fill in every field to create an account.', error=True)
            return
        self._set_status(self._signup_status, 'Creating account…')
        self._set_inputs_enabled(False)
        self._signup_button.setText('Creating…')

        worker = _ApiWorker(_signup_flow, username, email, password)
        worker.result.connect(self._on_signup_success)
        worker.error.connect(self._on_signup_error)
        worker.finished.connect(worker.deleteLater)
        self._active_worker = worker
        worker.start()

    def _on_signup_success(self, _payload: dict) -> None:
        self._active_worker = None
        self._set_inputs_enabled(True)
        self._signup_button.setText('Sign Up')
        username = self._signup_user.text().strip()
        self._set_status(self._signup_status, 'Account created — please sign in.', error=False, ok=True)
        self._signup_pw.clear()
        # Pre-fill the login tab so the user only needs to type their password.
        if username and not self._login_user.text().strip():
            self._login_user.setText(username)
        self._tabs.setCurrentIndex(0)
        self._login_pw.setFocus()

    def _on_signup_error(self, message: str) -> None:
        self._active_worker = None
        self._set_inputs_enabled(True)
        self._signup_button.setText('Sign Up')
        self._set_status(self._signup_status, message or 'Sign up failed.', error=True)

    # ---------------------------------------------------------------- Helpers

    def _set_inputs_enabled(self, enabled: bool) -> None:
        for widget in (
            self._login_user, self._login_pw, self._login_button, self._stay_signed_in,
            self._signup_user, self._signup_email, self._signup_pw, self._signup_button,
            self._tabs,
        ):
            widget.setEnabled(enabled)

    @staticmethod
    def _set_status(label: QLabel, message: str, *, error: bool = False, ok: bool = False) -> None:
        label.setText(message)
        if error:
            label.setObjectName('statusError')
        elif ok:
            label.setObjectName('statusOk')
        else:
            label.setObjectName('status')
        # Re-polish so the new objectName-scoped style applies.
        label.style().unpolish(label)
        label.style().polish(label)
