from __future__ import annotations

"""
Lock glyph (ported from V1 for V2).

Returns a theme-aware ``QIcon`` rendered via QPainter (no external assets).
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPen, QPixmap

from datalens.ui.theme.app_theme import AppTheme


def lock_icon(theme: AppTheme, *, size: int = 18, open: bool) -> QIcon:
    pixmap = QPixmap(int(size), int(size))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    accent_hex = theme.confirm_color if open else theme.cancel_color
    pen_color = theme.qcolor_with_alpha(accent_hex, 0.9)
    pen_width = max(2.0, size * 0.07)
    pen = QPen(pen_color, pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    padding = size * 0.08
    body_width = size * 0.6
    body_height = size * 0.48
    body_x = (size - body_width) / 2
    body_y = size - body_height - padding
    body_rect = QRectF(body_x, body_y, body_width, body_height)
    body_radius = size * 0.12
    painter.drawRoundedRect(body_rect, body_radius, body_radius)

    shackle_height = size * 0.32
    shackle_width = size * 0.42
    shackle_top = max(padding, body_y - shackle_height + (size * 0.02))

    if open:
        painter.save()
        rotation_angle = -30.0
        rotation_origin_x = body_x + shackle_width * 0.2
        painter.translate(rotation_origin_x, body_y)
        painter.rotate(rotation_angle)
        painter.translate(-rotation_origin_x, -body_y)

    shackle_path = QPainterPath()
    shackle_rect = QRectF((size - shackle_width) / 2, shackle_top, shackle_width, shackle_height)
    shackle_path.arcMoveTo(shackle_rect, 180)
    shackle_path.arcTo(shackle_rect, 180, -180)
    shackle_path.lineTo(shackle_rect.right(), body_y)
    if not open:
        shackle_path.moveTo(shackle_rect.left(), body_y)
        shackle_path.lineTo(shackle_rect.left(), shackle_rect.y() + shackle_rect.height() / 2)
    painter.drawPath(shackle_path)

    if open:
        painter.restore()
        painter.drawLine(
            QPointF(body_rect.left() + body_rect.width() * 0.75, body_y),
            QPointF(body_rect.left() + body_rect.width() * 0.75, shackle_top + shackle_height / 2),
        )

    painter.end()
    return QIcon(pixmap)


__all__ = ["lock_icon"]

