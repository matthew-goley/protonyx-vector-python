from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget

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
        parent.notifications.show(
            'Vector is out of date',
            f'v{APP_VERSION} → v{latest}',
        )

    worker.version_received.connect(_on_version)
    worker.failed.connect(lambda: None)
    worker.start()
