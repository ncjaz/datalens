# src/datalens/domain/theme.py
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class ThemeSettings:
    primary_color: str
    secondary_color: str
    tertiary_color: str
    text_color: str
    chart_grid_color: str
    accent_confirm: str
    accent_cancel: str
    accent_warning: str


@dataclass(frozen=True)
class ThemeOpacitySettings:
    """
    Central opacity policy for theme-driven UI styling.

    Theme *colours* are stored as opaque hex strings in :class:`ThemeSettings`.
    When the UI needs translucency (hover/disabled/selected fills), it should
    derive it using these alpha values rather than inventing per-widget magic
    numbers.

    Notes:
    - All values are clamped to 0..1 by :class:`datalens.ui.theme.app_theme.AppTheme`.
    - Widgets may still override opacity locally, but these are the defaults.
    """

    # Hover "tint" alpha. Most widgets use this as a low-opacity overlay of the
    # *selected/accent* colour while hovering inactive surfaces (matching V1).
    hover_fill: float = 0.30

    # Selected/active "fill" (e.g. selection cards: tinted bg).
    selected_fill: float = 0.25

    # Subtle fills/tracks (e.g. spinner track on secondary surfaces).
    subtle_fill: float = 0.45

    # Disabled state styling (foreground + surfaces).
    disabled_text: float = 0.55
    disabled_fill: float = 0.55
    disabled_border: float = 0.45


DEFAULT_THEME = ThemeSettings(
    primary_color="#F9A826",
    secondary_color="#10141C",
    tertiary_color="#00BCD4",
    text_color="#F5F9FF",
    chart_grid_color="#FFFFFF",
    accent_confirm="#22C55E",
    accent_cancel="#EF4444",
    accent_warning="#F59E0B",
)

DEFAULT_THEME_OPACITY = ThemeOpacitySettings()
