from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QCursor, QMouseEvent, QWheelEvent

from datalens.core.logging import get_logger
from datalens.ui.canvas.layers.base import HitKind
from datalens.ui.canvas.layers.vector_layer import VectorLayer, VectorShape
from datalens.ui.canvas.tools.base import CanvasTool, ToolResult
from datalens.ui.canvas.tools.edit_events import CanvasEditEvent, CanvasEditKind
from datalens.ui.canvas.viewport import ViewportTransform

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SelectionState:
    shape_id: str
    vertex_index: int


class SelectEditTool(CanvasTool):
    """
    Minimal interactive vector editing tool (v0).

    Behaviors:
    - Click vertex: select it.
    - Drag selected vertex: move it.
    - Click edge: insert a vertex at the click position (V1 pain point).
    - Press Delete (wired by widget_test): delete selected vertex.

    This is a UI-thread tool: it mutates in-memory overlay geometry only.
    """

    tool_id = "select_edit.v0"

    def __init__(
        self,
        *,
        vector_layer: VectorLayer,
        on_selection_changed: Callable[[SelectionState | None], None] | None = None,
        on_edit: Callable[[CanvasEditEvent], None] | None = None,
    ) -> None:
        self._layer = vector_layer
        self._on_selection_changed = on_selection_changed
        self._on_edit = on_edit
        self._dragging = False
        self._drag_vertex_from: QPointF | None = None
        self._drag_vertex_to: QPointF | None = None
        self._shape_drag_anchor: QPointF | None = None
        self._shape_drag_total_dx = 0.0
        self._shape_drag_total_dy = 0.0
        self._selected: SelectionState | None = None

    @property
    def selected(self) -> SelectionState | None:
        return self._selected

    def on_activate(self) -> None:
        log.info("Select/edit tool activated", extra={"operation": "canvas", "phase": "tool_activate", "tool_id": self.tool_id})

    def on_deactivate(self) -> None:
        self._dragging = False
        self._drag_vertex_from = None
        self._drag_vertex_to = None
        self._shape_drag_anchor = None
        self._shape_drag_total_dx = 0.0
        self._shape_drag_total_dy = 0.0
        self._set_selected(None)
        log.info("Select/edit tool deactivated", extra={"operation": "canvas", "phase": "tool_deactivate", "tool_id": self.tool_id})

    def _emit_edit(self, event: CanvasEditEvent) -> None:
        if self._on_edit is None:
            return
        try:
            self._on_edit(event)
        except Exception:
            log.warning(
                "Canvas tool edit callback failed (best-effort)",
                exc_info=True,
                extra={
                    "operation": "canvas",
                    "phase": "edit_callback_error",
                    "tool_id": self.tool_id,
                    "kind": str(event.kind),
                    "layer_id": str(event.layer_id),
                    "shape_id": str(event.shape_id),
                },
            )

    def delete_selected_vertex(self) -> bool:
        sel = self._selected
        if sel is None:
            log.debug("Delete requested with no selection", extra={"operation": "canvas", "phase": "delete_no_selection"})
            return False

        shapes = {s.shape_id: s for s in self._layer.shapes()}
        current = shapes.get(sel.shape_id)
        if current is None:
            self._set_selected(None)
            return False

        if sel.vertex_index < 0:
            undo_payload = VectorShape(
                shape_id=current.shape_id,
                points=tuple(QPointF(float(p.x()), float(p.y())) for p in current.points),
                closed=current.closed,
                style=current.style,
            )
            self._layer.remove_shape(current.shape_id)
            self._set_selected(None)
            self._emit_edit(
                CanvasEditEvent(
                    kind=CanvasEditKind.SHAPE_DELETED,
                    layer_id=self._layer.layer_id,
                    shape_id=str(current.shape_id),
                    undo_payload=undo_payload,
                )
            )
            log.info(
                "Deleted selected shape",
                extra={"operation": "canvas", "phase": "delete_shape", "shape_id": current.shape_id},
            )
            return True

        pts = list(current.points)
        if not (0 <= sel.vertex_index < len(pts)):
            self._set_selected(None)
            return False

        removed_pt = pts.pop(sel.vertex_index)

        min_points = 3 if current.closed else 2
        if current.closed and len(pts) < min_points:
            undo_payload = VectorShape(
                shape_id=current.shape_id,
                points=tuple(QPointF(float(p.x()), float(p.y())) for p in current.points),
                closed=current.closed,
                style=current.style,
            )
            self._layer.remove_shape(current.shape_id)
            self._set_selected(None)
            self._emit_edit(
                CanvasEditEvent(
                    kind=CanvasEditKind.SHAPE_DELETED,
                    layer_id=self._layer.layer_id,
                    shape_id=str(current.shape_id),
                    undo_payload=undo_payload,
                )
            )
            log.info(
                "Deleted vertex removed shape (too few points)",
                extra={"operation": "canvas", "phase": "delete_vertex", "shape_id": current.shape_id},
            )
            return True

        if (not current.closed) and len(pts) < min_points:
            undo_payload = VectorShape(
                shape_id=current.shape_id,
                points=tuple(QPointF(float(p.x()), float(p.y())) for p in current.points),
                closed=current.closed,
                style=current.style,
            )
            self._layer.remove_shape(current.shape_id)
            self._set_selected(None)
            self._emit_edit(
                CanvasEditEvent(
                    kind=CanvasEditKind.SHAPE_DELETED,
                    layer_id=self._layer.layer_id,
                    shape_id=str(current.shape_id),
                    undo_payload=undo_payload,
                )
            )
            log.info(
                "Deleted vertex removed shape (too few points)",
                extra={"operation": "canvas", "phase": "delete_vertex", "shape_id": current.shape_id},
            )
            return True

        new_index = max(0, min(len(pts) - 1, sel.vertex_index))
        updated = VectorShape(
            shape_id=current.shape_id,
            points=tuple(pts),
            closed=current.closed,
            style=current.style,
        )
        self._layer.upsert_shape(updated)
        self._set_selected(SelectionState(shape_id=current.shape_id, vertex_index=new_index))

        self._emit_edit(
            CanvasEditEvent(
                kind=CanvasEditKind.VERTEX_DELETED,
                layer_id=self._layer.layer_id,
                shape_id=str(current.shape_id),
                vertex_index=int(sel.vertex_index),
                from_pos=QPointF(float(removed_pt.x()), float(removed_pt.y())),
            )
        )
        log.info(
            "Deleted selected vertex",
            extra={"operation": "canvas", "phase": "delete_vertex", "shape_id": current.shape_id, "vertex_index": sel.vertex_index},
        )
        return True

    def on_mouse_event(self, event: QMouseEvent, view: ViewportTransform, image_pos: QPointF) -> ToolResult:
        et = QEvent.Type(event.type())
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            hit = self._layer.hit_test(image_pos, view)
            if hit is None:
                self._set_selected(None)
                return ToolResult(consumed=False)

            if hit.kind == HitKind.VERTEX:
                shape_id = str(hit.payload.get("shape_id", ""))
                vertex_index = int(hit.payload.get("vertex_index", -1))
                if shape_id and vertex_index >= 0:
                    self._set_selected(SelectionState(shape_id=shape_id, vertex_index=vertex_index))
                    self._dragging = True
                    self._drag_vertex_from = QPointF(float(image_pos.x()), float(image_pos.y()))
                    self._drag_vertex_to = QPointF(float(image_pos.x()), float(image_pos.y()))
                    self._shape_drag_anchor = None
                    self._shape_drag_total_dx = 0.0
                    self._shape_drag_total_dy = 0.0
                    self._emit_edit(
                        CanvasEditEvent(
                            kind=CanvasEditKind.VERTEX_SELECTED,
                            layer_id=self._layer.layer_id,
                            shape_id=str(shape_id),
                            vertex_index=int(vertex_index),
                        )
                    )
                    return ToolResult(consumed=True, cursor=QCursor(Qt.CursorShape.ClosedHandCursor))

            if hit.kind == HitKind.EDGE:
                inserted = self._insert_vertex_on_edge(hit, image_pos=image_pos)
                if inserted is not None:
                    self._set_selected(inserted)
                    self._dragging = True
                    self._drag_vertex_from = QPointF(float(image_pos.x()), float(image_pos.y()))
                    self._drag_vertex_to = QPointF(float(image_pos.x()), float(image_pos.y()))
                    self._shape_drag_anchor = None
                    self._shape_drag_total_dx = 0.0
                    self._shape_drag_total_dy = 0.0
                    self._emit_edit(
                        CanvasEditEvent(
                            kind=CanvasEditKind.VERTEX_INSERTED,
                            layer_id=self._layer.layer_id,
                            shape_id=str(inserted.shape_id),
                            vertex_index=int(inserted.vertex_index),
                            to_pos=QPointF(float(image_pos.x()), float(image_pos.y())),
                        )
                    )
                    return ToolResult(consumed=True, cursor=QCursor(Qt.CursorShape.ClosedHandCursor))

            if hit.kind == HitKind.SHAPE:
                selected = self._select_next_shape(hit)
                if selected is not None:
                    self._set_selected(selected)
                    self._dragging = True
                    self._drag_vertex_from = None
                    self._drag_vertex_to = None
                    self._shape_drag_anchor = QPointF(float(image_pos.x()), float(image_pos.y()))
                    self._shape_drag_total_dx = 0.0
                    self._shape_drag_total_dy = 0.0
                    self._emit_edit(
                        CanvasEditEvent(
                            kind=CanvasEditKind.SHAPE_SELECTED,
                            layer_id=self._layer.layer_id,
                            shape_id=str(selected.shape_id),
                        )
                    )
                    return ToolResult(consumed=True, cursor=QCursor(Qt.CursorShape.OpenHandCursor))

            return ToolResult(consumed=False)

        if et == QEvent.Type.MouseMove and self._dragging and self._selected is not None and bool(event.buttons() & Qt.MouseButton.LeftButton):
            moved = self._move_selected_vertex(image_pos)
            if not moved and self._selected.vertex_index < 0:
                moved = self._move_selected_shape(image_pos)
            if moved:
                return ToolResult(consumed=True, cursor=QCursor(Qt.CursorShape.ClosedHandCursor))
            return ToolResult(consumed=False)

        if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            sel = self._selected
            if sel is not None and sel.vertex_index >= 0 and self._drag_vertex_from is not None and self._drag_vertex_to is not None:
                if (self._drag_vertex_from.x() != self._drag_vertex_to.x()) or (self._drag_vertex_from.y() != self._drag_vertex_to.y()):
                    self._emit_edit(
                        CanvasEditEvent(
                            kind=CanvasEditKind.VERTEX_MOVED,
                            layer_id=self._layer.layer_id,
                            shape_id=str(sel.shape_id),
                            vertex_index=int(sel.vertex_index),
                            from_pos=self._drag_vertex_from,
                            to_pos=self._drag_vertex_to,
                        )
                    )
            if (
                sel is not None
                and sel.vertex_index < 0
                and (self._shape_drag_total_dx != 0.0 or self._shape_drag_total_dy != 0.0)
                and self._shape_drag_anchor is not None
            ):
                self._emit_edit(
                    CanvasEditEvent(
                        kind=CanvasEditKind.SHAPE_TRANSLATED,
                        layer_id=self._layer.layer_id,
                        shape_id=str(sel.shape_id),
                        dx=float(self._shape_drag_total_dx),
                        dy=float(self._shape_drag_total_dy),
                    )
                )
            self._dragging = False
            self._drag_vertex_from = None
            self._drag_vertex_to = None
            self._shape_drag_anchor = None
            self._shape_drag_total_dx = 0.0
            self._shape_drag_total_dy = 0.0
            return ToolResult(consumed=self._selected is not None, cursor=QCursor(Qt.CursorShape.ArrowCursor))

        return ToolResult(consumed=False)

    def on_wheel_event(self, event: QWheelEvent, view: ViewportTransform, image_pos: QPointF) -> ToolResult:
        _ = (event, view, image_pos)
        return ToolResult(consumed=False)

    def _set_selected(self, sel: SelectionState | None) -> None:
        self._selected = sel
        if sel is None:
            self._layer.set_selected_shape(None)
        else:
            if sel.vertex_index < 0:
                self._layer.set_selected_shape(sel.shape_id)
            else:
                self._layer.set_selected_vertex(sel.shape_id, sel.vertex_index)

        if self._on_selection_changed is not None:
            try:
                self._on_selection_changed(sel)
            except Exception:
                log.debug("Selection changed callback failed (best-effort)", exc_info=True)

    def _insert_vertex_on_edge(self, hit, *, image_pos: QPointF) -> SelectionState | None:
        shape_id = str(hit.payload.get("shape_id", ""))
        edge_index = int(hit.payload.get("edge_index", -1))
        if not shape_id or edge_index < 0:
            return None

        shapes = {s.shape_id: s for s in self._layer.shapes()}
        current = shapes.get(shape_id)
        if current is None or len(current.points) < 2:
            return None

        pts = list(current.points)
        insert_at = max(0, min(len(pts), edge_index + 1))
        pts.insert(insert_at, QPointF(float(image_pos.x()), float(image_pos.y())))
        updated = VectorShape(shape_id=current.shape_id, points=tuple(pts), closed=current.closed, style=current.style)
        self._layer.upsert_shape(updated)

        log.info(
            "Inserted vertex on edge",
            extra={"operation": "canvas", "phase": "insert_vertex", "shape_id": current.shape_id, "edge_index": edge_index},
        )
        return SelectionState(shape_id=current.shape_id, vertex_index=insert_at)

    def _move_selected_vertex(self, image_pos: QPointF) -> bool:
        sel = self._selected
        if sel is None:
            return False
        if sel.vertex_index < 0:
            return False

        shapes = {s.shape_id: s for s in self._layer.shapes()}
        current = shapes.get(sel.shape_id)
        if current is None:
            self._set_selected(None)
            return False

        pts = list(current.points)
        if not (0 <= sel.vertex_index < len(pts)):
            self._set_selected(None)
            return False

        pts[sel.vertex_index] = QPointF(float(image_pos.x()), float(image_pos.y()))
        updated = VectorShape(shape_id=current.shape_id, points=tuple(pts), closed=current.closed, style=current.style)
        self._layer.upsert_shape(updated)
        self._drag_vertex_to = QPointF(float(image_pos.x()), float(image_pos.y()))
        return True

    def _move_selected_shape(self, image_pos: QPointF) -> bool:
        sel = self._selected
        if sel is None or sel.vertex_index >= 0:
            return False

        anchor = self._shape_drag_anchor
        if anchor is None:
            self._shape_drag_anchor = QPointF(float(image_pos.x()), float(image_pos.y()))
            return False

        dx = float(image_pos.x() - anchor.x())
        dy = float(image_pos.y() - anchor.y())
        if dx == 0.0 and dy == 0.0:
            return False

        shapes = {s.shape_id: s for s in self._layer.shapes()}
        current = shapes.get(sel.shape_id)
        if current is None:
            self._set_selected(None)
            self._shape_drag_anchor = None
            return False

        moved_points = [QPointF(float(p.x() + dx), float(p.y() + dy)) for p in current.points]
        updated = VectorShape(shape_id=current.shape_id, points=tuple(moved_points), closed=current.closed, style=current.style)
        self._layer.upsert_shape(updated)

        self._shape_drag_anchor = QPointF(float(image_pos.x()), float(image_pos.y()))
        self._shape_drag_total_dx += dx
        self._shape_drag_total_dy += dy
        return True

    def _select_next_shape(self, hit) -> SelectionState | None:
        candidates = hit.payload.get("shape_ids")
        if not isinstance(candidates, list) or not candidates:
            return None

        ids = [str(x) for x in candidates if str(x)]
        if not ids:
            return None

        current = self._selected.shape_id if self._selected is not None else None
        if current in ids:
            idx = ids.index(current)
            chosen = ids[(idx + 1) % len(ids)]
        else:
            chosen = ids[0]

        log.info(
            "Selected shape",
            extra={"operation": "canvas", "phase": "select_shape", "shape_id": chosen, "candidates": len(ids)},
        )
        return SelectionState(shape_id=chosen, vertex_index=-1)


__all__ = ["SelectEditTool", "SelectionState"]
