from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from PySide6.QtCore import QPointF
from PySide6.QtGui import QCursor, QMouseEvent, QWheelEvent

from datalens.ui.canvas.viewport import ViewportTransform


@dataclass(frozen=True)
class ToolResult:
    consumed: bool
    cursor: QCursor | None = None


@runtime_checkable
class CanvasTool(Protocol):
    """
    Active behavior for an ImageCanvas.

    Tools receive pointer events before layer hit-testing. They may consume events
    to capture a gesture (painting, dragging, etc.) and update layers.
    """

    tool_id: str

    def on_activate(self) -> None:
        ...

    def on_deactivate(self) -> None:
        ...

    def on_mouse_event(self, event: QMouseEvent, view: ViewportTransform, image_pos: QPointF) -> ToolResult:
        ...

    def on_wheel_event(self, event: QWheelEvent, view: ViewportTransform, image_pos: QPointF) -> ToolResult:
        ...

