from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from .boxes import BoxAnnotation, NormalizedBox
from .core import AnnotationId, AnnotationType
from ..media import MediaId


class SuggestionSource(Enum):
    """
    Indicates where a suggestion came from.

    - MODEL: a detection/segmentation model (YOLO, RT-DETR, SAM, etc.)
    - PREVIOUS_FRAME: propagated from previous frame
    - IMPORT: imported from an external dataset
    """

    MODEL = auto()
    PREVIOUS_FRAME = auto()
    IMPORT = auto()


@dataclass(frozen=True)
class SuggestedAnnotation(BoxAnnotation):
    """
    Suggested bounding box (usually from a model or auto-track).

    - `model_id` is optional; used when the source is a specific model.
    - `source` indicates whether this is from an ML model, temporal
      propagation, or an import.
    """

    source: SuggestionSource
    model_variant_id: Optional[str] = None

    def __init__(
        self,
        id: AnnotationId,
        media_id: MediaId,
        tag: str,
        box: NormalizedBox,
        score: Optional[float],
        source: SuggestionSource,
        model_variant_id: Optional[str] = None,
    ) -> None:
        super().__init__(id=id, media_id=media_id, tag=tag, box=box, score=score)
        object.__setattr__(self, "annotation_type", AnnotationType.SUGGESTED)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "model_variant_id", model_variant_id)
