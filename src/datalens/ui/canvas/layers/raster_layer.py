from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPainter, QPixmap

from datalens.ui.canvas.layers.base import CanvasHit, CanvasLayer, CanvasLayerId, HitKind
from datalens.ui.canvas.viewport import ViewportTransform


@dataclass
class RasterLayer(CanvasLayer):
    """
    Simple raster overlay layer.

    Draws a QImage/QPixmap mapped into the current viewport.
    """

    layer_id: CanvasLayerId
    opacity: float = 1.0
    _pixmap: QPixmap | None = None

    def set_image(self, image: QImage | QPixmap | None) -> None:
        if image is None:
            self._pixmap = None
            return
        if isinstance(image, QPixmap):
            self._pixmap = image
        else:
            self._pixmap = QPixmap.fromImage(image)

    def draw(self, painter: QPainter, view: ViewportTransform) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        rect = view.image_rect_in_widget()
        if rect.isNull():
            return
        prev = painter.opacity()
        try:
            painter.setOpacity(max(0.0, min(1.0, float(self.opacity))))
            painter.drawPixmap(rect, self._pixmap, self._pixmap.rect())
        finally:
            painter.setOpacity(prev)

    def hit_test(self, image_pos: QPointF, view: ViewportTransform) -> CanvasHit | None:
        # Raster overlays typically aren't directly hit-tested at v0.
        _ = view
        return None

