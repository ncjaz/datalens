from __future__ import annotations

"""
AUTO mode glyph (similar to DSLR camera mode indicators).

Returns a theme-aware ``QIcon`` rendered via QPainter (no external assets).
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QIcon, QPainter, QPen, QPixmap

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

    bg = str(background_color or theme.primary_color)

    # Text + background "badge": size the background to the text instead of
    # assuming a fixed margin. This avoids the background being too small at
    # small icon sizes.
    label = "AUTO"
    font = QFont()
    font.setStyleHint(QFont.SansSerif)
    font.setBold(True)

    border_w = max(1.0, size * 0.05)
    # Keep a small amount of breathing room so antialiased text/border doesn't
    # get clipped by the pixmap edges, but don't waste too much width (AUTO is
    # wide relative to typical 28px tool icons).
    safe_margin = max(0.6, border_w / 2.0 + 0.25)

    max_badge_w = max(4.0, size - safe_margin * 2.0)
    max_badge_h = max(4.0, size - safe_margin * 2.0)

    # Badge padding must scale down aggressively at small icon sizes; otherwise
    # the label ("AUTO") doesn't have enough horizontal room and gets clipped.
    pad_x = max(0.6, size * 0.03)
    pad_y = max(0.6, size * 0.04)
    target_max_w = max(1.0, max_badge_w - pad_x * 2.0)
    target_max_h = max(1.0, max_badge_h - pad_y * 2.0)

    # Use pixel sizes (not point sizes) so the glyph renders consistently across
    # DPI settings and small icon sizes.
    #
    # Prefer narrowing the text via font "stretch" before shrinking the font
    # height too much. This keeps the AUTO glyph readable at small icon sizes.
    font_px = max(6, int(size * 0.40))
    stretch = 100
    while font_px > 4:
        font.setPixelSize(font_px)
        font.setStretch(stretch)
        metrics = QFontMetricsF(font)
        text_w = metrics.horizontalAdvance(label)
        text_h = metrics.height()
        if text_w <= target_max_w and text_h <= target_max_h:
            break
        if stretch > 55:
            stretch -= 5
            continue
        stretch = 100
        font_px -= 1

    font.setPixelSize(max(4, font_px))
    font.setStretch(max(55, min(100, int(stretch))))
    metrics = QFontMetricsF(font)
    text_w = metrics.horizontalAdvance(label)
    text_h = metrics.height()

    badge_w = min(max_badge_w, text_w + pad_x * 2.0)
    badge_h = min(max_badge_h, text_h + pad_y * 2.0)
    badge_x = max(safe_margin, (size - badge_w) / 2.0)
    badge_y = max(safe_margin, (size - badge_h) / 2.0)
    badge_rect = QRectF(badge_x, badge_y, badge_w, badge_h)
    corner_radius = badge_h * 0.30

    # Outer glow/border
    painter.setPen(QPen(theme.qcolor_with_alpha(bg, 0.42), border_w))
    painter.setBrush(theme.qcolor_with_alpha(bg, 0.72))
    painter.drawRoundedRect(badge_rect, corner_radius, corner_radius)

    # Inner surface
    inset = max(1.0, border_w * 1.35)
    inner_rect = badge_rect.adjusted(inset, inset, -inset, -inset)
    painter.setPen(Qt.NoPen)
    painter.setBrush(theme.qcolor_with_alpha(bg, 0.24))
    painter.drawRoundedRect(inner_rect, corner_radius * 0.85, corner_radius * 0.85)

    # Label
    painter.setFont(font)
    painter.setPen(theme.qcolor_with_alpha(theme.text_color, 0.95))
    painter.drawText(badge_rect, Qt.AlignCenter, label)

    painter.end()
    return QIcon(pixmap)


__all__ = ["auto_icon"]
