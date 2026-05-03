from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .constants import APP_VERSION


_VERSION_URL = 'http://localhost:3000/version'
_REQUEST_TIMEOUT_S = 4


class _VersionWorker(QThread):
    version_received = pyqtSignal(str)
    failed = pyqtSignal()

    def run(self) -> None:
        try:
            import requests
            response = requests.get(_VERSION_URL, timeout=_REQUEST_TIMEOUT_S)
            response.raise_for_status()
            payload = response.json() if response.headers.get('content-type', '').startswith('application/json') else None
            if isinstance(payload, dict):
                version = payload.get('version') or payload.get('latest') or ''
            else:
                version = response.text.strip().strip('"')
            version = (version or '').strip()
            if not version:
                self.failed.emit()
                return
            self.version_received.emit(version)
        except Exception:  # noqa: BLE001 — version check must never crash the app
            self.failed.emit()


def check_version(parent: QWidget, token: str | None = None) -> None:
    worker = _VersionWorker(parent)
    parent._version_check_worker = worker  # keep reference so QThread isn't GC'd

    def _on_version(latest: str) -> None:
        if latest == APP_VERSION:
            return
        toast = VersionToast(parent, current=APP_VERSION, latest=latest)
        parent._version_toast = toast
        toast.show_animated()

    worker.version_received.connect(_on_version)
    worker.failed.connect(lambda: None)
    worker.start()


class VersionToast(QFrame):
    WIDTH = 320
    MARGIN = 16

    def __init__(self, parent: QWidget, current: str, latest: str) -> None:
        super().__init__(parent)
        self.setObjectName('versionToast')
        self.setStyleSheet(
            'QFrame#versionToast {'
            ' background-color: #161b26;'
            ' border: 1px solid #2a3142;'
            ' border-radius: 12px;'
            '}'
        )
        self.setFixedWidth(self.WIDTH)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 12, 12, 12)
        outer.setSpacing(8)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        title = QLabel('Vector is out of date')
        title.setStyleSheet(
            'QLabel { color: #ffffff; font-size: 12pt; font-weight: 700; background: transparent; border: none; }'
        )
        subtitle = QLabel(f'v{current} → v{latest}')
        subtitle.setStyleSheet(
            'QLabel { color: #8d98af; font-size: 11pt; background: transparent; border: none; }'
        )

        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        outer.addLayout(text_col, 1)

        close_btn = QPushButton('✕')
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            'QPushButton {'
            ' background: transparent;'
            ' border: none;'
            ' color: #8d98af;'
            ' padding: 0px;'
            ' font-size: 12pt;'
            '}'
            'QPushButton:hover { color: #ffffff; }'
        )
        close_btn.clicked.connect(self.dismiss)
        outer.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._anim: QPropertyAnimation | None = None

        # Layout pass so sizeHint is valid before first reposition.
        self.adjustSize()

    def _final_geometry(self) -> QRect:
        parent = self.parentWidget()
        height = max(self.sizeHint().height(), self.height() or 0)
        if parent is None:
            return QRect(self.MARGIN, self.MARGIN, self.WIDTH, height)
        x = parent.width() - self.WIDTH - self.MARGIN
        y = self.MARGIN
        return QRect(x, y, self.WIDTH, height)

    def _hidden_geometry(self, final: QRect) -> QRect:
        return QRect(final.x(), -final.height(), final.width(), final.height())

    def show_animated(self) -> None:
        final = self._final_geometry()
        start = self._hidden_geometry(final)
        self.setGeometry(start)
        self.show()
        self.raise_()

        anim = QPropertyAnimation(self, b'geometry', self)
        anim.setDuration(350)
        anim.setStartValue(start)
        anim.setEndValue(final)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim

    def dismiss(self) -> None:
        final = self.geometry()
        hidden = self._hidden_geometry(final)
        anim = QPropertyAnimation(self, b'geometry', self)
        anim.setDuration(250)
        anim.setStartValue(final)
        anim.setEndValue(hidden)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self.hide)
        anim.start()
        self._anim = anim

    def reposition(self) -> None:
        if not self.isVisible():
            return
        final = self._final_geometry()
        # If an animation is currently running, let it finish; otherwise snap.
        if self._anim is not None and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.setEndValue(final)
        else:
            self.setGeometry(final)
