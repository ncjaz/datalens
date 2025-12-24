"""
Plugin-facing tools API (V2).

This module defines the stable tool metadata, mutation, and overlay contracts
used by toolbars and canvas hosts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QCursor, QIcon, QImage, QPixmap

from datalens.ui.canvas.layers.base import CanvasHit
from datalens.ui.canvas.tools.base import CanvasTool
from datalens.ui.theme.app_theme import AppTheme


class ToolKind(str, Enum):
    MODE = "mode"
    ACTION = "action"
    TOGGLE = "toggle"


@dataclass(frozen=True)
class ToolViewport:
    """
    Snapshot of canvas viewport state.

    `visible_rect` is in widget coordinates (the image rect drawn in the widget).
    """

    image_size: QSize
    widget_size: QSize
    visible_rect: QRectF
    scale: float
    offset_widget: QPointF


@dataclass(frozen=True)
class ToolDefinition:
    """
    Metadata for a tool contributed by a plugin.
    """

    tool_id: str
    label: str
    tooltip: str
    icon_factory: Callable[[AppTheme], QIcon]
    kind: ToolKind
    default_order: int
    section: str = "tools"
    canvas_types: frozenset[str] = field(default_factory=lambda: frozenset({"image_2d"}))
    default_shortcuts: tuple[str, ...] = field(default_factory=tuple)
    create: Callable[[ToolHost], CanvasTool]
    settings_schema: dict | None = None


@dataclass(frozen=True)
class AddShapeMutation:
    shape_type: str
    points: tuple[QPointF, ...]
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UpdateVerticesMutation:
    shape_id: str
    vertex_updates: dict[int, QPointF]


@dataclass(frozen=True)
class DeleteShapesMutation:
    shape_ids: tuple[str, ...]


@dataclass(frozen=True)
class SetAttributeMutation:
    shape_ids: tuple[str, ...]
    attribute_name: str
    value: Any


@dataclass(frozen=True)
class PaintStrokeMutation:
    layer_id: str
    stroke_points: tuple[QPointF, ...]
    brush_size: float
    mode: str
    color: tuple[int, int, int, int] | None = None


ToolMutation = (
    AddShapeMutation
    | UpdateVerticesMutation
    | DeleteShapesMutation
    | SetAttributeMutation
    | PaintStrokeMutation
)


@dataclass(frozen=True)
class OverlayPolyline:
    points: tuple[QPointF, ...]
    color: tuple[int, int, int, int]
    width: float = 2.0
    dash_pattern: tuple[float, ...] | None = None
    z: int = 0


@dataclass(frozen=True)
class OverlayPolygon:
    points: tuple[QPointF, ...]
    stroke_color: tuple[int, int, int, int] | None = None
    fill_color: tuple[int, int, int, int] | None = None
    stroke_width: float = 2.0
    z: int = 0


@dataclass(frozen=True)
class OverlayPoints:
    points: tuple[QPointF, ...]
    radius: float
    color: tuple[int, int, int, int]
    z: int = 0


@dataclass(frozen=True)
class OverlayGradient:
    center: QPointF
    radius: float
    color_stops: tuple[tuple[float, tuple[int, int, int, int]], ...]
    z: int = 0


@dataclass(frozen=True)
class OverlayText:
    position: QPointF
    text: str
    color: tuple[int, int, int, int]
    font_size: int = 12
    z: int = 0


OverlayPrimitive = (
    OverlayPolyline
    | OverlayPolygon
    | OverlayPoints
    | OverlayGradient
    | OverlayText
)


ToolHitResult = CanvasHit


@runtime_checkable
class ToolHost(Protocol):
    def screen_to_canvas(self, screen_pos: QPointF) -> QPointF: ...

    def canvas_to_screen(self, canvas_pos: QPointF) -> QPointF: ...

    @property
    def viewport(self) -> ToolViewport: ...

    def get_canvas_data(self) -> QImage | QPixmap | None: ...

    def get_roi_data(self, rect: QRectF) -> QImage | QPixmap | None: ...

    def hit_test(self, canvas_pos: QPointF) -> ToolHitResult | None: ...

    def set_overlay(self, layer_id: str, primitives: list[OverlayPrimitive] | None) -> None: ...

    def clear_overlay(self, layer_id: str) -> None: ...

    def set_cursor(self, cursor: Qt.CursorShape | QCursor) -> None: ...

    def set_status(self, text: str, *, timeout_ms: int = 0) -> None: ...

    def apply_mutation(self, mutation: ToolMutation, *, description: str, merge_id: str | None = None) -> bool: ...

    def begin_mutation_group(self, description: str) -> None: ...

    def end_mutation_group(self) -> None: ...

    def get_tool_preference(self, tool_id: str, key: str, default: Any) -> Any: ...

    def set_tool_preference(self, tool_id: str, key: str, value: Any) -> None: ...


__all__ = [
    "AddShapeMutation",
    "DeleteShapesMutation",
    "OverlayGradient",
    "OverlayPoints",
    "OverlayPolygon",
    "OverlayPolyline",
    "OverlayPrimitive",
    "OverlayText",
    "PaintStrokeMutation",
    "SetAttributeMutation",
    "ToolDefinition",
    "ToolHitResult",
    "ToolHost",
    "ToolKind",
    "ToolMutation",
    "ToolViewport",
    "UpdateVerticesMutation",
]
