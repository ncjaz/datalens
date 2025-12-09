# src/datalens/domain/theme.py
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


DEFAULT_THEME = ThemeSettings(
    primary_color="#00BCD4",
    secondary_color="#10141C",
    tertiary_color="#F9A826",
    text_color="#F5F9FF",
    chart_grid_color="#FFFFFF",
    accent_confirm="#22C55E",
    accent_cancel="#EF4444",
)
