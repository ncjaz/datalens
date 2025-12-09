from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .core import AnnotationBase, AnnotationId, AnnotationType
from ..media import MediaId


@dataclass(frozen=True)
class NormalizedPoint:
    x: float
    y: float

    def as_tuple(self) -> tuple[float, float]:
        return self.x, self.y


@dataclass(frozen=True)
class PolygonAnnotation(AnnotationBase):
    """
    Polygon annotation with normalized points in image coordinates [0, 1].
    """

    points: tuple[NormalizedPoint, ...]

    def __init__(
        self,
        id: AnnotationId,
        media_id: MediaId,
        tag: str,
        points: Sequence[NormalizedPoint],
    ) -> None:
        super().__init__(
            id=id,
            media_id=media_id,
            tag=tag,
            annotation_type=AnnotationType.POLYGON,
        )
        object.__setattr__(self, "points", tuple(points))
