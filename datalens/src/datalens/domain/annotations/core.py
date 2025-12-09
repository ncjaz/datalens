from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import NewType, Sequence

from ..media import MediaId

AnnotationId = NewType("AnnotationId", int)


class AnnotationType(Enum):
    BOX = auto()
    POLYGON = auto()
    SUGGESTED = auto()


@dataclass(frozen=True)
class AnnotationBase:
    """
    Base class for all annotations. Concrete shapes extend this.

    - `annotation_type` distinguishes shape/behaviour.
    - `tag` is the semantic class (e.g. 'person', 'dog').
    """

    id: AnnotationId
    media_id: MediaId
    tag: str
    annotation_type: AnnotationType


@dataclass(frozen=True)
class AnnotationSet:
    """
    All annotations associated with a single media item.

    This is the main payload returned by annotation services. It is
    immutable and safe to share across threads.
    """

    media_id: MediaId
    annotations: tuple[AnnotationBase, ...]

    def boxes(self) -> tuple[AnnotationBase, ...]:
        from .boxes import BoxAnnotation

        return tuple(a for a in self.annotations if isinstance(a, BoxAnnotation))

    def polygons(self) -> tuple[AnnotationBase, ...]:
        from .polygons import PolygonAnnotation

        return tuple(a for a in self.annotations if isinstance(a, PolygonAnnotation))

    def suggested(self) -> tuple[AnnotationBase, ...]:
        from .suggested import SuggestedAnnotation

        return tuple(a for a in self.annotations if isinstance(a, SuggestedAnnotation))

    def tags(self) -> set[str]:
        return {a.tag for a in self.annotations}

    @classmethod
    def empty(cls, media_id: MediaId) -> "AnnotationSet":
        return cls(media_id=media_id, annotations=())
