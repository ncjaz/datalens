from __future__ import annotations

"""
Reset glyph (theme-aware) for DataLens V2.

This icon is designed to match the V2 iconography guidelines:
- drawn via QPainter (no external assets)
- colors derived from AppTheme
- rounded strokes, subtle layered fills

The reset icon depicts a circular arrow (undo/reset style) with a clear
arrowhead, suggesting "return to initial state" or "restore defaults."
"""

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap, QPolygonF

from datalens.ui.theme.app_theme import AppTheme


def reset_icon(theme: AppTheme, *, size: int = 18) -> QIcon:
    """
    Return a themed reset icon (circular arrow).

    Args:
        theme: Current AppTheme.
        size: Pixmap size in pixels (icons are typically 18-28px; design at 56px).

    Returns:
        QIcon with normal and disabled states.

    Design:
    - Circular arrow (counterclockwise) with clear arrowhead
    - Gap at bottom right to clearly show direction
    - Traditional reset/undo icon style
    - Subtle background disk for depth
    """
    size_i = max(1, int(size))

    # Create normal state pixmap
    pixmap_normal = _create_reset_pixmap(theme, size_i, enabled=True)

    # Create disabled state pixmap
    pixmap_disabled = _create_reset_pixmap(theme, size_i, enabled=False)

    icon = QIcon()
    icon.addPixmap(pixmap_normal, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(pixmap_disabled, QIcon.Mode.Disabled, QIcon.State.Off)

    return icon


def _create_reset_pixmap(theme: AppTheme, size: int, *, enabled: bool) -> QPixmap:
    """Create a single pixmap for reset icon (normal or disabled state)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    center = size / 2.0
    stroke_w = max(2.0, size * 0.13)
    radius = center - stroke_w * 1.2

    # Arrow dimensions - make it clear and prominent
    arrow_len = max(4.0, size * 0.32)
    arrow_width = max(3.0, size * 0.26)

    painter.translate(center, center)

    # Opacity adjustments for disabled state
    bg_alpha = 0.08 if enabled else 0.04
    stroke_alpha = 0.85 if enabled else 0.35
    fill_alpha = 0.95 if enabled else 0.40

    # Subtle background disk for depth
    painter.setPen(Qt.NoPen)
    painter.setBrush(theme.qcolor_with_alpha(theme.primary_color, bg_alpha))
    painter.drawEllipse(-radius * 1.1, -radius * 1.1, radius * 2.2, radius * 2.2)

    # Draw circular arc (counterclockwise from top-left around to bottom-left)
    # This creates a clear "loop back" motion
    pen = QPen(theme.qcolor_with_alpha(theme.primary_color, stroke_alpha), stroke_w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    # Arc rect
    arc_rect = (-radius, -radius, radius * 2, radius * 2)

    # Arc spans from 135° (top-left) counterclockwise 270° to end at 45° (bottom-right gap)
    # Qt: 0° at 3 o'clock, positive angles are CCW
    arc_start_angle = 135.0  # Top-left
    arc_span_angle = 270.0   # CCW sweep (leaves gap at bottom-right)

    painter.drawArc(*arc_rect, int(arc_start_angle * 16), int(arc_span_angle * 16))

    # Draw arrowhead at arc start (top-left), pointing CCW
    # The arrow shows the direction of the "reset" motion
    arrow_pos_angle_deg = 135.0  # Match arc start
    arrow_pos_angle_rad = math.radians(arrow_pos_angle_deg)

    # Position on the circle
    arrow_x = radius * math.cos(arrow_pos_angle_rad)
    arrow_y = -radius * math.sin(arrow_pos_angle_rad)

    painter.save()
    painter.translate(arrow_x, arrow_y)
    # Point the arrow tangent to the circle (CCW direction)
    # Tangent at 135° points toward 135° + 90° = 225° (down-left)
    painter.rotate(arrow_pos_angle_deg + 90.0)

    # Draw filled arrowhead
    arrow_notch = arrow_len * 0.35
    arrow_poly = QPolygonF([
        QPointF(0.0, 0.0),  # Tip
        QPointF(-arrow_len, -arrow_width / 2.0),  # Top wing
        QPointF(-arrow_notch, 0.0),  # Notch
        QPointF(-arrow_len, arrow_width / 2.0),  # Bottom wing
    ])

    painter.setPen(Qt.NoPen)
    painter.setBrush(theme.qcolor_with_alpha(theme.primary_color, fill_alpha))
    painter.drawPolygon(arrow_poly)
    painter.restore()

    painter.end()
    return pixmap


__all__ = ["reset_icon"]
