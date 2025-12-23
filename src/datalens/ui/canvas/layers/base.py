from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter

from datalens.ui.canvas.viewport import ViewportTransform


CanvasLayerId = str


class HitKind(str, Enum):
    VERTEX = "vertex"
    EDGE = "edge"
    SHAPE = "shape"
    PIXEL = "pixel"
    HUD = "hud"


@dataclass(frozen=True)
class CanvasHit:
    layer_id: CanvasLayerId
    kind: HitKind
    image_pos: QPointF
    payload: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.payload is None:
            object.__setattr__(self, "payload", {})


@runtime_checkable
class CanvasLayer(Protocol):
    """
    Base protocol for canvas layers.

    Layers are responsible for drawing and optional hit-testing.
    Tools provide behavior; layers are typically passive renderables.
    """

    layer_id: CanvasLayerId

    def draw(self, painter: QPainter, view: ViewportTransform) -> None:
        ...

    def hit_test(self, image_pos: QPointF, view: ViewportTransform) -> CanvasHit | None:  # noqa: D401
        """
        Return a hit result for the given image-space position, or None.
        """
        return None

