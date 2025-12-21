from __future__ import annotations

"""
Eye glyph (ported from V1 for V2).

Returns a theme-aware ``QIcon`` rendered via QPainter (no external assets).
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap

from datalens.ui.theme.app_theme import AppTheme


def eye_icon(theme: AppTheme, *, size: int = 18, open: bool = True) -> QIcon:
    pixmap = QPixmap(int(size), int(size))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    center_x = size / 2.0
    center_y = size / 2.0
    center = QPointF(center_x, center_y)
    text_hex = theme.text_color

    if open:
        eye_width = size * 0.65
        eye_height = size * 0.45
        eye_rect = QRectF(center_x - eye_width / 2, center_y - eye_height / 2, eye_width, eye_height)

        pen_width = max(2.0, size * 0.08)
        pen = QPen(theme.qcolor_with_alpha(text_hex, 0.9), pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(eye_rect)

        pupil_radius = size * 0.12
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.qcolor_with_alpha(text_hex, 0.95))
        painter.drawEllipse(center, pupil_radius, pupil_radius)
    else:
        eye_width = size * 0.65
        eye_y = center_y

        pen_width = max(2.5, size * 0.10)
        pen = QPen(theme.qcolor_with_alpha(text_hex, 0.85), pen_width, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        start_x = center_x - eye_width / 2
        end_x = center_x + eye_width / 2
        painter.drawLine(QPointF(start_x, eye_y), QPointF(end_x, eye_y))

        slash_pen = QPen(theme.qcolor_with_alpha(text_hex, 0.7), max(2.0, size * 0.08), Qt.SolidLine, Qt.RoundCap)
        painter.setPen(slash_pen)
        painter.drawLine(
            QPointF(center_x - size * 0.25, center_y + size * 0.18),
            QPointF(center_x + size * 0.25, center_y - size * 0.18),
        )

    painter.end()
    return QIcon(pixmap)


__all__ = ["eye_icon"]

