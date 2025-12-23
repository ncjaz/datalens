from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, QSize


@dataclass
class ViewportTransform:
    """
    Converts between widget coordinates and image coordinates for pan/zoom.

    Coordinate convention:
    - image space: (0..image_width, 0..image_height)
    - widget space: (0..widget_width, 0..widget_height)

    This class is intentionally small and UI-thread only.
    """

    image_size: QSize = field(default_factory=QSize)
    scale: float = 1.0
    offset_widget: QPointF = field(default_factory=lambda: QPointF(0.0, 0.0))
    _user_adjusted: bool = False

    def set_image_size(self, size: QSize) -> None:
        self.image_size = QSize(size)
        self._user_adjusted = False

    def fit_to_widget(self, widget_size: QSize, *, margin_px: int = 0) -> None:
        """
        Fit the full image into `widget_size`, preserving aspect ratio.
        """
        if self.image_size.isEmpty() or widget_size.isEmpty():
            self.scale = 1.0
            self.offset_widget = QPointF(0.0, 0.0)
            self._user_adjusted = False
            return

        w = max(1, int(widget_size.width()) - 2 * int(margin_px))
        h = max(1, int(widget_size.height()) - 2 * int(margin_px))

        sx = float(w) / float(max(1, int(self.image_size.width())))
        sy = float(h) / float(max(1, int(self.image_size.height())))
        self.scale = max(1e-6, min(sx, sy))

        drawn_w = float(self.image_size.width()) * self.scale
        drawn_h = float(self.image_size.height()) * self.scale
        x0 = float((widget_size.width() - drawn_w) / 2.0)
        y0 = float((widget_size.height() - drawn_h) / 2.0)
        self.offset_widget = QPointF(x0, y0)
        self._user_adjusted = False

    @property
    def user_adjusted(self) -> bool:
        """
        True if the user has panned/zoomed away from fit-to-widget.
        """
        return bool(self._user_adjusted)

    def pan_by(self, delta_widget: QPointF) -> None:
        self.offset_widget = QPointF(
            float(self.offset_widget.x()) + float(delta_widget.x()),
            float(self.offset_widget.y()) + float(delta_widget.y()),
        )
        self._user_adjusted = True

    def zoom_at(self, widget_anchor: QPointF, *, factor: float, min_scale: float = 1e-3, max_scale: float = 200.0) -> None:
        """
        Zoom around a widget-space anchor point (keeps the same image point under the cursor).
        """
        if self.image_size.isEmpty():
            return
        old_scale = float(self.scale) if float(self.scale) != 0.0 else 1.0
        new_scale = max(float(min_scale), min(float(max_scale), old_scale * float(factor)))
        if abs(new_scale - old_scale) <= 1e-12:
            return

        img = self.widget_to_image(widget_anchor)
        self.scale = float(new_scale)
        self.offset_widget = QPointF(
            float(widget_anchor.x()) - float(img.x()) * float(self.scale),
            float(widget_anchor.y()) - float(img.y()) * float(self.scale),
        )
        self._user_adjusted = True

    def clamp_to_widget(self, widget_size: QSize, *, margin_px: int = 0) -> None:
        """
        Keep the image rect reasonably within the widget.

        This avoids the user panning the image completely off-screen.
        """
        if self.image_size.isEmpty() or widget_size.isEmpty():
            return

        rect = self.image_rect_in_widget()
        if rect.isNull():
            return

        # If the image is smaller than the widget, keep it centered.
        if rect.width() <= float(widget_size.width() - 2 * int(margin_px)):
            x0 = float((widget_size.width() - rect.width()) / 2.0)
        else:
            x_min = float(widget_size.width() - rect.width() - int(margin_px))
            x_max = float(int(margin_px))
            x0 = max(x_min, min(x_max, float(rect.x())))

        if rect.height() <= float(widget_size.height() - 2 * int(margin_px)):
            y0 = float((widget_size.height() - rect.height()) / 2.0)
        else:
            y_min = float(widget_size.height() - rect.height() - int(margin_px))
            y_max = float(int(margin_px))
            y0 = max(y_min, min(y_max, float(rect.y())))

        self.offset_widget = QPointF(x0, y0)

    def image_to_widget(self, pt: QPointF) -> QPointF:
        return QPointF(
            float(self.offset_widget.x()) + float(pt.x()) * float(self.scale),
            float(self.offset_widget.y()) + float(pt.y()) * float(self.scale),
        )

    def widget_to_image(self, pt: QPointF) -> QPointF:
        s = float(self.scale) if float(self.scale) != 0.0 else 1.0
        return QPointF(
            (float(pt.x()) - float(self.offset_widget.x())) / s,
            (float(pt.y()) - float(self.offset_widget.y())) / s,
        )

    def image_rect_in_widget(self) -> QRectF:
        if self.image_size.isEmpty():
            return QRectF()
        top_left = self.image_to_widget(QPointF(0.0, 0.0))
        return QRectF(
            float(top_left.x()),
            float(top_left.y()),
            float(self.image_size.width()) * float(self.scale),
            float(self.image_size.height()) * float(self.scale),
        )
