from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


_TOAST_WIDTH = 320
_EDGE_MARGIN = 16
_STACK_GAP = 8
_SHOW_DURATION_MS = 350
_HIDE_DURATION_MS = 250


class NotificationManager:
    def __init__(self, parent: QWidget) -> None:
        self._parent = parent
        self._toasts: list[NotificationToast] = []

    def show(self, message: str, submessage: str = '', duration: int = 0) -> None:
        toast = NotificationToast(self._parent, message, submessage, self)
        self._toasts.append(toast)
        toast.show_animated(stack_index=len(self._toasts) - 1)
        if duration > 0:
            QTimer.singleShot(duration, toast.dismiss)

    def reposition_all(self) -> None:
        for index, toast in enumerate(self._toasts):
            try:
                toast.reposition(stack_index=index)
            except RuntimeError:
                pass

    def _remove(self, toast: 'NotificationToast') -> None:
        try:
            self._toasts.remove(toast)
        except ValueError:
            return
        for index, remaining in enumerate(self._toasts):
            try:
                remaining.slide_to(stack_index=index)
            except RuntimeError:
                pass


class NotificationToast(QFrame):
    def __init__(
        self,
        parent: QWidget,
        message: str,
        submessage: str,
        manager: NotificationManager,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._anim: QPropertyAnimation | None = None

        self.setObjectName('notificationToast')
        self.setStyleSheet(
            'QFrame#notificationToast {'
            ' background-color: #161b26;'
            ' border: 1px solid #2a3142;'
            ' border-radius: 12px;'
            '}'
        )
        self.setFixedWidth(_TOAST_WIDTH)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 12, 12, 12)
        outer.setSpacing(8)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        title = QLabel(message)
        title.setStyleSheet(
            'QLabel { color: #ffffff; font-size: 12pt; font-weight: 700; background: transparent; border: none; }'
        )
        text_col.addWidget(title)

        if submessage:
            subtitle = QLabel(submessage)
            subtitle.setStyleSheet(
                'QLabel { color: #8d98af; font-size: 11pt; background: transparent; border: none; }'
            )
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

        self.adjustSize()

    def _stack_y(self, stack_index: int) -> int:
        offset = _EDGE_MARGIN
        for toast in self._manager._toasts[:stack_index]:
            offset += toast.sizeHint().height() + _STACK_GAP
        return offset

    def _final_geometry(self, stack_index: int) -> QRect:
        parent = self.parentWidget()
        height = max(self.sizeHint().height(), self.height() or 0)
        if parent is None:
            return QRect(_EDGE_MARGIN, self._stack_y(stack_index), _TOAST_WIDTH, height)
        x = parent.width() - _TOAST_WIDTH - _EDGE_MARGIN
        y = self._stack_y(stack_index)
        return QRect(x, y, _TOAST_WIDTH, height)

    def _hidden_geometry(self, final: QRect) -> QRect:
        return QRect(final.x(), -final.height(), final.width(), final.height())

    def show_animated(self, stack_index: int) -> None:
        final = self._final_geometry(stack_index)
        start = self._hidden_geometry(final)
        self.setGeometry(start)
        self.show()
        self.raise_()

        anim = QPropertyAnimation(self, b'geometry', self)
        anim.setDuration(_SHOW_DURATION_MS)
        anim.setStartValue(start)
        anim.setEndValue(final)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim

    def dismiss(self) -> None:
        if not self.isVisible():
            return
        current = self.geometry()
        hidden = self._hidden_geometry(current)
        anim = QPropertyAnimation(self, b'geometry', self)
        anim.setDuration(_HIDE_DURATION_MS)
        anim.setStartValue(current)
        anim.setEndValue(hidden)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self._on_dismiss_finished)
        anim.start()
        self._anim = anim

    def _on_dismiss_finished(self) -> None:
        self.hide()
        self._manager._remove(self)

    def slide_to(self, stack_index: int) -> None:
        """Animate to the target stack slot — used when a toast above is removed."""
        if not self.isVisible():
            return
        final = self._final_geometry(stack_index)
        anim = QPropertyAnimation(self, b'geometry', self)
        anim.setDuration(200)
        anim.setStartValue(self.geometry())
        anim.setEndValue(final)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim

    def reposition(self, stack_index: int) -> None:
        if not self.isVisible():
            return
        final = self._final_geometry(stack_index)
        if self._anim is not None and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.setEndValue(final)
        else:
            self.setGeometry(final)
