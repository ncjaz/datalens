from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QPointF

from datalens.ui.canvas.layers.base import CanvasLayerId


class CanvasEditKind(str, Enum):
    """
    High-level edit kinds emitted by canvas tools.

    This is intentionally small and "changes-only": events only populate fields
    relevant to the edit, so callers can persist without re-serializing the
    entire shape on every interaction.
    """

    SHAPE_SELECTED = "shape_selected"
    SHAPE_TRANSLATED = "shape_translated"

    VERTEX_SELECTED = "vertex_selected"
    VERTEX_INSERTED = "vertex_inserted"
    VERTEX_MOVED = "vertex_moved"
    VERTEX_DELETED = "vertex_deleted"

    SHAPE_DELETED = "shape_deleted"


@dataclass(frozen=True, slots=True)
class CanvasEditEvent:
    """
    A changes-only edit event emitted by a tool.

    Rules:
    - For move/translate operations, provide old/new positions or dx/dy.
    - For selection operations, do not imply persistence; it's UI state only.
    - `shape_id` is always present for shape/vertex operations.
    - `vertex_index` is only set for vertex-specific operations.
    """

    kind: CanvasEditKind
    layer_id: CanvasLayerId
    shape_id: str

    vertex_index: int | None = None

    # Vertex move changes-only
    from_pos: QPointF | None = None
    to_pos: QPointF | None = None

    # Shape translate changes-only
    dx: float | None = None
    dy: float | None = None


__all__ = ["CanvasEditEvent", "CanvasEditKind"]

