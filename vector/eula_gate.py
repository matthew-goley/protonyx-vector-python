"""Full-window EULA acceptance gate.

``EulaGateOverlay`` blurs the running app and blocks all interaction behind a
centered card until the user accepts the End User License Agreement (server
side only, no local persistence) or declines and exits. Acceptance is sent to
the backend on a background ``QThread`` so the UI never freezes.

The check that decides whether to show this overlay lives in
``vector.app._maybe_show_eula_gate`` (run once after the main window is shown).
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QEvent, Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from auth.auth import _eula_status_code, accept_eula, clear_token

from .constants import EULA_URL
from .scale import sc, scpt


class _AcceptWorker(QThread):
    """Runs ``accept_eula`` off the UI thread (same pattern as the auth login
    workers in ``auth/login_window.py``).

    Emits ``done`` exactly once with one of:
      * ``'ok'``           - acceptance recorded server side
      * ``'unauthorized'`` - the session token is no longer valid (HTTP 401)
      * ``'failed'``       - a transient network/server failure; safe to retry
    """

    done = pyqtSignal(str)

    def __init__(self, token: str) -> None:
        super().__init__()
        self._token = token

    def run(self) -> None:  # noqa: D401 - QThread API
        try:
            result = accept_eula(self._token)
        except Exception:  # noqa: BLE001 - accept_eula already swallows; belt-and-suspenders
            self.done.emit('failed')
            return
        if isinstance(result, dict) and result.get('success'):
            self.done.emit('ok')
            return
        # The accept failed. Probe the session so an expired token can be told
        # apart from a transient outage: a 401 on the status endpoint means the
        # session is dead, anything else (2xx or no response) is retryable.
        try:
            code = _eula_status_code(self._token)
        except Exception:  # noqa: BLE001
            code = None
        self.done.emit('unauthorized' if code == 401 else 'failed')


class EulaGateOverlay(QWidget):
    """A blocking, full-window EULA acceptance overlay.

    Construction blurs ``parent``'s central widget and paints a semi-transparent
    backdrop over the whole window. The overlay grabs the keyboard and sits on
    top so the blurred app behind it cannot be interacted with.
    """

    accepted = pyqtSignal()

    def __init__(
        self,
        parent: QWidget,
        token: str,
        on_accepted: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._token = token
        self._on_accepted = on_accepted
        self._worker: Optional[_AcceptWorker] = None

        # Blur the app behind the gate (mirrors the pro-gate blur radius).
        self._blur_target: Optional[QWidget] = (
            parent.centralWidget() if hasattr(parent, 'centralWidget') else None
        )
        if self._blur_target is not None:
            blur = QGraphicsBlurEffect(self._blur_target)
            blur.setBlurRadius(50)
            self._blur_target.setGraphicsEffect(blur)

        self.setObjectName('eulaGateOverlay')
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._build_ui()

        # Always cover the whole parent, including across window resizes.
        parent.installEventFilter(self)
        self._fit_to_parent()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(sc(40), sc(40), sc(40), sc(40))
        root.addStretch(1)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)

        card = QFrame()
        card.setObjectName('eulaCard')
        card.setMaximumWidth(sc(500))
        card.setStyleSheet(
            'QFrame#eulaCard {'
            ' background-color: #1e2030;'
            ' border: 1px solid #2a3142;'
            f' border-radius: {sc(16)}px;'
            ' }'
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(sc(32), sc(32), sc(32), sc(32))
        card_layout.setSpacing(sc(16))

        title = QLabel('End User License Agreement')
        tf = QFont()
        tf.setPointSize(scpt(20))
        tf.setBold(True)
        title.setFont(tf)
        title.setWordWrap(True)
        title.setStyleSheet(
            'QLabel {'
            ' color: #ffffff;'
            f' font-size: {scpt(20)}pt;'
            ' font-weight: 700;'
            ' background: transparent;'
            ' border: none;'
            ' }'
        )
        card_layout.addWidget(title)

        message = QLabel(
            'Please review and accept our End User License Agreement to '
            'continue using Vector.'
        )
        message.setWordWrap(True)
        message.setStyleSheet(
            'QLabel {'
            ' color: #a0a6b6;'
            f' font-size: {scpt(14)}pt;'
            ' background: transparent;'
            ' border: none;'
            ' }'
        )
        card_layout.addWidget(message)

        # Styled as a flat text link (same approach as the login "Forgot
        # Password?" link). Opens the EULA in the system browser.
        self._link = QPushButton('Read the End User License Agreement')
        self._link.setObjectName('eulaLink')
        self._link.setFlat(True)
        self._link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._link.setStyleSheet(
            'QPushButton#eulaLink {'
            ' background: transparent;'
            ' border: none;'
            ' color: #2dd4bf;'
            f' font-size: {scpt(13)}pt;'
            ' text-align: left;'
            ' padding: 0px;'
            ' }'
            'QPushButton#eulaLink:hover { color: #4ee8d3; }'
        )
        self._link.clicked.connect(self._open_eula)
        card_layout.addWidget(self._link, alignment=Qt.AlignmentFlag.AlignLeft)

        self._error_label = QLabel('')
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(
            'QLabel {'
            ' color: #ff6b6b;'
            f' font-size: {scpt(12)}pt;'
            ' background: transparent;'
            ' border: none;'
            ' }'
        )
        self._error_label.hide()
        card_layout.addWidget(self._error_label)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(sc(12))
        btn_row.addStretch(1)

        self._decline_btn = QPushButton('Decline')
        self._decline_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._decline_btn.clicked.connect(self._on_decline)
        btn_row.addWidget(self._decline_btn)

        self._accept_btn = QPushButton('I Accept')
        self._accept_btn.setProperty('accent', 'true')
        self._accept_btn.setDefault(True)
        self._accept_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._accept_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self._accept_btn)

        card_layout.addLayout(btn_row)

        row.addWidget(card)
        row.addStretch(1)
        root.addLayout(row)
        root.addStretch(1)

    # ------------------------------------------------------------- Geometry

    def _fit_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._fit_to_parent()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Keep covering the entire parent if the window was resized. The guard
        # stops the setGeometry below from re-triggering this handler endlessly.
        parent = self.parentWidget()
        if parent is not None and self.size() != parent.size():
            self._fit_to_parent()

    # ------------------------------------------------------- Event blocking

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._fit_to_parent()
        self.raise_()
        self.setFocus()
        try:
            self.grabKeyboard()
        except Exception:  # noqa: BLE001
            pass

    def hideEvent(self, event) -> None:  # noqa: N802
        try:
            self.releaseKeyboard()
        except Exception:  # noqa: BLE001
            pass
        super().hideEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Swallow every key so nothing reaches the blurred app (including the
        # application-wide R / L / D / S shortcuts on the main window).
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # Consume backdrop clicks so they never fall through to widgets behind.
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(7, 10, 18, 205))

    # ----------------------------------------------------------- Behaviour

    def _open_eula(self) -> None:
        QDesktopServices.openUrl(QUrl(EULA_URL))

    def _on_accept(self) -> None:
        if self._worker is not None:
            return
        self._accept_btn.setEnabled(False)
        self._error_label.hide()
        worker = _AcceptWorker(self._token)
        worker.done.connect(self._on_accept_done)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _on_accept_done(self, status: str) -> None:
        self._worker = None
        if status == 'ok':
            self._complete()
        elif status == 'unauthorized':
            self._handle_expired_session()
        else:
            self._error_label.setText(
                'Unable to connect. Please check your internet connection and try again.'
            )
            self._error_label.show()
            self._accept_btn.setEnabled(True)

    def _on_decline(self) -> None:
        # Clean exit. Teardown first so the keyboard grab is released.
        self._teardown(remove_blur=False)
        QApplication.quit()

    def _handle_expired_session(self) -> None:
        # Session expired mid-run: drop the saved token and quit so the user
        # re-authenticates on the next launch.
        self._teardown(remove_blur=False)
        try:
            clear_token()
        except Exception:  # noqa: BLE001
            pass
        QApplication.quit()

    def _complete(self) -> None:
        self._teardown(remove_blur=True)
        if callable(self._on_accepted):
            try:
                self._on_accepted()
            except Exception:  # noqa: BLE001
                pass
        self.accepted.emit()
        self.hide()
        self.deleteLater()

    def _teardown(self, *, remove_blur: bool) -> None:
        parent = self.parentWidget()
        if parent is not None:
            parent.removeEventFilter(self)
        try:
            self.releaseKeyboard()
        except Exception:  # noqa: BLE001
            pass
        if remove_blur and self._blur_target is not None:
            self._blur_target.setGraphicsEffect(None)
