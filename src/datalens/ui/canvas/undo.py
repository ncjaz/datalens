from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand, QUndoStack

from datalens.core.logging import get_logger
from datalens.ui.canvas.layers.vector_layer import VectorLayer, VectorShape
from datalens.ui.canvas.tools.edit_events import CanvasEditEvent, CanvasEditKind


log = get_logger(__name__)


def _label_for_edit(edit: CanvasEditEvent) -> str:
    kind = edit.kind
    if kind == CanvasEditKind.VERTEX_MOVED:
        return "Move vertex"
    if kind == CanvasEditKind.SHAPE_TRANSLATED:
        return "Move shape"
    if kind == CanvasEditKind.VERTEX_INSERTED:
        return "Insert vertex"
    if kind == CanvasEditKind.VERTEX_DELETED:
        return "Delete vertex"
    if kind == CanvasEditKind.SHAPE_DELETED:
        return "Delete shape"
    return "Edit"


def _qpointf_copy(pt: QPointF) -> QPointF:
    return QPointF(float(pt.x()), float(pt.y()))


class VectorLayerUndoCommand(QUndoCommand):
    """
    Undoable edit command for `VectorLayer`.

    This bridges UI-thread tool edits into Qt's undo stack so higher-level UI can
    route Ctrl+Z/Ctrl+Y via `QUndoGroup` to the active workspace stack.
    """

    def __init__(
        self,
        *,
        layer: VectorLayer,
        edit: CanvasEditEvent,
        already_applied: bool = True,
    ) -> None:
        super().__init__(_label_for_edit(edit))
        self._layer = layer
        self._edit = edit
        self._already_applied = bool(already_applied)
        self._first_redo = True

    def redo(self) -> None:
        if self._already_applied and self._first_redo:
            self._first_redo = False
            return
        self._first_redo = False
        log.debug(
            "Undo command redo",
            extra={
                "operation": "undo",
                "phase": "command_redo",
                "kind": str(self._edit.kind),
                "layer_id": str(self._edit.layer_id),
                "shape_id": str(self._edit.shape_id),
                "vertex_index": int(self._edit.vertex_index) if self._edit.vertex_index is not None else None,
            },
        )
        self._apply_forward()

    def undo(self) -> None:
        log.debug(
            "Undo command undo",
            extra={
                "operation": "undo",
                "phase": "command_undo",
                "kind": str(self._edit.kind),
                "layer_id": str(self._edit.layer_id),
                "shape_id": str(self._edit.shape_id),
                "vertex_index": int(self._edit.vertex_index) if self._edit.vertex_index is not None else None,
            },
        )
        self._apply_reverse()

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def _apply_forward(self) -> None:
        edit = self._edit
        kind = edit.kind
        if kind == CanvasEditKind.VERTEX_MOVED:
            self._apply_vertex_position(edit.shape_id, edit.vertex_index, edit.to_pos)
        elif kind == CanvasEditKind.SHAPE_TRANSLATED:
            self._apply_shape_translate(edit.shape_id, edit.dx, edit.dy)
        elif kind == CanvasEditKind.VERTEX_INSERTED:
            self._apply_vertex_insert(edit.shape_id, edit.vertex_index, edit.to_pos)
        elif kind == CanvasEditKind.VERTEX_DELETED:
            self._apply_vertex_delete(edit.shape_id, edit.vertex_index)
        elif kind == CanvasEditKind.SHAPE_DELETED:
            self._layer.remove_shape(edit.shape_id)
        else:
            return

    def _apply_reverse(self) -> None:
        edit = self._edit
        kind = edit.kind
        if kind == CanvasEditKind.VERTEX_MOVED:
            self._apply_vertex_position(edit.shape_id, edit.vertex_index, edit.from_pos)
        elif kind == CanvasEditKind.SHAPE_TRANSLATED:
            dx = -float(edit.dx or 0.0)
            dy = -float(edit.dy or 0.0)
            self._apply_shape_translate(edit.shape_id, dx, dy)
        elif kind == CanvasEditKind.VERTEX_INSERTED:
            self._apply_vertex_delete(edit.shape_id, edit.vertex_index)
        elif kind == CanvasEditKind.VERTEX_DELETED:
            self._apply_vertex_insert(edit.shape_id, edit.vertex_index, edit.from_pos)
        elif kind == CanvasEditKind.SHAPE_DELETED:
            payload = edit.undo_payload
            if isinstance(payload, VectorShape):
                self._layer.upsert_shape(payload)
        else:
            return

    # ------------------------------------------------------------------
    # Vector ops
    # ------------------------------------------------------------------

    def _apply_vertex_position(
        self,
        shape_id: str,
        vertex_index: int | None,
        pos: QPointF | None,
    ) -> None:
        if vertex_index is None or pos is None:
            return
        shape = self._layer.get_shape(shape_id)
        if shape is None:
            return
        pts = list(shape.points)
        if not (0 <= int(vertex_index) < len(pts)):
            return
        pts[int(vertex_index)] = _qpointf_copy(pos)
        self._layer.upsert_shape(
            VectorShape(
                shape_id=shape.shape_id,
                points=tuple(pts),
                closed=shape.closed,
                style=shape.style,
            )
        )

    def _apply_shape_translate(self, shape_id: str, dx: float | None, dy: float | None) -> None:
        dx = float(dx or 0.0)
        dy = float(dy or 0.0)
        if dx == 0.0 and dy == 0.0:
            return
        shape = self._layer.get_shape(shape_id)
        if shape is None:
            return
        pts = [QPointF(float(p.x()) + dx, float(p.y()) + dy) for p in shape.points]
        self._layer.upsert_shape(
            VectorShape(
                shape_id=shape.shape_id,
                points=tuple(pts),
                closed=shape.closed,
                style=shape.style,
            )
        )

    def _apply_vertex_insert(
        self,
        shape_id: str,
        vertex_index: int | None,
        pos: QPointF | None,
    ) -> None:
        if vertex_index is None or pos is None:
            return
        shape = self._layer.get_shape(shape_id)
        if shape is None:
            return
        pts = list(shape.points)
        idx = max(0, min(len(pts), int(vertex_index)))
        pts.insert(idx, _qpointf_copy(pos))
        self._layer.upsert_shape(
            VectorShape(
                shape_id=shape.shape_id,
                points=tuple(pts),
                closed=shape.closed,
                style=shape.style,
            )
        )

    def _apply_vertex_delete(self, shape_id: str, vertex_index: int | None) -> None:
        if vertex_index is None:
            return
        shape = self._layer.get_shape(shape_id)
        if shape is None:
            return
        pts = list(shape.points)
        idx = int(vertex_index)
        if not (0 <= idx < len(pts)):
            return
        pts.pop(idx)
        self._layer.upsert_shape(
            VectorShape(
                shape_id=shape.shape_id,
                points=tuple(pts),
                closed=shape.closed,
                style=shape.style,
            )
        )


class VectorLayerUndoAdapter:
    """
    Helper that pushes `VectorLayerUndoCommand` instances onto a QUndoStack.

    This is intentionally thin: tools own the UI interaction; the adapter only
    converts commit events into undoable commands.
    """

    def __init__(self, *, layer: VectorLayer, stack: QUndoStack) -> None:
        self._layer = layer
        self._stack = stack

    def handle_edit(self, edit: CanvasEditEvent) -> None:
        if str(edit.layer_id) != str(self._layer.layer_id):
            return
        if edit.kind in {CanvasEditKind.SHAPE_SELECTED, CanvasEditKind.VERTEX_SELECTED}:
            return
        if edit.kind == CanvasEditKind.SHAPE_TRANSLATED and not (edit.dx or edit.dy):
            return
        cmd = VectorLayerUndoCommand(layer=self._layer, edit=edit, already_applied=True)
        try:
            self._stack.push(cmd)
        except Exception:
            log.warning(
                "Failed to push undo command (best-effort)",
                exc_info=True,
                extra={
                    "operation": "undo",
                    "phase": "push_error",
                    "kind": str(edit.kind),
                    "layer_id": str(edit.layer_id),
                    "shape_id": str(edit.shape_id),
                },
            )


__all__ = ["VectorLayerUndoAdapter", "VectorLayerUndoCommand"]
