from __future__ import annotations

from typing import Callable

from datalens.core.logging import get_logger
from datalens.ui.canvas.tools.base import CanvasTool

log = get_logger(__name__)


class ToolManager:
    """
    Tracks the currently active tool.

    The canvas uses this to route pointer events before falling back to layer
    hit-testing and selection behavior.
    """

    def __init__(self) -> None:
        self._active: CanvasTool | None = None
        self._listeners: list[Callable[[CanvasTool | None], None]] = []

    @property
    def active_tool(self) -> CanvasTool | None:
        return self._active

    def set_active(self, tool: CanvasTool | None) -> None:
        if tool is self._active:
            return

        if self._active is not None:
            cancel = getattr(self._active, "cancel", None)
            if callable(cancel):
                try:
                    cancel()
                except Exception:
                    log.debug("Tool cancel failed (best-effort)", exc_info=True)
            try:
                self._active.on_deactivate()
            except Exception:
                log.debug("Tool deactivate failed (best-effort)", exc_info=True)

        self._active = tool

        if self._active is not None:
            try:
                self._active.on_activate()
            except Exception:
                log.debug("Tool activate failed (best-effort)", exc_info=True)

        for listener in list(self._listeners):
            try:
                listener(self._active)
            except Exception:
                log.debug("Tool listener failed (best-effort)", exc_info=True)

        log.info(
            "Active canvas tool changed",
            extra={
                "operation": "canvas",
                "phase": "tool_changed",
                "tool_id": getattr(self._active, "tool_id", None),
            },
        )

    def subscribe(self, callback: Callable[[CanvasTool | None], None]) -> Callable[[], None]:
        if callback not in self._listeners:
            self._listeners.append(callback)

        def _unsubscribe() -> None:
            try:
                self._listeners.remove(callback)
            except ValueError:
                return

        return _unsubscribe
