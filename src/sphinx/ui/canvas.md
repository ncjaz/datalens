# Canvas (Image + Overlays)

DataLens V2 provides a reusable **Image Canvas** widget for workspace plugins that need to show an image with multiple overlay layers (vector + raster) and optional interactive tools.

- **Planning/spec**: `datalens/src/review_and_plan/plugins/canvas_system.md`
- **Plugin-facing API**: `datalens/api/canvas.py`
- **Core implementation**: `datalens/ui/canvas/`

## What it is

`ImageCanvas` is a `QWidget` that:

- draws a base image (RGB frame / media)
- draws a stack of overlay layers (raster/vector)
- routes mouse/wheel events to an active tool first, then falls back to layer hit-testing

Heavy computation must run off the UI thread; tools/layers should only swap in **ready-to-draw** `QImage/QPixmap` and request a repaint.

## Minimal example

```python
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage

from datalens.api.canvas import ImageCanvas, RasterLayer, VectorLayer, VectorShape, VectorStyle

canvas = ImageCanvas(parent=some_parent)
canvas.set_base_image(QImage("example.jpg"))

mask = RasterLayer(layer_id="mask", opacity=0.5)
mask.set_image(QImage("mask.png"))
canvas.add_layer(mask, z=10)

vectors = VectorLayer(
    layer_id="vectors",
    shapes=[
        VectorShape(
            shape_id="roi",
            points=(QPointF(120, 80), QPointF(360, 80), QPointF(360, 240), QPointF(120, 240)),
            closed=True,
            style=VectorStyle(stroke_hex="#F9A826", stroke_width_px=2, stroke_alpha=0.95),
        ),
    ],
)
canvas.add_layer(vectors, z=20)
```

## Notes for plugin developers

- Prefer `datalens.api.canvas` imports (stable surface).
- Do not do expensive work in `paintEvent`; precompute overlays (threadpool/loader) and push results to the UI thread.

## Viewport controls (v0)

- `Ctrl+Wheel`: zoom in/out.
- Middle mouse drag: pan.

These are implemented in `ImageCanvas` so plugins get them by default without re-implementing pan/zoom in every tool.

## Testing

The shipped `widget_test` plugin includes a **Canvas** section that exercises:

- base image rendering
- vector overlay drawing
- vertex/edge hit-testing (logged at `debug`)
