from __future__ import annotations

"""
AutoDiscovery glyph (ported from V1 for V2).

Returns a theme-aware ``QIcon`` rendered via QPainter (no external assets).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap

from datalens.ui.theme.app_theme import AppTheme


def autodiscovery_icon(theme: AppTheme, *, size: int = 18, rotation_deg: float = 0.0) -> QIcon:
    pixmap = QPixmap(int(size), int(size))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    center_x = size / 2.0
    center_y = size / 2.0

    painter.translate(center_x, center_y)
    painter.rotate(rotation_deg)
    painter.translate(-center_x, -center_y)

    for i, rel in enumerate((0.48, 0.64, 0.80)):
        radius = size * rel / 2
        inset = (size / 2) - radius
        rect = (inset, inset, radius * 2, radius * 2)
        pen_width = max(1.2, size * 0.06)
        alpha = max(0.05, 0.7 - i * 0.18)
        pen = QPen(theme.qcolor_with_alpha(theme.primary_color, alpha), pen_width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(*rect, int(210 * 16), int(120 * 16))

    painter.setPen(Qt.NoPen)
    painter.setBrush(theme.qcolor_with_alpha(theme.tertiary_color, 0.95))
    dot_r = max(1.0, size * 0.07)
    painter.drawEllipse(center_x - dot_r, center_y - dot_r, dot_r * 2, dot_r * 2)

    painter.end()
    return QIcon(pixmap)


__all__ = ["autodiscovery_icon"]

