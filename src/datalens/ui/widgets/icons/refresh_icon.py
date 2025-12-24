from __future__ import annotations

"""
Refresh glyph (theme-aware) for DataLens V2.

This icon is designed to match the V2 iconography guidelines:
- drawn via QPainter (no external assets)
- colors derived from AppTheme
- rounded strokes, subtle layered fills

The icon supports animation by accepting a `rotation_deg` parameter.
Use `datalens.ui.widgets.icons.animated.refresh.RefreshAnimator` for a
ready-made "spin" animation on buttons.
"""

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap, QPolygonF

from datalens.ui.theme.app_theme import AppTheme


def refresh_icon(theme: AppTheme, *, size: int = 18, rotation_deg: float = 0.0) -> QIcon:
    """
    Return a themed refresh icon (two circular arrows).

    Args:
        theme: Current AppTheme.
        size: Pixmap size in pixels (icons are typically 18-28px; design at 56px).
        rotation_deg: Additional rotation in degrees (for animation).
    """
    size_i = max(1, int(size))
    pixmap = QPixmap(size_i, size_i)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    center = size_i / 2.0
    stroke_w = max(2.0, size_i * 0.12)
    outer_r = center - stroke_w * 0.85
    arrow_len = max(3.0, size_i * 0.26)
    arrow_w = max(2.0, size_i * 0.22)

    # Apply overall rotation for animation (rotate around center).
    # All subsequent drawing happens in rotated coordinate space.
    painter.translate(center, center)
    painter.rotate(float(rotation_deg))

    # Subtle background disk for depth (keeps the glyph readable on mixed surfaces).
    # Draw centered at origin (since we're already translated to center).
    painter.setPen(Qt.NoPen)
    painter.setBrush(theme.qcolor_with_alpha(theme.primary_color, 0.12))
    painter.drawEllipse(
        -outer_r,
        -outer_r,
        outer_r * 2,
        outer_r * 2,
    )

    pen = QPen(theme.qcolor_with_alpha(theme.primary_color, 0.78), stroke_w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    # Arc rectangle centered at origin
    arc_size = size_i - stroke_w * 1.7
    rect = (
        -arc_size / 2.0,
        -arc_size / 2.0,
        arc_size,
        arc_size,
    )

    def draw_arrowhead(*, angle_deg: float, direction: int) -> None:
        """
        Draw a small arrowhead at the end of an arc.

        `angle_deg` uses Qt's arc angle convention: 0° at 3 o'clock, CCW positive.
        `direction`: +1 for CCW, -1 for CW.
        """
        painter.save()
        # We're already at center, just rotate to angle
        painter.rotate(float(angle_deg))
        painter.translate(float(outer_r), 0.0)
        # Align arrow along the tangent direction.
        painter.rotate(float(90.0 * direction))

        notch = max(1.0, arrow_len * 0.45)
        poly = QPolygonF(
            [
                # Tip at origin.
                QPointF(0.0, 0.0),
                QPointF(-arrow_len, -arrow_w / 2.0),
                QPointF(-notch, 0.0),
                QPointF(-arrow_len, arrow_w / 2.0),
            ]
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.qcolor_with_alpha(theme.primary_color, 0.95))
        painter.drawPolygon(poly)
        painter.restore()

    # Two arcs offset to suggest a refresh loop.
    # Arc angles in Qt are *16 and span CCW; keep gaps for arrowheads.
    arc1_start = 45.0
    arc1_span = 140.0
    arc2_start = 225.0
    arc2_span = 140.0

    painter.drawArc(*rect, int(arc1_start * 16), int(arc1_span * 16))
    painter.drawArc(*rect, int(arc2_start * 16), int(arc2_span * 16))

    # Arrowheads at the arc ends.
    draw_arrowhead(angle_deg=arc1_start + arc1_span, direction=+1)
    draw_arrowhead(angle_deg=arc2_start + arc2_span, direction=+1)

    # Small highlight dot for "motion"/energy (centered at origin).
    painter.setPen(Qt.NoPen)
    painter.setBrush(theme.qcolor_with_alpha(theme.tertiary_color, 0.9))
    dot_r = max(1.0, size_i * 0.06)
    painter.drawEllipse(
        -dot_r,
        -dot_r,
        dot_r * 2,
        dot_r * 2,
    )

    painter.end()
    return QIcon(pixmap)


__all__ = ["refresh_icon"]
