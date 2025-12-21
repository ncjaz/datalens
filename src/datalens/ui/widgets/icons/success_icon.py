from __future__ import annotations

"""
Success/Confirmation icon glyph with checkmark.

Returns a theme-aware ``QIcon`` rendered via QPainter (no external assets).
Used to indicate successful operations, confirmations, or positive states.
"""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPen, QPixmap

from datalens.ui.theme.app_theme import AppTheme


def success_icon(theme: AppTheme, *, size: int = 28) -> QIcon:
    """
    Return a themed success icon with a checkmark symbol.

    Features a circular background with "✓" checkmark symbol,
    using the theme's confirm accent color.

    Args:
        theme: The application theme
        size: Icon size in pixels (default 28)

    Returns:
        QIcon with checkmark symbol
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    # Use confirm color from theme
    confirm_color = theme.confirm_color
    confirm_border = theme.confirm_border

    # Calculate dimensions
    center_x = size / 2
    center_y = size / 2
    radius = size * 0.4

    # Draw circular background with layered fills
    # Outer glow
    pen = QPen(theme.qcolor_with_alpha(confirm_border, 0.5), max(1.0, size * 0.05))
    painter.setPen(pen)
    painter.setBrush(theme.qcolor_with_alpha(confirm_color, 0.3))
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
    painter.setBrush(theme.qcolor_with_alpha(confirm_color, 0.6))
    painter.drawEllipse(
        QRectF(
            center_x - inner_radius,
            center_y - inner_radius,
            inner_radius * 2,
            inner_radius * 2,
        )
    )

    # Draw checkmark "✓"
    # The checkmark consists of two strokes:
    # 1. Short downward stroke (bottom-left to corner)
    # 2. Longer upward stroke (corner to top-right)

    checkmark_color = theme.qcolor_with_alpha(theme.text_color, 0.95)

    # Checkmark dimensions
    stroke_width = max(2.0, size * 0.12)

    # Define checkmark path points
    # Start from bottom-left, draw to corner (bottom), then to top-right
    checkmark_scale = size * 0.28

    # Bottom-left point
    p1 = QPointF(center_x - checkmark_scale * 0.5, center_y)
    # Corner point (bottom of checkmark)
    p2 = QPointF(center_x - checkmark_scale * 0.15, center_y + checkmark_scale * 0.35)
    # Top-right point
    p3 = QPointF(center_x + checkmark_scale * 0.6, center_y - checkmark_scale * 0.45)

    # Draw checkmark path with rounded line cap for smooth appearance
    path = QPainterPath()
    path.moveTo(p1)
    path.lineTo(p2)
    path.lineTo(p3)

    pen = QPen(checkmark_color, stroke_width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)

    painter.end()
    return QIcon(pixmap)


__all__ = ["success_icon"]
