# src/datalens/ui/widgets/core/checkboxes.py
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QCheckBox

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.theme.color_utils import lighten_hex
from datalens.ui.widgets.core.styled import StyledMixin


class DatalensCheckBox(QCheckBox, StyledMixin):
    """
    Themed checkbox for DataLens.

    Features:
    - Uses StyledMixin for base/selected/hover color overrides.
    - Indicator matches DataLens V1 style (rounded square).
    - Fully theme reactive (text, indicator, hover, disabled).
    - Supports border override via set_border_color().
    - Provides enable(), disable(), set_disabled() helpers.

    Example:
        c = DatalensCheckBox("Enable autosave", ctx.app_theme)
        c.toggled.connect(...)
    """

    def __init__(self, text: str, theme: AppTheme, parent=None):
        QCheckBox.__init__(self, text, parent)
        StyledMixin.__init__(self)

        self._theme = theme
        self._border_color_override: Optional[str] = None

        self.apply_theme(theme)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_border_color(self, hex_color: str) -> None:
        """
        Override the border color around the indicator.
        If unset, border is a slightly lighter version of the indicator fill.
        """
        self._border_color_override = hex_color
        self.apply_theme(self._theme)

    def set_disabled(self, disabled: bool) -> None:
        self.setEnabled(not disabled)

    def disable(self) -> None:
        self.setEnabled(False)

    def enable(self) -> None:
        self.setEnabled(True)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def apply_theme(self, theme: AppTheme) -> None:
        """
        Apply theme styling.
        Uses StyledMixin._resolve_colors for base/selected/hover behavior.
        """
        self._theme = theme
        s = theme.settings

        # Checkboxes only care about checked (selected) vs unchecked (base)
        base_bg, selected_bg, hover_base, hover_selected = self._resolve_colors(
            theme,
            default_base=s.secondary_color,
            default_selected=s.primary_color,
        )

        # For checkboxes, hovering a checked indicator should still be visibly
        # different from the fully-opaque selected fill (V1-style subtle hover).
        hover_selected = theme.with_alpha_hex(selected_bg, theme.opacity.hover_fill)

        # Border color logic (same rule as buttons/toggles)
        if self._border_color_override:
            border_color = self._border_color_override
        else:
            border_color = lighten_hex(selected_bg, 1.20)

        text_color = s.text_color

        # Disabled colors: derived from theme opacity policy (consistent across UI)
        disabled_bg = theme.disabled_fill_color(s.secondary_color)
        disabled_text = theme.disabled_text_color()
        disabled_border = theme.disabled_border_color(s.secondary_color)

        indicator_size = 16
        indicator_radius = 4  # small rounding, not a pill

        qss = f"""
        /* Base text */
        QCheckBox {{
            color: {text_color};
            spacing: 6px;
        }}

        /* Indicator box (unchecked) */
        QCheckBox::indicator {{
            width: {indicator_size}px;
            height: {indicator_size}px;
            border-radius: {indicator_radius}px;
            background-color: {base_bg};
            border: 1px solid {border_color};
        }}

        /* Hover on unchecked */
        QCheckBox::indicator:hover:!checked:enabled {{
            background-color: {hover_base};
        }}

        /* Checked state */
        QCheckBox::indicator:checked {{
            background-color: {selected_bg};
            border: 1px solid {border_color};
        }}

        /* Hover while checked */
        QCheckBox::indicator:checked:hover:enabled {{
            background-color: {hover_selected};
        }}

        /* Disabled state */
        QCheckBox:disabled {{
            color: {disabled_text};
        }}
        QCheckBox::indicator:disabled {{
            background-color: {disabled_bg};
            border: 1px solid {disabled_border};
        }}
        """

        self.setStyleSheet(qss)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
