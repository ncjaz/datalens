from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeSettings:
    """
    Theme colour tokens (opaque hex strings).

    Naming intent:
    - ``background_color``: foundation colour used for the Qt palette Window role.
    - ``secondary_color``: secondary brand accent (not the window background).
    - ``background_secondary_color``: optional secondary window surface colour for
      UI chrome (menu/status bars, tool strips) that should visually separate
      from the main window background.

    Optional surface overrides:
    When unset (None), UI should derive them from ``background_color`` so the
    palette stays coherent. When set, they can be used for accessibility or
    strict design control.
    """

    primary_color: str
    background_color: str
    secondary_color: str
    tertiary_color: str
    text_color: str
    chart_grid_color: str
    accent_confirm: str
    accent_cancel: str
    accent_warning: str

    primary_border: str
    secondary_border: str
    tertiary_border: str
    accent_confirm_border: str
    accent_cancel_border: str
    accent_warning_border: str

    background_secondary_color: str | None = None

    surface_base: str | None = None
    surface_button: str | None = None
    surface_alt: str | None = None


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
    hover_fill: float = 0.50

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
    background_color="#10141C",
    # Leave unset by default: the UI derives this from `background_color` so the
    # palette stays coherent, but it can be overridden for stronger separation.
    background_secondary_color="#161B27",
    secondary_color="#7a07f4",
    tertiary_color="#00BCD4",
    text_color="#F5F9FF",
    chart_grid_color="#FFFFFF",
    accent_confirm="#22C55E",
    accent_cancel="#EF4444",
    accent_warning="#F59E0B",
    primary_border="#F9A826",
    secondary_border="#7a07f4",
    tertiary_border="#00BCD4",
    accent_confirm_border="#22C55E",
    accent_cancel_border="#EF4444",
    accent_warning_border="#F59E0B",
)

DEFAULT_THEME_OPACITY = ThemeOpacitySettings()
