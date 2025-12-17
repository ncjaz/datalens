from __future__ import annotations

"""
Annotation visibility toggle glyph (ported from V1 for V2).

Returns a theme-aware ``QIcon`` rendered via QPainter (no external assets).
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from datalens.ui.theme.app_theme import AppTheme


def annotation_toggle_icon(theme: AppTheme, *, active: bool, enabled: bool = True, size: int = 48) -> QIcon:
    pixmap = QPixmap(int(size), int(size))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    base_hex = theme.primary_color if enabled else theme.secondary_color
    base_color = theme.qcolor_with_alpha(base_hex, 0.35 if active else 0.22)
    painter.setPen(Qt.NoPen)
    painter.setBrush(base_color)
    painter.drawRoundedRect(12, 16, size - 24, size - 26, 10, 10)

    outline_hex = theme.tertiary_color if active else theme.primary_color
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(outline_hex), 3, Qt.SolidLine, Qt.RoundCap))
    painter.drawRoundedRect(14, 14, size - 28, size - 26, 10, 10)

    inner_color = theme.qcolor_with_alpha(outline_hex, 0.6)
    painter.setPen(QPen(inner_color, 2, Qt.SolidLine, Qt.RoundCap))
    inner_rect = QRectF(18, 20, size - 32, size - 30)
    painter.drawRoundedRect(inner_rect, 10, 10)

    if active:
        dotted_pen = QPen(theme.qcolor_with_alpha(outline_hex, 0.75), 2, Qt.CustomDashLine, Qt.RoundCap)
        dotted_pen.setDashPattern([6, 4])
        painter.setPen(dotted_pen)
        dotted_rect = inner_rect.adjusted(4, 4, -4, -4)
        painter.drawRoundedRect(dotted_rect, 8, 8)

    painter.end()
    return QIcon(pixmap)


__all__ = ["annotation_toggle_icon"]

