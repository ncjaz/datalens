from __future__ import annotations

from PySide6.QtGui import QColor


def lighten_color(color: QColor, factor: float = 1.15) -> QColor:
    result = QColor(color)
    if not result.isValid():
        return result
    pct = int(100 * float(factor))
    return result.lighter(pct)


def darken_color(color: QColor, factor: float = 1.15) -> QColor:
    result = QColor(color)
    if not result.isValid():
        return result
    factor = float(factor)
    if factor <= 0:
        return result
    # Support both conventions:
    # - factor > 1.0: darker by percentage (e.g. 1.15 -> darker(115))
    # - factor < 1.0: darker by multiplier (e.g. 0.90 -> darker(111))
    pct = int(round(100 / factor)) if factor < 1.0 else int(round(100 * factor))
    return result.darker(max(0, pct))


def lighten_hex(hex_color: str, factor: float = 1.15) -> str:
    color = QColor(hex_color)
    if not color.isValid():
        return hex_color
    return lighten_color(color, factor).name()


def darken_hex(hex_color: str, factor: float = 1.15) -> str:
    color = QColor(hex_color)
    if not color.isValid():
        return hex_color
    return darken_color(color, factor).name()


def contrast_text_color(*, bg_hex: str, light_text: str, dark_text: str) -> str:
    bg = QColor(bg_hex)
    light = QColor(light_text)
    dark = QColor(dark_text)
    if not bg.isValid():
        return light_text
    if not light.isValid() or not dark.isValid():
        return light_text

    def to_linear(x: float) -> float:
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    def rel_lum(c: QColor) -> float:
        r = to_linear(c.redF())
        g = to_linear(c.greenF())
        b = to_linear(c.blueF())
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def contrast_ratio(a: QColor, b: QColor) -> float:
        la = rel_lum(a)
        lb = rel_lum(b)
        hi = max(la, lb)
        lo = min(la, lb)
        return (hi + 0.05) / (lo + 0.05)

    light_cr = contrast_ratio(bg, light)
    dark_cr = contrast_ratio(bg, dark)
    return dark_text if dark_cr >= light_cr else light_text
