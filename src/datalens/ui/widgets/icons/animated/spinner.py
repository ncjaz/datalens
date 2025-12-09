from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QSizePolicy

from datalens.ui.widgets.core.themed_widget import ThemedWidget
from datalens.ui.theme.app_theme import AppTheme



class DualRingSpinner(ThemedWidget):
    """
    Dual-ring loading spinner used as the core "app is busy" indicator.

    - Subclasses ThemedWidget so it:
        * Has access to self.theme (AppTheme)
        * Repaints automatically on theme changes via apply_theme()
    - Uses theme primary/tertiary colours for the rings, with secondary as
      a subtle background track.
    - Animation is timer-driven; speeds are in degrees per second.

    Public API:
        start()                     -> begin spinning
        stop()                      -> stop spinning
        set_speed(outer, inner)     -> set ring speeds (deg/sec)
    """

    def __init__(self, theme: AppTheme, parent=None):
        super().__init__(theme, parent)

        # Rotation angles
        self._outer_angle = 0.0
        self._inner_angle = 0.0

        # Speeds (degrees per second)
        self._outer_speed = 180.0      # clockwise
        self._inner_speed = -360.0     # counter-clockwise

        # Timer for animation (~60 FPS)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_timeout)

        # Cached QColor instances (updated in apply_theme)
        self._outer_color = QColor("#4DA3FF")
        self._inner_color = QColor("#8B9BCC")
        self._track_color = QColor("#20232A")

        # Suggest a compact minimum size
        self.setMinimumSize(40, 40)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Apply theme initially
        self.apply_theme(self.theme)

    # ------------------------------------------------------------------ #
    # Theme Handling
    # ------------------------------------------------------------------ #

    def apply_theme(self, theme: AppTheme) -> None:  # override
        super().apply_theme(theme)

        # Resolve spinner colors from theme
        self._outer_color = QColor(theme.primary_color)
        self._inner_color = QColor(theme.tertiary_color)

        # Track/background uses a softened secondary
        secondary = QColor(theme.secondary_color)
        secondary.setAlphaF(0.45)
        self._track_color = secondary

        self.update()

    # ------------------------------------------------------------------ #
    # API
    # ------------------------------------------------------------------ #

    def start(self):
        """Begin spinning."""
        if not self._timer.isActive():
            self._timer.start()

    def stop(self):
        """Stop spinning and reset angles."""
        if self._timer.isActive():
            self._timer.stop()
        self._outer_angle = 0
        self._inner_angle = 0
        self.update()

    def set_speed(self, outer: float | None = None, inner: float | None = None):
        """Update outer/inner ring rotational speeds."""
        if outer is not None:
            self._outer_speed = float(outer)
        if inner is not None:
            self._inner_speed = float(inner)

    # ------------------------------------------------------------------ #
    # Animation Tick
    # ------------------------------------------------------------------ #

    def _on_timeout(self):
        dt = self._timer.interval() / 1000.0

        self._outer_angle = (self._outer_angle + self._outer_speed * dt) % 360
        self._inner_angle = (self._inner_angle + self._inner_speed * dt) % 360

        self.update()

    # ------------------------------------------------------------------ #
    # Painting
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        size = min(self.width(), self.height())
        if size < 6:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)

        radius = size / 2 - 2

        outer_radius = radius
        inner_radius = radius * 0.65

        outer_width = max(2, radius * 0.12)
        inner_width = max(2, radius * 0.08)
        track_width = max(1, radius * 0.06)

        # Track circle
        painter.save()
        painter.setPen(QPen(self._track_color, track_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        track_rect = QRectF(-outer_radius, -outer_radius, outer_radius * 2, outer_radius * 2)
        painter.drawEllipse(track_rect)
        painter.restore()

        # Outer arc (240°)
        painter.save()
        painter.setPen(QPen(self._outer_color, outer_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        start_angle = int(self._outer_angle * 16)
        span_angle = int(-240 * 16)  # clockwise
        painter.drawArc(track_rect, start_angle, span_angle)
        painter.restore()

        # Inner arc (180°)
        painter.save()
        painter.setPen(QPen(self._inner_color, inner_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        inner_rect = QRectF(-inner_radius, -inner_radius, inner_radius * 2, inner_radius * 2)
        start_angle = int(self._inner_angle * 16)
        span_angle = int(180 * 16)
        painter.drawArc(inner_rect, start_angle, span_angle)
        painter.restore()

        painter.end()