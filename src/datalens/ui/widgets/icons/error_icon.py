from __future__ import annotations

"""
Error/Cancel icon glyph with X mark.

Returns a theme-aware ``QIcon`` rendered via QPainter (no external assets).
Used to indicate errors, failures, or cancellation states.
"""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPen, QPixmap

from datalens.ui.theme.app_theme import AppTheme


def error_icon(theme: AppTheme, *, size: int = 28) -> QIcon:
    """
    Return a themed error icon with an X mark symbol.

    Features a circular background with "✕" X mark symbol,
    using the theme's cancel accent color.

    Args:
        theme: The application theme
        size: Icon size in pixels (default 28)

    Returns:
        QIcon with X mark symbol
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    # Use cancel color from theme
    cancel_color = theme.cancel_color
    cancel_border = theme.cancel_border

    # Calculate dimensions
    center_x = size / 2
    center_y = size / 2
    radius = size * 0.4

    # Draw circular background with layered fills
    # Outer glow
    pen = QPen(theme.qcolor_with_alpha(cancel_border, 0.5), max(1.0, size * 0.05))
    painter.setPen(pen)
    painter.setBrush(theme.qcolor_with_alpha(cancel_color, 0.3))
    painter.drawEllipse(
        QRectF(
            center_x - radius,
            center_y - radius,
            radius * 2,
            radius * 2,
        )
    )

    # Inner circle (stronger color)
    inner_radius = radius * 0.85
    painter.setPen(Qt.NoPen)
    painter.setBrush(theme.qcolor_with_alpha(cancel_color, 0.6))
    painter.drawEllipse(
        QRectF(
            center_x - inner_radius,
            center_y - inner_radius,
            inner_radius * 2,
            inner_radius * 2,
        )
    )

    # Draw X mark "✕"
    # The X mark consists of two diagonal strokes:
    # 1. Top-left to bottom-right
    # 2. Top-right to bottom-left

    x_color = theme.qcolor_with_alpha(theme.text_color, 0.95)

    # X mark dimensions
    stroke_width = max(2.0, size * 0.12)
    x_scale = size * 0.25

    # Define X mark path points
    # First stroke: top-left to bottom-right
    tl = QPointF(center_x - x_scale, center_y - x_scale)
    br = QPointF(center_x + x_scale, center_y + x_scale)

    # Second stroke: top-right to bottom-left
    tr = QPointF(center_x + x_scale, center_y - x_scale)
    bl = QPointF(center_x - x_scale, center_y + x_scale)

    # Draw X with rounded line caps for smooth appearance
    pen = QPen(x_color, stroke_width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    # Draw first diagonal stroke
    painter.drawLine(tl, br)
    # Draw second diagonal stroke
    painter.drawLine(tr, bl)

    painter.end()
    return QIcon(pixmap)


__all__ = ["error_icon"]
