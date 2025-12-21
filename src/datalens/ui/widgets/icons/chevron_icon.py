from __future__ import annotations

"""
Chevron glyph (ported from V1 for V2).

Returns a theme-aware ``QIcon`` rendered via QPainter (no external assets).
"""

from typing import Literal

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPen, QPixmap

from datalens.ui.theme.app_theme import AppTheme


BarPosition = Literal["start", "end"]


def chevron_icon(
    theme: AppTheme,
    *,
    direction: str = "up",
    size: int = 14,
    bar: BarPosition | None = None,
) -> QIcon:
    target_size = max(10, int(size))
    pixmap = QPixmap(target_size, target_size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    stroke_w = max(1.8, target_size * 0.18)
    pen = QPen(theme.qcolor_with_alpha(theme.text_color, 0.9), stroke_w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    inset = target_size * 0.28
    direction_l = direction.lower()
    if direction_l == "down":
        points = (
            QPointF(inset, inset),
            QPointF(target_size / 2, target_size - inset),
            QPointF(target_size - inset, inset),
        )
    elif direction_l == "left":
        points = (
            QPointF(target_size - inset, inset),
            QPointF(inset, target_size / 2),
            QPointF(target_size - inset, target_size - inset),
        )
    elif direction_l == "right":
        points = (
            QPointF(inset, inset),
            QPointF(target_size - inset, target_size / 2),
            QPointF(inset, target_size - inset),
        )
    else:  # up
        points = (
            QPointF(inset, target_size - inset),
            QPointF(target_size / 2, inset),
            QPointF(target_size - inset, target_size - inset),
        )

    path = QPainterPath()
    path.moveTo(points[0])
    path.lineTo(points[1])
    path.lineTo(points[2])
    painter.drawPath(path)

    if bar is not None:
        bar_w = max(2.0, stroke_w * 0.9)
        bar_pen = QPen(theme.qcolor_with_alpha(theme.text_color, 0.9), bar_w, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(bar_pen)

        bar_len = target_size * 0.58
        if direction_l in ("left", "right"):
            x = inset if bar == "start" else target_size - inset
            y1 = (target_size - bar_len) / 2
            y2 = y1 + bar_len
            painter.drawLine(QPointF(x, y1), QPointF(x, y2))
        else:
            y = inset if bar == "start" else target_size - inset
            x1 = (target_size - bar_len) / 2
            x2 = x1 + bar_len
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))

    painter.end()
    return QIcon(pixmap)


__all__ = ["chevron_icon"]
