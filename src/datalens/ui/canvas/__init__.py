"""
Core canvas widget system (V2).

Provides a reusable image canvas with pluggable layers (raster/vector) and tools.

This package is Qt/UI only. Persistence, background work, and project lifecycle are handled
by services/plugins and should feed results back to the canvas as ready-to-draw frames.

See planning doc: `datalens/src/review_and_plan/plugins/canvas_system.md`.
"""

from .canvas_widget import ImageCanvas
from .viewport import ViewportTransform
from .layers.base import CanvasHit, CanvasLayer, CanvasLayerId, HitKind
from .layers.raster_layer import RasterLayer
from .layers.vector_layer import VectorLayer, VectorShape, VectorStyle
from .tools.base import CanvasTool, ToolResult
from .tools.tool_manager import ToolManager

__all__ = [
    "CanvasHit",
    "CanvasLayer",
    "CanvasLayerId",
    "CanvasTool",
    "HitKind",
    "ImageCanvas",
    "RasterLayer",
    "VectorLayer",
    "VectorShape",
    "VectorStyle",
    "ToolManager",
    "ToolResult",
    "ViewportTransform",
]
