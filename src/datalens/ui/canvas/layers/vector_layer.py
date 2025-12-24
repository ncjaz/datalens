from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import Any, Iterable

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from datalens.core.logging import get_logger
from datalens.ui.canvas.layers.base import CanvasHit, CanvasLayer, CanvasLayerId, HitKind
from datalens.ui.canvas.viewport import ViewportTransform

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class VectorStyle:
    """
    Styling for vector overlays.

    Kept intentionally small for v0. If we need richer styling later (dashed lines,
    per-vertex handles, labels), we'll add fields rather than introducing many
    tiny classes.
    """

    stroke_hex: str = "#F9A826"
    stroke_width_px: int = 2
    stroke_alpha: float = 1.0

    # Optional fill for closed polygons (v0). If set, the polygon can render a
    # translucent interior fill. This is a UI-only concern (no I/O).
    fill_hex: str | None = None
    fill_alpha: float = 0.12
    fill_on_select_only: bool = True


@dataclass(frozen=True, slots=True)
class VectorShape:
    """
    A shape drawn in image coordinates.

    - `points` are in image coordinates.
    - `closed=True` means render a polygon; `closed=False` means polyline.
    """

    shape_id: str
    points: tuple[QPointF, ...]
    closed: bool = False
    style: VectorStyle = field(default_factory=VectorStyle)


def _qcolor(hex_color: str, alpha: float) -> QColor:
    c = QColor(str(hex_color))
    c.setAlphaF(max(0.0, min(1.0, float(alpha))))
    return c


def _dist_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    denom = abx * abx + aby * aby
    if denom <= 1e-12:
        return hypot(px - ax, py - ay)
    t = (apx * abx + apy * aby) / denom
    t = max(0.0, min(1.0, t))
    cx = ax + t * abx
    cy = ay + t * aby
    return hypot(px - cx, py - cy)


def _point_in_polygon(x: float, y: float, pts: list[QPointF]) -> bool:
    """
    Ray-casting point-in-polygon test (widget coordinates).

    Points on the boundary are treated as "inside" for selection UX.
    """
    if len(pts) < 3:
        return False

    inside = False
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        ax = float(a.x())
        ay = float(a.y())
        bx = float(b.x())
        by = float(b.y())

        # Check if point is on the segment (boundary considered inside).
        d = _dist_point_to_segment(x, y, ax, ay, bx, by)
        if d <= 1.0:
            return True

        # Ray casting toggle.
        intersects = (ay > y) != (by > y)
        if intersects:
            # Avoid division by zero; at this point (ay>y)!=(by>y) implies by-ay != 0.
            x_at_y = ax + (y - ay) * (bx - ax) / (by - ay)
            if x < x_at_y:
                inside = not inside

    return inside


class VectorLayer(CanvasLayer):
    """
    Simple vector overlay layer (v0).

    Supports hit-testing for:
    - vertices (returns `HitKind.VERTEX` with payload {shape_id, vertex_index})
    - edges (returns `HitKind.EDGE` with payload {shape_id, edge_index})
    """

    def __init__(
        self,
        *,
        layer_id: CanvasLayerId,
        shapes: Iterable[VectorShape] = (),
        vertex_hit_radius_px: int = 8,
        edge_hit_radius_px: int = 6,
    ) -> None:
        self.layer_id = str(layer_id)
        self._shapes: dict[str, VectorShape] = {s.shape_id: s for s in shapes}
        self._vertex_hit_radius_px = max(1, int(vertex_hit_radius_px))
        self._edge_hit_radius_px = max(1, int(edge_hit_radius_px))
        self._selected_shape_id: str | None = None
        self._selected_vertex_index: int | None = None

    def set_shapes(self, shapes: Iterable[VectorShape]) -> None:
        self._shapes = {s.shape_id: s for s in shapes}

    def upsert_shape(self, shape: VectorShape) -> None:
        self._shapes[str(shape.shape_id)] = shape

    def remove_shape(self, shape_id: str) -> None:
        self._shapes.pop(str(shape_id), None)

    def get_shape(self, shape_id: str) -> VectorShape | None:
        return self._shapes.get(str(shape_id))

    def shapes(self) -> tuple[VectorShape, ...]:
        return tuple(self._shapes.values())

    def set_selected_vertex(self, shape_id: str | None, vertex_index: int | None) -> None:
        if shape_id is None or vertex_index is None:
            self._selected_shape_id = None
            self._selected_vertex_index = None
            return
        self._selected_shape_id = str(shape_id)
        self._selected_vertex_index = int(vertex_index)

    def set_selected_shape(self, shape_id: str | None) -> None:
        if shape_id is None:
            self._selected_shape_id = None
            self._selected_vertex_index = None
            return
        self._selected_shape_id = str(shape_id)
        self._selected_vertex_index = None

    def selected_vertex(self) -> tuple[str, int] | None:
        if self._selected_shape_id is None or self._selected_vertex_index is None:
            return None
        return (str(self._selected_shape_id), int(self._selected_vertex_index))

    def selected_shape(self) -> str | None:
        return str(self._selected_shape_id) if self._selected_shape_id is not None else None

    def draw(self, painter: QPainter, view: ViewportTransform) -> None:
        for shape in self._shapes.values():
            if len(shape.points) < 1:
                continue

            pen = QPen(_qcolor(shape.style.stroke_hex, shape.style.stroke_alpha))
            pen.setWidth(max(1, int(shape.style.stroke_width_px)))
            pen.setCosmetic(True)  # keep thickness stable when zooming
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)

            pts = [view.image_to_widget(p) for p in shape.points]
            is_shape_selected = self._selected_shape_id is not None and str(self._selected_shape_id) == str(shape.shape_id) and self._selected_vertex_index is None
            if shape.closed and len(pts) >= 3 and shape.style.fill_hex is not None:
                if (not bool(shape.style.fill_on_select_only)) or is_shape_selected:
                    painter.setBrush(_qcolor(shape.style.fill_hex, float(shape.style.fill_alpha)))
                else:
                    painter.setBrush(Qt.NoBrush)
            else:
                painter.setBrush(Qt.NoBrush)

            if len(pts) == 1:
                p = pts[0]
                r = 2.5
                painter.drawEllipse(p, r, r)
                continue

            if shape.closed and len(pts) >= 3:
                painter.drawPolygon(pts)
            else:
                for i in range(len(pts) - 1):
                    painter.drawLine(pts[i], pts[i + 1])

            # Vertex handles (debug-friendly): always draw small circles.
            handle_radius = 4.0
            selected = self.selected_vertex()
            for idx, p in enumerate(pts):
                is_selected = selected is not None and selected[0] == shape.shape_id and selected[1] == idx
                fill = _qcolor(shape.style.stroke_hex, 0.95 if is_selected else 0.25)
                painter.setBrush(fill)
                painter.drawEllipse(p, handle_radius, handle_radius)

    def hit_test(self, image_pos: QPointF, view: ViewportTransform) -> CanvasHit | None:
        if not self._shapes:
            return None

        widget_pt = view.image_to_widget(image_pos)
        wx = float(widget_pt.x())
        wy = float(widget_pt.y())

        best_vertex: tuple[float, str, int] | None = None
        best_edge: tuple[float, str, int] | None = None

        for shape in self._shapes.values():
            pts_w = [view.image_to_widget(p) for p in shape.points]
            for idx, p in enumerate(pts_w):
                d = hypot(wx - float(p.x()), wy - float(p.y()))
                if d <= float(self._vertex_hit_radius_px) and (best_vertex is None or d < best_vertex[0]):
                    best_vertex = (d, shape.shape_id, idx)

            if len(pts_w) >= 2:
                edge_count = len(pts_w) - 1
                for i in range(edge_count):
                    a = pts_w[i]
                    b = pts_w[i + 1]
                    d = _dist_point_to_segment(wx, wy, float(a.x()), float(a.y()), float(b.x()), float(b.y()))
                    if d <= float(self._edge_hit_radius_px) and (best_edge is None or d < best_edge[0]):
                        best_edge = (d, shape.shape_id, i)
                if shape.closed and len(pts_w) >= 3:
                    a = pts_w[-1]
                    b = pts_w[0]
                    d = _dist_point_to_segment(wx, wy, float(a.x()), float(a.y()), float(b.x()), float(b.y()))
                    if d <= float(self._edge_hit_radius_px) and (best_edge is None or d < best_edge[0]):
                        best_edge = (d, shape.shape_id, edge_count)

        if best_vertex is not None:
            _, shape_id, vertex_index = best_vertex
            return CanvasHit(
                layer_id=self.layer_id,
                kind=HitKind.VERTEX,
                image_pos=image_pos,
                payload={"shape_id": str(shape_id), "vertex_index": int(vertex_index)},
            )

        if best_edge is not None:
            _, shape_id, edge_index = best_edge
            return CanvasHit(
                layer_id=self.layer_id,
                kind=HitKind.EDGE,
                image_pos=image_pos,
                payload={"shape_id": str(shape_id), "edge_index": int(edge_index)},
            )

        # Shape interior hits (closed polygons only). If multiple polygons overlap,
        # treat later-inserted shapes as "on top" (draw order).
        containing: list[str] = []
        shapes = list(self._shapes.values())
        for shape in reversed(shapes):
            if not shape.closed or len(shape.points) < 3:
                continue
            pts_w = [view.image_to_widget(p) for p in shape.points]
            if _point_in_polygon(wx, wy, pts_w):
                containing.append(str(shape.shape_id))

        if containing:
            return CanvasHit(
                layer_id=self.layer_id,
                kind=HitKind.SHAPE,
                image_pos=image_pos,
                payload={"shape_ids": containing, "shape_id": containing[0]},
            )

        return None


__all__ = ["VectorLayer", "VectorShape", "VectorStyle"]
