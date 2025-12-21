from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QAbstractButton


class ButtonIconAnimator(QObject):
    """
    Small helper for animated icons on QAbstractButton (QToolButton, QPushButton, etc.).

    Pattern:
    - keep the painter in a static icon function (returns QIcon)
    - keep the animation loop in an animator object (QObject + QTimer)

    This avoids mixing "create an icon" with "manage a timer + widget lifetime".
    """

    def __init__(
        self,
        *,
        frame_supplier: Callable[[float], QIcon],
        interval_ms: int = 60,
        degrees_per_tick: float = 8.0,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._frame_supplier = frame_supplier
        self._interval_ms = int(interval_ms)
        self._degrees_per_tick = float(degrees_per_tick)
        self._angle = 0.0
        self._timer: QTimer | None = None
        self._button: QAbstractButton | None = None
        self._static_icon: QIcon | None = None

    def start(self, button: QAbstractButton) -> None:
        if self._timer is not None and self._timer.isActive():
            return
        self._button = button
        self._static_icon = button.icon()
        self._angle = 0.0

        timer = QTimer(self)
        timer.setInterval(self._interval_ms)
        timer.timeout.connect(self._on_timeout)
        self._timer = timer
        timer.start()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        if self._button is not None and self._static_icon is not None:
            self._button.setIcon(self._static_icon)
        self._button = None

    def _on_timeout(self) -> None:
        self._angle = (self._angle + self._degrees_per_tick) % 360.0
        icon = self._frame_supplier(self._angle)
        if self._button is not None:
            self._button.setIcon(icon)


__all__ = ["ButtonIconAnimator"]

