from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QCursor,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QUndoStack,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from datalens.api.tools import (
    OverlayGradient,
    OverlayPoints,
    OverlayPolygon,
    OverlayPolyline,
    OverlayPrimitive,
    OverlayText,
    ToolMutation,
    ToolViewport,
)
from datalens.core.logging import get_logger
from datalens.ui.canvas.layers.base import CanvasHit, CanvasLayer, CanvasLayerId, HitKind
from datalens.ui.canvas.mutations import ToolMutationCommand, ToolMutationHandler
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
        self._base_image: QImage | None = None
        self._margin_px = 8

        self._panning = False
        self._pan_last_pos: QPointF | None = None

        self.tools = ToolManager()
        self.selection = SelectionRouter()
        self._tool_unsub: Callable[[], None] | None = self.tools.subscribe(self._on_tool_changed)
        self.destroyed.connect(lambda *_: self._clear_tool_subscription())

        self._undo_stack: QUndoStack | None = None
        self._mutation_handler: ToolMutationHandler | None = None
        self._tool_pref_getter: Callable[[str, str, object], object] | None = None
        self._tool_pref_setter: Callable[[str, str, object], None] | None = None
        self._tool_prefs: dict[tuple[str, str], object] = {}
        self._status_handler: Callable[[str, int], None] | None = None
        self._overlay_layers: dict[str, list[OverlayPrimitive]] = {}

        self._layers: dict[CanvasLayerId, _LayerEntry] = {}
        self._invalid_tool_result_logged: set[tuple[str | None, str]] = set()
        self._click_debug_budget = 25

    @property
    def view(self) -> ViewportTransform:
        return self._view

    def set_undo_stack(self, stack: QUndoStack | None) -> None:
        if self._undo_stack is stack:
            return
        if self._undo_stack is not None:
            try:
                self._undo_stack.indexChanged.disconnect(self._on_undo_index_changed)  # type: ignore[arg-type]
            except Exception:
                pass
        self._undo_stack = stack
        if self._undo_stack is not None:
            try:
                self._undo_stack.indexChanged.connect(self._on_undo_index_changed)  # type: ignore[arg-type]
            except Exception:
                pass

    @property
    def undo_stack(self) -> QUndoStack | None:
        return self._undo_stack

    def set_mutation_handler(self, handler: ToolMutationHandler | None) -> None:
        self._mutation_handler = handler

    def set_tool_preference_accessors(
        self,
        *,
        getter: Callable[[str, str, object], object] | None,
        setter: Callable[[str, str, object], None] | None,
    ) -> None:
        self._tool_pref_getter = getter
        self._tool_pref_setter = setter

    def set_status_handler(self, handler: Callable[[str, int], None] | None) -> None:
        self._status_handler = handler

    def screen_to_canvas(self, screen_pos: QPointF) -> QPointF:
        return self._view.widget_to_image(screen_pos)

    def canvas_to_screen(self, canvas_pos: QPointF) -> QPointF:
        return self._view.image_to_widget(canvas_pos)

    @property
    def viewport(self) -> ToolViewport:
        return ToolViewport(
            image_size=QSize(self._view.image_size),
            widget_size=self.size(),
            visible_rect=self._view.image_rect_in_widget(),
            scale=float(self._view.scale),
            offset_widget=QPointF(float(self._view.offset_widget.x()), float(self._view.offset_widget.y())),
        )

    def get_canvas_data(self) -> QImage | QPixmap | None:
        if self._base_image is not None:
            return self._base_image
        return self._base_pixmap

    def get_roi_data(self, rect: QRectF) -> QImage | QPixmap | None:
        img = self._base_image
        if img is None or img.isNull():
            return None
        target = QRectF(rect).toRect()
        if target.isNull():
            return None
        return img.copy(target)

    def hit_test(self, canvas_pos: QPointF) -> CanvasHit | None:
        return self._hit_test(canvas_pos)

    def set_overlay(self, layer_id: str, primitives: list[OverlayPrimitive] | None) -> None:
        key = str(layer_id)
        if not primitives:
            self._overlay_layers.pop(key, None)
        else:
            self._overlay_layers[key] = list(primitives)
        self.update()

    def clear_overlay(self, layer_id: str) -> None:
        self._overlay_layers.pop(str(layer_id), None)
        self.update()

    def set_cursor(self, cursor: Qt.CursorShape | QCursor) -> None:
        self.setCursor(cursor)

    def set_status(self, text: str, *, timeout_ms: int = 0) -> None:
        handler = self._status_handler
        if callable(handler):
            try:
                handler(str(text), int(timeout_ms))
                return
            except Exception:
                log.debug("Canvas status handler failed (best-effort)", exc_info=True)
        log.debug(
            "Canvas status update",
            extra={"operation": "canvas", "phase": "status", "text": str(text), "timeout_ms": int(timeout_ms)},
        )

    def begin_mutation_group(self, description: str) -> None:
        if self._undo_stack is None:
            return
        try:
            self._undo_stack.beginMacro(str(description))
        except Exception:
            log.debug(
                "Undo macro begin failed (best-effort)",
                exc_info=True,
                extra={"operation": "undo", "phase": "begin_macro_error"},
            )

    def end_mutation_group(self) -> None:
        if self._undo_stack is None:
            return
        try:
            self._undo_stack.endMacro()
        except Exception:
            log.debug(
                "Undo macro end failed (best-effort)",
                exc_info=True,
                extra={"operation": "undo", "phase": "end_macro_error"},
            )

    def apply_mutation(self, mutation: ToolMutation, *, description: str, merge_id: str | None = None) -> bool:
        handler = self._mutation_handler
        if handler is None:
            log.warning(
                "Tool mutation ignored (no handler)",
                extra={"operation": "tools", "phase": "mutation_no_handler", "mutation": type(mutation).__name__},
            )
            return False

        try:
            undo_payload = handler.capture_undo_payload(mutation)
        except Exception:
            log.debug(
                "Tool mutation undo capture failed (best-effort)",
                exc_info=True,
                extra={"operation": "tools", "phase": "mutation_capture_error"},
            )
            undo_payload = None

        try:
            applied = bool(handler.apply_mutation(mutation))
        except Exception:
            log.warning(
                "Tool mutation apply failed",
                exc_info=True,
                extra={"operation": "tools", "phase": "mutation_apply_error", "mutation": type(mutation).__name__},
            )
            return False

        if not applied:
            log.warning(
                "Tool mutation rejected",
                extra={"operation": "tools", "phase": "mutation_apply_rejected", "mutation": type(mutation).__name__},
            )
            return False

        if self._undo_stack is not None:
            cmd = ToolMutationCommand(
                mutation=mutation,
                handler=handler,
                description=str(description),
                merge_id=merge_id,
                undo_payload=undo_payload,
                already_applied=True,
            )
            try:
                self._undo_stack.push(cmd)
            except Exception:
                log.warning(
                    "Failed to push tool mutation undo command (best-effort)",
                    exc_info=True,
                    extra={"operation": "undo", "phase": "push_error"},
                )

        log.info(
            "Tool mutation applied",
            extra={
                "operation": "tools",
                "phase": "mutation_applied",
                "mutation": type(mutation).__name__,
                "merge_id": str(merge_id) if merge_id is not None else None,
            },
        )
        self.update()
        return True

    def get_tool_preference(self, tool_id: str, key: str, default: Any) -> Any:
        tool_key = (str(tool_id), str(key))
        getter = self._tool_pref_getter
        if callable(getter):
            try:
                return getter(tool_key[0], tool_key[1], default)
            except Exception:
                log.debug("Tool preference getter failed (best-effort)", exc_info=True)
        return self._tool_prefs.get(tool_key, default)

    def set_tool_preference(self, tool_id: str, key: str, value: Any) -> None:
        tool_key = (str(tool_id), str(key))
        setter = self._tool_pref_setter
        if callable(setter):
            try:
                setter(tool_key[0], tool_key[1], value)
                return
            except Exception:
                log.debug("Tool preference setter failed (best-effort)", exc_info=True)
        self._tool_prefs[tool_key] = value

    def widget_to_image_pos(self, widget_pos: QPointF) -> QPointF:
        return self._view.widget_to_image(widget_pos)

    def image_to_widget_pos(self, image_pos: QPointF) -> QPointF:
        return self._view.image_to_widget(image_pos)

    def set_base_image(self, image: QImage | QPixmap | None, *, fit: bool = True) -> None:
        if image is None:
            self._base_pixmap = None
            self._base_image = None
            self._view.set_image_size(QSize())
            self.update()
            return

        if isinstance(image, QPixmap):
            pix = image
            self._base_image = image.toImage()
        else:
            pix = QPixmap.fromImage(image)
            self._base_image = image
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

    def _clear_tool_subscription(self) -> None:
        unsub = self._tool_unsub
        self._tool_unsub = None
        if callable(unsub):
            try:
                unsub()
            except Exception:
                pass

    def _on_tool_changed(self, tool: object | None) -> None:
        _ = tool
        if self._overlay_layers:
            self._overlay_layers.clear()
            self.update()

    def _on_undo_index_changed(self, *_args: object) -> None:
        self.update()

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

    @staticmethod
    def _color_from_rgba(rgba: tuple[int, int, int, int]) -> QColor:
        r, g, b, a = rgba
        return QColor(int(r), int(g), int(b), int(a))

    def _draw_overlays(self, painter: QPainter) -> None:
        if not self._overlay_layers:
            return

        ordered: list[tuple[int, int, OverlayPrimitive]] = []
        order = 0
        for items in self._overlay_layers.values():
            for item in items:
                ordered.append((int(getattr(item, "z", 0)), order, item))
                order += 1
        ordered.sort(key=lambda item: (item[0], item[1]))

        for _, __, item in ordered:
            self._draw_overlay_primitive(painter, item)

    def _draw_overlay_primitive(self, painter: QPainter, item: OverlayPrimitive) -> None:
        view = self._view
        painter.save()

        try:
            if isinstance(item, OverlayPolyline):
                if len(item.points) < 2:
                    return
                pts = [view.image_to_widget(p) for p in item.points]
                pen = QPen(self._color_from_rgba(item.color))
                pen.setWidth(max(1, int(item.width)))
                pen.setCosmetic(True)
                if item.dash_pattern:
                    pen.setDashPattern([float(x) for x in item.dash_pattern])
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPolyline(QPolygonF(pts))
                return

            if isinstance(item, OverlayPolygon):
                if len(item.points) < 2:
                    return
                pts = [view.image_to_widget(p) for p in item.points]
                if item.stroke_color is None:
                    painter.setPen(Qt.NoPen)
                else:
                    pen = QPen(self._color_from_rgba(item.stroke_color))
                    pen.setWidth(max(1, int(item.stroke_width)))
                    pen.setCosmetic(True)
                    painter.setPen(pen)
                if item.fill_color is None:
                    painter.setBrush(Qt.NoBrush)
                else:
                    painter.setBrush(QBrush(self._color_from_rgba(item.fill_color)))
                painter.drawPolygon(QPolygonF(pts))
                return

            if isinstance(item, OverlayPoints):
                if not item.points:
                    return
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(self._color_from_rgba(item.color)))
                radius = float(item.radius)
                for pt in item.points:
                    wpt = view.image_to_widget(pt)
                    painter.drawEllipse(wpt, radius, radius)
                return

            if isinstance(item, OverlayGradient):
                center = view.image_to_widget(item.center)
                radius = float(item.radius)
                gradient = QRadialGradient(center, radius)
                for pos, rgba in item.color_stops:
                    gradient.setColorAt(float(pos), self._color_from_rgba(rgba))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(gradient))
                painter.drawEllipse(center, radius, radius)
                return

            if isinstance(item, OverlayText):
                pos = view.image_to_widget(item.position)
                painter.setPen(self._color_from_rgba(item.color))
                font = QFont(painter.font())
                font.setPointSize(int(item.font_size))
                painter.setFont(font)
                painter.drawText(pos, str(item.text))
                return
        finally:
            painter.restore()

    def _draw_tool_overlay(self, painter: QPainter) -> None:
        tool = self.tools.active_tool
        if tool is None:
            return
        fn = getattr(tool, "paint_overlay", None)
        if not callable(fn):
            return
        try:
            fn(painter, self._view)
        except Exception:
            log.debug(
                "Tool overlay paint failed (best-effort)",
                exc_info=True,
                extra={"operation": "canvas", "phase": "tool_overlay_error", "tool_id": getattr(tool, "tool_id", None)},
            )

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
        self._draw_overlays(painter)
        self._draw_tool_overlay(painter)

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

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        self._handle_key_event(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        self._handle_key_event(event)

    def _handle_key_event(self, event: QKeyEvent) -> None:
        try:
            tool = self.tools.active_tool
            if tool is not None:
                res = None
                fn = getattr(tool, "on_key_event", None)
                if callable(fn):
                    try:
                        res = fn(event)
                    except Exception:
                        log.warning(
                            "Canvas tool key handler failed",
                            exc_info=True,
                            extra={
                                "operation": "canvas",
                                "phase": "tool_key_error",
                                "tool_id": getattr(tool, "tool_id", None),
                            },
                        )
                        res = ToolResult(consumed=False)
                    res = self._normalize_tool_result(res, tool=tool, phase="key")
                    if res.cursor is not None:
                        self.setCursor(res.cursor)
                    if bool(res.consumed):
                        self.update()
                        event.accept()
                        return

                if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key_Escape:
                    cancel = getattr(tool, "cancel", None)
                    if callable(cancel):
                        try:
                            cancel()
                        except Exception:
                            log.debug("Tool cancel failed (best-effort)", exc_info=True)
                        self.update()
                        event.accept()
                        return

            if event.type() == QEvent.Type.KeyPress:
                super().keyPressEvent(event)
            else:
                super().keyReleaseEvent(event)
        except Exception:
            log.exception(
                "Canvas key event failed",
                extra={"operation": "canvas", "phase": "key_event_error"},
            )
            if event.type() == QEvent.Type.KeyPress:
                super().keyPressEvent(event)
            else:
                super().keyReleaseEvent(event)

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
