from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy, QWidget

from datalens.core.context import get_app_context
from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.domain.system.shortcuts import GestureBindingSpec, GestureId, GesturePhase
from datalens.ui.shortcuts.gesture_router import GestureRouter
from datalens.ui.theme.app_theme import AppTheme


log = get_logger(__name__)


@dataclass
class _GestureCounters:
    begin: int = 0
    update: int = 0
    end: int = 0
    cancel: int = 0


class _GestureArea(QFrame):
    def __init__(self, *, theme: AppTheme, status_label: QLabel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._status_label = status_label
        self._counters = _GestureCounters()

        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(
            "QFrame {"
            f"background: {theme.with_alpha_hex(theme.secondary_color, 0.6)};"
            f"border: 1px solid {theme.with_alpha_hex(theme.tertiary_border, 0.55)};"
            "border-radius: 10px;"
            "}"
        )

        app_ctx = get_app_context()
        plugin_id = PluginId("widget_test")
        gesture_id = "shift_drag"
        chord = app_ctx.shortcuts.get_effective_gesture_chord(
            plugin_id=plugin_id, gesture_id=gesture_id, default="Shift+LeftClick"
        )
        consume = app_ctx.shortcuts.get_effective_gesture_consume_event(
            plugin_id=plugin_id, gesture_id=gesture_id, default=False
        )

        bindings = (
            GestureBindingSpec(
                gesture_id=GestureId(gesture_id),
                title="Shift + LeftDrag",
                description="Demo: press Shift and drag with left mouse button.",
                begin_chord=chord,
                consume_event=consume,
            ),
        )

        self._router = GestureRouter(bindings=bindings, callback=self._on_gesture_phase)

    def _on_gesture_phase(self, spec: GestureBindingSpec, phase: GesturePhase, event) -> bool:
        pos = None
        if hasattr(event, "position"):
            try:
                p = event.position()
                pos = (int(p.x()), int(p.y()))
            except Exception:
                pos = None

        if phase == GesturePhase.BEGIN:
            self._counters.begin += 1
        elif phase == GesturePhase.UPDATE:
            self._counters.update += 1
        elif phase == GesturePhase.END:
            self._counters.end += 1
        elif phase == GesturePhase.CANCEL:
            self._counters.cancel += 1

        msg = (
            f"{spec.title} | phase={phase.value}"
            f" | begin={self._counters.begin} update={self._counters.update}"
            f" end={self._counters.end} cancel={self._counters.cancel}"
        )
        if pos is not None:
            msg += f" | pos={pos[0]},{pos[1]}"
        self._status_label.setText(msg)
        return True

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        try:
            if self._router.handle_mouse_press(event):
                event.accept()
                return
        except Exception:
            log.warning("Gesture router press failed (best-effort)", exc_info=True)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        try:
            if self._router.handle_mouse_move(event):
                event.accept()
                return
        except Exception:
            log.warning("Gesture router move failed (best-effort)", exc_info=True)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        try:
            if self._router.handle_mouse_release(event):
                event.accept()
                return
        except Exception:
            log.warning("Gesture router release failed (best-effort)", exc_info=True)
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        # Best-effort cancel when the cursor leaves the area mid-gesture.
        try:
            self._router.cancel(event=event)
        except Exception:
            pass
        super().leaveEvent(event)


class GesturePanel(QWidget):
    def __init__(self, *, theme: AppTheme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        hint = QLabel("Hold Shift and drag in the box to exercise press/drag/release gesture routing.", self)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)};")
        layout.addWidget(hint, 0, 0, 1, 2)

        status = QLabel("No gesture yet.", self)
        status.setWordWrap(True)
        status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(status, 1, 0, 1, 2)

        area = _GestureArea(theme=theme, status_label=status, parent=self)
        layout.addWidget(area, 2, 0, 1, 2)

        layout.setColumnStretch(0, 1)


__all__ = ["GesturePanel"]
