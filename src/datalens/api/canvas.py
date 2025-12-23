"""
Plugin-facing Canvas API (V2).

This module is the stable import surface for plugins that want to use the core
ImageCanvas widget and standard layer/tool contracts.

Plugins should prefer importing from `datalens.api.canvas` rather than deep
internal module paths under `datalens.ui.canvas.*`.
"""

from datalens.ui.canvas import (  # noqa: F401
    CanvasHit,
    CanvasLayer,
    CanvasLayerId,
    CanvasTool,
    HitKind,
    ImageCanvas,
    RasterLayer,
    ToolManager,
    ToolResult,
    VectorLayer,
    VectorShape,
    VectorStyle,
    ViewportTransform,
)

__all__ = [
    "CanvasHit",
    "CanvasLayer",
    "CanvasLayerId",
    "CanvasTool",
    "HitKind",
    "ImageCanvas",
    "RasterLayer",
    "ToolManager",
    "ToolResult",
    "VectorLayer",
    "VectorShape",
    "VectorStyle",
    "ViewportTransform",
]
