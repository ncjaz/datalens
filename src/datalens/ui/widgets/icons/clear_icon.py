from __future__ import annotations

"""
Clear glyph (theme-aware) for DataLens V2.

This icon is designed to match the V2 iconography guidelines:
- drawn via QPainter (no external assets)
- colors derived from AppTheme
- rounded strokes, subtle layered fills

The clear icon depicts a small brush/broom, suggesting "clear/reset/remove".
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QIcon, QPainter, QPainterPath, QPen, QPixmap

from datalens.ui.theme.app_theme import AppTheme


def clear_icon(theme: AppTheme, *, size: int = 18, mirror: bool = False) -> QIcon:
    """
    Return a themed clear icon (brush/broom).

    Args:
        theme: Current AppTheme.
        size: Pixmap size in pixels (icons are typically 18-28px; design at 56px).
        mirror: When True, horizontally mirrors the glyph (useful to match UI directionality).

    Returns:
        QIcon with normal and disabled states.
    """
    size_i = max(1, int(size))
    pixmap_normal = _maybe_mirror(_create_clear_pixmap(theme, size_i, enabled=True), mirror=mirror)
    pixmap_disabled = _maybe_mirror(_create_clear_pixmap(theme, size_i, enabled=False), mirror=mirror)

    icon = QIcon()
    icon.addPixmap(pixmap_normal, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(pixmap_disabled, QIcon.Mode.Disabled, QIcon.State.Off)
    return icon


def _maybe_mirror(pixmap: QPixmap, *, mirror: bool) -> QPixmap:
    if not mirror:
        return pixmap
    return QPixmap.fromImage(pixmap.toImage().mirrored(True, False))


def _create_clear_pixmap(theme: AppTheme, size: int, *, enabled: bool) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    center = size / 2.0
    stroke_w = max(2.0, size * 0.11)
    radius = center - stroke_w * 0.9

    bg_alpha = 0.10 if enabled else 0.04
    stroke_alpha = 0.80 if enabled else 0.35
    fill_alpha = 0.22 if enabled else 0.10
    accent_alpha = 0.85 if enabled else 0.30

    painter.translate(center, center)

    # Subtle background disk for readability on mixed surfaces.
    painter.setPen(Qt.NoPen)
    painter.setBrush(theme.qcolor_with_alpha(theme.primary_color, bg_alpha))
    painter.drawEllipse(-radius, -radius, radius * 2, radius * 2)

    # Brush: draw in a rotated coordinate system.
    # Keep the heavier bristle end visually "down" so it reads as a brush (not a mallet).
    painter.save()
    painter.rotate(-22.0)

    handle_len = size * 0.86
    handle_thick = max(2.6, size * 0.11)
    ferrule_h = max(2.8, size * 0.11)
    ferrule_w = max(4.0, size * 0.24)
    bristle_base_h = max(3.0, size * 0.12)
    bristle_base_w = max(5.0, size * 0.26)
    bristle_fan_h = max(5.0, size * 0.26)
    bristle_fan_w_top = bristle_base_w * 0.85
    bristle_fan_w_bottom = bristle_base_w * 1.35

    # Geometry (in the rotated coordinate system): vertical handle with bristles at the bottom.
    handle_top = -handle_len * 0.55
    handle_bottom = handle_len * 0.12

    # Handle (rounded, slightly tapered).
    painter.setPen(QPen(theme.qcolor_with_alpha(theme.primary_color, stroke_alpha), stroke_w * 0.85))
    painter.setBrush(QBrush(theme.qcolor_with_alpha(theme.primary_color, fill_alpha)))
    painter.drawRoundedRect(
        -handle_thick * 0.50,
        handle_top,
        handle_thick,
        handle_bottom - handle_top,
        handle_thick / 2.0,
        handle_thick / 2.0,
    )

    # Ferrule (metal band between handle and bristles).
    ferrule_top = handle_bottom - ferrule_h * 0.05
    painter.setPen(QPen(theme.qcolor_with_alpha(theme.primary_color, stroke_alpha), max(1.0, stroke_w * 0.55)))
    painter.setBrush(QBrush(theme.qcolor_with_alpha(theme.secondary_color, 0.16 if enabled else 0.08)))
    painter.drawRoundedRect(
        -ferrule_w * 0.50,
        ferrule_top,
        ferrule_w,
        ferrule_h,
        max(1.0, ferrule_h * 0.25),
        max(1.0, ferrule_h * 0.25),
    )

    # Bristle base (narrow strip).
    base_top = ferrule_top + ferrule_h - bristle_base_h * 0.15
    painter.setPen(QPen(theme.qcolor_with_alpha(theme.primary_color, stroke_alpha), max(1.0, stroke_w * 0.55)))
    painter.setBrush(QBrush(theme.qcolor_with_alpha(theme.tertiary_color, 0.22 if enabled else 0.10)))
    painter.drawRoundedRect(
        -bristle_base_w * 0.50,
        base_top,
        bristle_base_w,
        bristle_base_h,
        max(1.0, bristle_base_h * 0.22),
        max(1.0, bristle_base_h * 0.22),
    )

    # Bristle fan (trapezoid) so the "brush end" is clearly larger at the bottom.
    fan_top = base_top + bristle_base_h * 0.75
    fan_bottom = fan_top + bristle_fan_h
    x_top_l = -bristle_fan_w_top * 0.50
    x_top_r = bristle_fan_w_top * 0.50
    x_bot_l = -bristle_fan_w_bottom * 0.50
    x_bot_r = bristle_fan_w_bottom * 0.50

    fan_path = QPainterPath()
    fan_path.moveTo(x_top_l, fan_top)
    fan_path.lineTo(x_top_r, fan_top)
    fan_path.lineTo(x_bot_r, fan_bottom)
    fan_path.lineTo(x_bot_l, fan_bottom)
    fan_path.closeSubpath()

    painter.setPen(QPen(theme.qcolor_with_alpha(theme.primary_color, stroke_alpha), max(1.0, stroke_w * 0.55)))
    painter.setBrush(QBrush(theme.qcolor_with_alpha(theme.primary_color, 0.14 if enabled else 0.07)))
    painter.drawPath(fan_path)

    # Bristle lines (suggest texture). Denser toward the center.
    pen = QPen(theme.qcolor_with_alpha(theme.primary_color, 0.55 if enabled else 0.22), max(1.0, stroke_w * 0.38))
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    for frac in (-0.35, -0.18, 0.0, 0.18, 0.35):
        x = frac * bristle_fan_w_top * 0.72
        painter.drawLine(
            QPointF(x, fan_top + bristle_fan_h * 0.10),
            QPointF(x * 1.15, fan_bottom - bristle_fan_h * 0.10),
        )

    painter.restore()

    # Sweep hint under the bristles (a light accent stroke).
    pen = QPen(theme.qcolor_with_alpha(theme.tertiary_color, accent_alpha), max(1.0, stroke_w * 0.55))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    sweep_r = radius * 0.55
    painter.drawArc(-sweep_r, sweep_r * 0.15, sweep_r * 2, sweep_r * 1.2, int(200 * 16), int(110 * 16))

    painter.end()
    return pixmap


__all__ = ["clear_icon"]
