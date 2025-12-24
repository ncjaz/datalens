from __future__ import annotations

"""
AUTO mode glyph (similar to DSLR camera mode indicators).

Returns a theme-aware ``QIcon`` rendered via QPainter (no external assets).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPen, QPixmap

from datalens.ui.theme.app_theme import AppTheme


def auto_icon(theme: AppTheme, *, size: int = 28, background_color: str | None = None) -> QIcon:
    """
    Return a themed AUTO icon similar to DSLR camera mode indicators.

    Features a rounded rectangle background with "AUTO" text, mimicking
    the style of camera mode displays.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    # Rounded rectangle background with layered fills
    margin = size * 0.1
    rect_width = size - (margin * 2)
    rect_height = size - (margin * 2)
    corner_radius = size * 0.15

    bg = str(background_color or theme.primary_color)

    # Outer glow/border
    pen = QPen(theme.qcolor_with_alpha(bg, 0.4), max(1.0, size * 0.04))
    painter.setPen(pen)
    painter.setBrush(theme.qcolor_with_alpha(bg, 0.7))
    painter.drawRoundedRect(
        margin,
        margin,
        rect_width,
        rect_height,
        corner_radius,
        corner_radius,
    )

    # Inner surface
    inner_margin = margin + size * 0.06
    inner_width = size - (inner_margin * 2)
    inner_height = size - (inner_margin * 2)
    inner_corner = corner_radius * 0.8

    painter.setPen(Qt.NoPen)
    painter.setBrush(theme.qcolor_with_alpha(bg, 0.25))
    painter.drawRoundedRect(
        inner_margin,
        inner_margin,
        inner_width,
        inner_height,
        inner_corner,
        inner_corner,
    )

    # "AUTO" text
    font = QFont("Arial", max(6, int(size * 0.28)), QFont.Bold)
    painter.setFont(font)
    painter.setPen(theme.qcolor_with_alpha(theme.text_color, 0.95))

    text_rect = pixmap.rect()
    painter.drawText(text_rect, Qt.AlignCenter, "AUTO")

    painter.end()
    return QIcon(pixmap)


__all__ = ["auto_icon"]
