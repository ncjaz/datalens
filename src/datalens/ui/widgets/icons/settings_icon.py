from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

from datalens.ui.theme.app_theme import AppTheme


def settings_icon(theme: AppTheme, *, size: int = 28) -> QIcon:
    """
    Return a themed gear icon consistent with the V1 welcome/profile styling.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    center = size / 2.0
    outer_radius = center - 2.0
    inner_radius = outer_radius * 0.55
    hub_radius = inner_radius * 0.38

    painter.setPen(Qt.NoPen)
    painter.setBrush(theme.qcolor_with_alpha(theme.primary_color, 0.28))
    painter.drawEllipse(
        center - outer_radius,
        center - outer_radius,
        outer_radius * 2,
        outer_radius * 2,
    )

    tooth_color = theme.qcolor_with_alpha(theme.tertiary_color, 0.9)
    painter.setBrush(tooth_color)
    tooth_width = size * 0.22
    tooth_height = size * 0.26
    for angle in range(0, 360, 60):
        painter.save()
        painter.translate(center, center)
        painter.rotate(float(angle))
        painter.drawRoundedRect(
            -tooth_width / 2.0,
            -outer_radius,
            tooth_width,
            tooth_height,
            2.2,
            2.2,
        )
        painter.restore()

    painter.setBrush(theme.qcolor_with_alpha(theme.primary_color, 0.65))
    painter.drawEllipse(
        center - inner_radius,
        center - inner_radius,
        inner_radius * 2,
        inner_radius * 2,
    )

    painter.setBrush(theme.qcolor_with_alpha(theme.secondary_color, 0.9))
    painter.drawEllipse(
        center - hub_radius,
        center - hub_radius,
        hub_radius * 2,
        hub_radius * 2,
    )

    painter.end()
    return QIcon(pixmap)

