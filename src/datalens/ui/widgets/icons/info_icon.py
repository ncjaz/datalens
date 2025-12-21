from __future__ import annotations

"""
Info/Information icon glyph with 'i' mark.

Returns a theme-aware ``QIcon`` rendered via QPainter (no external assets).
Used to indicate informational messages or help content.
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap

from datalens.ui.theme.app_theme import AppTheme


def info_icon(theme: AppTheme, *, size: int = 28) -> QIcon:
    """
    Return a themed info icon with an 'i' mark symbol.

    Features a circular background with "i" symbol,
    using the theme's primary color.

    Args:
        theme: The application theme
        size: Icon size in pixels (default 28)

    Returns:
        QIcon with info 'i' symbol
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    # Use primary color from theme for info
    primary_color = theme.primary_color
    primary_border = theme.primary_border

    # Calculate dimensions
    center_x = size / 2
    center_y = size / 2
    radius = size * 0.4

    # Draw circular background with layered fills
    # Outer glow
    pen = QPen(theme.qcolor_with_alpha(primary_border, 0.5), max(1.0, size * 0.05))
    painter.setPen(pen)
    painter.setBrush(theme.qcolor_with_alpha(primary_color, 0.3))
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
    painter.setBrush(theme.qcolor_with_alpha(primary_color, 0.6))
    painter.drawEllipse(
        QRectF(
            center_x - inner_radius,
            center_y - inner_radius,
            inner_radius * 2,
            inner_radius * 2,
        )
    )

    # Draw 'i' symbol
    # The 'i' consists of:
    # 1. A vertical bar (stem of the i)
    # 2. A dot (top of the i)

    i_color = theme.qcolor_with_alpha(theme.text_color, 0.95)
    painter.setPen(Qt.NoPen)
    painter.setBrush(i_color)

    # Vertical bar of the 'i'
    bar_width = size * 0.12
    bar_height = size * 0.35
    bar_x = center_x - (bar_width / 2)
    bar_y = center_y - (size * 0.05)  # Position slightly below center

    # Use rounded rectangle for the bar
    bar_corner_radius = bar_width / 2
    painter.drawRoundedRect(
        QRectF(bar_x, bar_y, bar_width, bar_height),
        bar_corner_radius,
        bar_corner_radius,
    )

    # Dot of the 'i'
    dot_radius = size * 0.08
    dot_y = bar_y - (size * 0.18)  # Position above bar with gap

    painter.drawEllipse(
        QRectF(
            center_x - dot_radius,
            dot_y,
            dot_radius * 2,
            dot_radius * 2,
        )
    )

    painter.end()
    return QIcon(pixmap)


__all__ = ["info_icon"]
