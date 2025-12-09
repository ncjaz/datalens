from __future__ import annotations

from .core import AnnotationId, AnnotationSet, AnnotationType
from .boxes import BoxAnnotation
from .polygons import PolygonAnnotation
from .suggested import SuggestedAnnotation, SuggestionSource

__all__ = [
    "AnnotationId",
    "AnnotationSet",
    "AnnotationType",
    "BoxAnnotation",
    "PolygonAnnotation",
    "SuggestedAnnotation",
    "SuggestionSource",
]
