# src/datalens/ui/widgets/core/button.py
from __future__ import annotations

from enum import Enum
from typing import Optional

from PySide6.QtWidgets import QPushButton
from PySide6.QtGui import QColor

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.styled import StyledMixin


class ButtonVariant(str, Enum):
    """
    Semantic variants for buttons.

    PRIMARY   -> main action, uses theme primary color by default
    SECONDARY -> normal/less prominent action, uses theme secondary
    TERTIARY  -> uses theme tertiary (e.g. special accent)
    CONFIRM   -> confirm/OK/apply, uses theme accent_confirm
    CANCEL    -> cancel/quit/delete, uses theme accent_cancel
    WARNING   -> warning / careful, uses theme accent_warning if present
    """
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    WARNING = "warning"


class DatalensButton(QPushButton, StyledMixin):
    """
    Base themed button for DataLens.

    Core behaviour:
      - Uses StyledMixin for:
          * base/selected/hover colour resolution
          * pill radius + padding (global defaults + per-instance overrides)
      - Has semantic variants:
          * PRIMARY / SECONDARY / TERTIARY / CONFIRM / CANCEL / WARNING
      - Applies:
          * normal, hover, pressed, disabled states
          * border colour (derived from main colour unless overridden)

    Per-instance overrides:
      - set_primary_color_for_button(hex)
      - set_secondary_color_for_button(hex)
      - set_tertiary_color_for_button(hex)
      - set_main_color(hex)                # override normal background
      - set_hover_color(hex)
      - set_pressed_color(hex)
      - set_border_color(hex)

    Enable/disable helpers:
      - enable()
      - disable()
      - set_disabled(bool)

    Typical usage:
        btn = DatalensButton("OK", ctx.app_theme, ButtonVariant.CONFIRM)
        btn.clicked.connect(...)

    Plugin devs should subclass *this* rather than reimplementing theme logic.
    """

    def __init__(
        self,
        text: str,
        theme: AppTheme,
        variant: ButtonVariant = ButtonVariant.SECONDARY,
        parent: Optional[QPushButton] = None,
    ) -> None:
        QPushButton.__init__(self, text, parent)
        StyledMixin.__init__(self)

        self._variant = variant
        self._theme: AppTheme = theme

        # Local role colour overrides (if set, they replace theme primary/secondary/tertiary for this button)
        self._primary_override: Optional[str] = None
        self._secondary_override: Optional[str] = None
        self._tertiary_override: Optional[str] = None

        # Per-state overrides
        self._main_bg_override: Optional[str] = None
        self._hover_bg_override: Optional[str] = None
        self._pressed_bg_override: Optional[str] = None
        self._border_color_override: Optional[str] = None

        self.apply_theme(theme)

    # ------------------------------------------------------------------
    # Role colour overrides (per-button primary/secondary/tertiary)
    # ------------------------------------------------------------------

    def set_primary_color_for_button(self, hex_color: str) -> None:
        """Override the primary colour for this button instance."""
        self._primary_override = hex_color
        self.apply_theme(self._theme)

    def set_secondary_color_for_button(self, hex_color: str) -> None:
        """Override the secondary colour for this button instance."""
        self._secondary_override = hex_color
        self.apply_theme(self._theme)

    def set_tertiary_color_for_button(self, hex_color: str) -> None:
        """Override the tertiary colour for this button instance."""
        self._tertiary_override = hex_color
        self.apply_theme(self._theme)

    # ------------------------------------------------------------------
    # State-specific overrides
    # ------------------------------------------------------------------

    def set_main_color(self, hex_color: str) -> None:
        """
        Override the normal (enabled, not-hovered, not-pressed) background
        colour for this button.
        """
        self._main_bg_override = hex_color
        self.apply_theme(self._theme)

    def set_hover_color(self, hex_color: str) -> None:
        """Override the hover background colour."""
        self._hover_bg_override = hex_color
        self.apply_theme(self._theme)

    def set_pressed_color(self, hex_color: str) -> None:
        """Override the pressed background colour."""
        self._pressed_bg_override = hex_color
        self.apply_theme(self._theme)

    def set_border_color(self, hex_color: str) -> None:
        """
        Override the border colour. If this is NOT set, the border colour is
        derived as a slightly brighter version of the main colour.
        """
        self._border_color_override = hex_color
        self.apply_theme(self._theme)

    # ------------------------------------------------------------------
    # Enable / disable helpers
    # ------------------------------------------------------------------

    def set_disabled(self, disabled: bool) -> None:
        """Convenience wrapper around setEnabled with clearer semantics."""
        self.setEnabled(not disabled)

    def disable(self) -> None:
        """Disable this button (greyed out)."""
        self.setEnabled(False)

    def enable(self) -> None:
        """Enable this button."""
        self.setEnabled(True)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def apply_theme(self, theme: AppTheme) -> None:
        """
        Apply theme colours to this button.

        Called on construction and whenever the theme (or button overrides)
        change.

        Respects:
          - StyledMixin colour overrides (base/selected/hover)
          - Button-level primary/secondary/tertiary overrides
          - Button-level main/hover/pressed/border overrides
          - Global + per-instance pill shape from StyledMixin
        """
        self._theme = theme
        s = theme.settings

        # Resolve role colours for this button (local overrides OR theme)
        primary = self._primary_override or s.primary_color
        secondary = self._secondary_override or s.secondary_color
        tertiary = self._tertiary_override or getattr(s, "tertiary_color", s.primary_color)

        # Map variant -> default selected colour
        if self._variant is ButtonVariant.PRIMARY:
            selected_default = primary
        elif self._variant is ButtonVariant.SECONDARY:
            selected_default = primary  # primary fill, secondary as base surface
        elif self._variant is ButtonVariant.TERTIARY:
            selected_default = tertiary
        elif self._variant is ButtonVariant.CONFIRM:
            selected_default = getattr(s, "accent_confirm", primary)
        elif self._variant is ButtonVariant.CANCEL:
            selected_default = getattr(s, "accent_cancel", secondary)
        elif self._variant is ButtonVariant.WARNING:
            selected_default = getattr(s, "accent_warning", getattr(s, "accent_cancel", secondary))
        else:
            selected_default = primary

        # Use secondary as default "base" surface
        base_bg, selected_bg, hover_base, hover_selected = self._resolve_colors(
            theme,
            default_base=secondary,
            default_selected=selected_default,
        )

        # Apply per-state overrides on top
        normal_bg = self._main_bg_override or selected_bg
        hover_bg = self._hover_bg_override or hover_selected

        # Pressed: darker version of normal by default
        if self._pressed_bg_override:
            pressed_bg = self._pressed_bg_override
        else:
            pressed_bg = self._darken_hex(normal_bg, factor=1.15)

        # Border: slightly brighter than normal_bg by default if not overridden
        if self._border_color_override:
            border_color = self._border_color_override
        else:
            border_color = self._lighten_hex(normal_bg, factor=1.15)

        text_color = s.text_color

        # Disabled colours: prefer theme-provided, else generic grey
        disabled_bg = getattr(s, "disabled_bg_color", "#4B5563")   # slate-ish grey
        disabled_text = getattr(s, "disabled_text_color", "#9CA3AF")  # lighter grey
        disabled_border = getattr(s, "disabled_border_color", disabled_bg)

        radius = self._pill_radius
        vpad = self._pill_vpadding
        hpad = self._pill_hpadding

        # Build QSS
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {normal_bg};
                color: {text_color};
                border-radius: {radius}px;
                padding: {vpad}px {hpad}px;
                border: 1px solid {border_color};
            }}
            QPushButton:hover:!pressed:enabled {{
                background-color: {hover_bg};
            }}
            QPushButton:pressed:enabled {{
                background-color: {pressed_bg};
            }}
            QPushButton:disabled {{
                background-color: {disabled_bg};
                color: {disabled_text};
                border: 1px solid {disabled_border};
            }}
        """)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _lighten_hex(hex_color: str, factor: float = 1.15) -> str:
        """
        Return a slightly lighter version of the given hex colour using Qt's
        QColor.lighter. Factor > 1.0 = lighter.
        """
        try:
            c = QColor(hex_color)
            if not c.isValid():
                return hex_color
            # QColor.lighter takes percentage (100 = same, 150 = 1.5x lighter)
            pct = int(100 * factor)
            return c.lighter(pct).name()
        except Exception:
            return hex_color

    @staticmethod
    def _darken_hex(hex_color: str, factor: float = 1.15) -> str:
        """
        Return a slightly darker version of the given hex colour using Qt's
        QColor.darker. Factor > 1.0 = darker.
        """
        try:
            c = QColor(hex_color)
            if not c.isValid():
                return hex_color
            # QColor.darker takes percentage (100 = same, 150 = 1.5x darker)
            pct = int(100 * factor)
            return c.darker(pct).name()
        except Exception:
            return hex_color
