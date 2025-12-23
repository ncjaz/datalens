from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from PySide6.QtCore import QEvent, QPointF, QSize, Qt
from PySide6.QtGui import QImage, QMouseEvent, QPainter, QPaintEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QWidget

from datalens.core.logging import get_logger
from datalens.ui.canvas.layers.base import CanvasHit, CanvasLayer, CanvasLayerId, HitKind
from datalens.ui.canvas.selection.router import SelectionRouter
from datalens.ui.canvas.tools.base import ToolResult
from datalens.ui.canvas.tools.tool_manager import ToolManager
from datalens.ui.canvas.viewport import ViewportTransform

log = get_logger(__name__)


@dataclass
class _LayerEntry:
    layer: CanvasLayer
    z: int
    visible: bool = True


class ImageCanvas(QWidget):
    """
    Reusable image canvas with overlay layers and optional tools.

    - Base image is drawn first.
    - Then overlay layers are drawn in ascending z-order.
    - Pointer events route to the active tool first; otherwise default hit-test.

    This widget is UI-thread only.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)

        self._view = ViewportTransform()
        self._base_pixmap: QPixmap | None = None
        self._margin_px = 8

        self._panning = False
        self._pan_last_pos: QPointF | None = None

        self.tools = ToolManager()
        self.selection = SelectionRouter()

        self._layers: dict[CanvasLayerId, _LayerEntry] = {}
        self._invalid_tool_result_logged: set[tuple[str | None, str]] = set()
        self._click_debug_budget = 25

    @property
    def view(self) -> ViewportTransform:
        return self._view

    def widget_to_image_pos(self, widget_pos: QPointF) -> QPointF:
        return self._view.widget_to_image(widget_pos)

    def image_to_widget_pos(self, image_pos: QPointF) -> QPointF:
        return self._view.image_to_widget(image_pos)

    def set_base_image(self, image: QImage | QPixmap | None, *, fit: bool = True) -> None:
        if image is None:
            self._base_pixmap = None
            self._view.set_image_size(QSize())
            self.update()
            return

        pix = image if isinstance(image, QPixmap) else QPixmap.fromImage(image)
        self._base_pixmap = pix
        self._view.set_image_size(pix.size())
        if fit:
            self._view.fit_to_widget(self.size(), margin_px=self._margin_px)
        self.update()

    def add_layer(self, layer: CanvasLayer, *, z: int = 0, visible: bool = True) -> None:
        self._layers[str(layer.layer_id)] = _LayerEntry(layer=layer, z=int(z), visible=bool(visible))
        self.update()

    def _normalize_tool_result(self, res: Any, *, tool: object, phase: str) -> ToolResult:
        """
        Tools must return ToolResult, but this is a runtime/3rd-party boundary.

        If a tool mistakenly returns None/invalid values, treat it as "not consumed"
        instead of crashing the UI event loop.
        """
        if isinstance(res, ToolResult):
            return res

        tool_id = getattr(tool, "tool_id", None)
        key = (tool_id, str(phase))
        level = "warning" if key not in self._invalid_tool_result_logged else "debug"
        self._invalid_tool_result_logged.add(key)

        getattr(log, level)(
            "Canvas tool returned invalid result (best-effort)",
            extra={
                "operation": "canvas",
                "phase": "tool_invalid_result",
                "event_phase": str(phase),
                "tool_id": tool_id,
                "result_type": type(res).__name__,
            },
        )
        return ToolResult(consumed=False)

    @staticmethod
    def _qt_int(value: object) -> int:
        """
        Convert PySide6 Qt enums/QFlags to int safely.

        PySide6 enums are not always directly int()-castable (e.g. `Qt.MouseButton`),
        so prefer the `.value` attribute when present.
        """
        try:
            if hasattr(value, "value"):
                return int(getattr(value, "value"))  # type: ignore[arg-type]
            return int(value)  # type: ignore[arg-type]
        except Exception:
            return 0

    def remove_layer(self, layer_id: CanvasLayerId) -> None:
        self._layers.pop(str(layer_id), None)
        self.update()

    def set_layer_visible(self, layer_id: CanvasLayerId, visible: bool) -> None:
        entry = self._layers.get(str(layer_id))
        if entry is None:
            return
        entry.visible = bool(visible)
        self.update()

    def _draw_base(self, painter: QPainter) -> None:
        if self._base_pixmap is None or self._base_pixmap.isNull():
            return
        rect = self._view.image_rect_in_widget()
        if rect.isNull():
            return
        painter.drawPixmap(rect, self._base_pixmap, self._base_pixmap.rect())

    def _sorted_layers(self) -> list[_LayerEntry]:
        return sorted(self._layers.values(), key=lambda e: int(e.z))

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self._draw_base(painter)
        for entry in self._sorted_layers():
            if not entry.visible:
                continue
            try:
                entry.layer.draw(painter, self._view)
            except Exception:
                log.debug(
                    "Layer draw failed (best-effort)",
                    exc_info=True,
                    extra={"operation": "canvas", "phase": "layer_draw_error", "layer_id": str(entry.layer.layer_id)},
                )

    def resizeEvent(self, event) -> None:  # type: ignore[override]  # noqa: N802
        super().resizeEvent(event)
        if self._view.image_size.isEmpty():
            return
        if not self._view.user_adjusted:
            self._view.fit_to_widget(self.size(), margin_px=self._margin_px)
        else:
            self._view.clamp_to_widget(self.size(), margin_px=self._margin_px)

    def _event_image_pos(self, event_pos: QPointF) -> QPointF:
        return self._view.widget_to_image(event_pos)

    def _in_image_bounds(self, image_pos: QPointF) -> bool:
        if self._view.image_size.isEmpty():
            return False
        return 0.0 <= image_pos.x() <= float(self._view.image_size.width()) and 0.0 <= image_pos.y() <= float(
            self._view.image_size.height()
        )

    def _hit_test(self, image_pos: QPointF) -> CanvasHit | None:
        # Hit-test in reverse draw order for interactive layers.
        for entry in reversed(self._sorted_layers()):
            if not entry.visible:
                continue
            try:
                hit = entry.layer.hit_test(image_pos, self._view)
            except Exception:
                hit = None
            if hit is not None:
                return hit
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._handle_mouse_event(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._handle_mouse_event(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._handle_mouse_event(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        try:
            pos = QPointF(event.position())
            img_pos = self._event_image_pos(pos)
            tool = self.tools.active_tool
            if tool is not None:
                try:
                    res = tool.on_wheel_event(event, self._view, img_pos)
                except Exception:
                    log.warning(
                        "Canvas tool wheel handler failed",
                        exc_info=True,
                        extra={"operation": "canvas", "phase": "tool_wheel_error", "tool_id": getattr(tool, "tool_id", None)},
                    )
                    res = ToolResult(consumed=False)
                res = self._normalize_tool_result(res, tool=tool, phase="wheel")
                if bool(res.consumed):
                    self.update()
                    return

            # Default: keep the rest of the app behaving normally; only zoom with Ctrl+Wheel.
            if bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                dy = float(event.angleDelta().y())
                factor = 1.0
                if dy != 0.0:
                    factor = 1.15 if dy > 0 else 1.0 / 1.15

                if log.isEnabledFor(logging.DEBUG):
                    log.debug(
                        "Canvas zoom",
                        extra={
                            "operation": "canvas",
                            "phase": "zoom",
                            "delta_y": dy,
                            "factor": factor,
                            "pos_widget": (float(pos.x()), float(pos.y())),
                            "pos_image": (float(img_pos.x()), float(img_pos.y())),
                        },
                    )

                self._view.zoom_at(pos, factor=factor, min_scale=1e-3, max_scale=200.0)
                self._view.clamp_to_widget(self.size(), margin_px=self._margin_px)
                self.update()
                event.accept()
                return

            super().wheelEvent(event)
        except Exception:
            log.exception(
                "Canvas wheel event failed",
                extra={"operation": "canvas", "phase": "wheel_event_error"},
            )
            super().wheelEvent(event)

    def _handle_mouse_event(self, event: QMouseEvent) -> None:
        try:
            pos = QPointF(event.position())
            img_pos = self._event_image_pos(pos)

            if self._click_debug_budget > 0 and log.isEnabledFor(logging.DEBUG):
                et = QEvent.Type(event.type())
                if et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
                    self._click_debug_budget -= 1
                    tool = self.tools.active_tool
                    log.debug(
                        "Canvas mouse event",
                        extra={
                            "operation": "canvas",
                            "phase": "mouse_event",
                            "event_type": et.name,
                            "button": self._qt_int(event.button()),
                            "buttons": self._qt_int(event.buttons()),
                            "mods": self._qt_int(event.modifiers()),
                            "tool_id": getattr(tool, "tool_id", None),
                            "pos_widget": (float(pos.x()), float(pos.y())),
                            "pos_image": (float(img_pos.x()), float(img_pos.y())),
                            "panning": bool(self._panning),
                        },
                    )

            # Default pan behavior: middle-mouse drag pans the view and is independent
            # of tools/layers. This keeps panning available without forcing every tool
            # to implement it.
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.MiddleButton:
                self._panning = True
                self._pan_last_pos = pos
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return

            if event.type() == QEvent.Type.MouseMove and self._panning and self._pan_last_pos is not None:
                delta = QPointF(float(pos.x() - self._pan_last_pos.x()), float(pos.y() - self._pan_last_pos.y()))
                self._pan_last_pos = pos
                self._view.pan_by(delta)
                self._view.clamp_to_widget(self.size(), margin_px=self._margin_px)
                self.update()
                event.accept()
                return

            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.MiddleButton:
                self._panning = False
                self._pan_last_pos = None
                self.setCursor(Qt.ArrowCursor)
                event.accept()
                return

            tool = self.tools.active_tool
            if tool is not None:
                try:
                    res = tool.on_mouse_event(event, self._view, img_pos)
                except Exception:
                    log.warning(
                        "Canvas tool mouse handler failed",
                        exc_info=True,
                        extra={"operation": "canvas", "phase": "tool_mouse_error", "tool_id": getattr(tool, "tool_id", None)},
                    )
                    res = ToolResult(consumed=False)
                res = self._normalize_tool_result(res, tool=tool, phase="mouse")
                if res.cursor is not None:
                    self.setCursor(res.cursor)
                if bool(res.consumed):
                    self.update()
                    return

            # Default selection/hit behavior.
            if not self._in_image_bounds(img_pos):
                event.ignore()
                return

            hit = self._hit_test(img_pos)
            if hit is None:
                hit = CanvasHit(
                    layer_id="__base__",
                    kind=HitKind.PIXEL,
                    image_pos=img_pos,
                    payload={"buttons": self._qt_int(event.buttons())},
                )

            try:
                consumed = bool(self.selection.handle_hit(hit))
            except Exception:
                consumed = False
                log.debug("Selection router failed (best-effort)", exc_info=True)

            if consumed:
                self.update()
                return

            # We didn't consume it: let Qt propagate it normally.
            event.ignore()
        except Exception:
            # Do not attempt to "re-dispatch" the event here; that risks recursion.
            # Best-effort: log + ignore so the parent can continue handling input.
            try:
                log.exception(
                    "Canvas mouse event failed",
                    extra={"operation": "canvas", "phase": "mouse_event_error"},
                )
            except Exception as log_exc:
                import sys

                print(f"[datalens.canvas] Failed to log mouse_event_error: {log_exc!r}", file=sys.stderr)
            event.ignore()
