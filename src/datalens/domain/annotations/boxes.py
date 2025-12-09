from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .core import AnnotationBase, AnnotationId, AnnotationType
from ..media import MediaId


@dataclass(frozen=True)
class NormalizedBox:
    """
    Normalized bounding box coordinates in [0, 1].

    Conversion to/from pixel space is handled by infrastructure or UI.
    """

    cx: float  # center x in [0, 1]
    cy: float  # center y in [0, 1]
    width: float  # width in [0, 1]
    height: float  # height in [0, 1]

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.cx, self.cy, self.width, self.height


@dataclass(frozen=True)
class BoxAnnotation(AnnotationBase):
    """
    Axis-aligned bounding box annotation.

    `score` is optional; used for suggested detections and evaluation.
    """

    box: NormalizedBox
    score: Optional[float] = None

    def __init__(
        self,
        id: AnnotationId,
        media_id: MediaId,
        tag: str,
        box: NormalizedBox,
        score: Optional[float] = None,
    ) -> None:
        super().__init__(
            id=id,
            media_id=media_id,
            tag=tag,
            annotation_type=AnnotationType.BOX,
        )
        object.__setattr__(self, "box", box)
        object.__setattr__(self, "score", score)
