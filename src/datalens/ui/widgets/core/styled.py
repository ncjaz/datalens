# src/datalens/ui/widgets/core/styled.py
from __future__ import annotations

from typing import Optional, Protocol

from datalens.ui.theme.app_theme import AppTheme


class StyledControl(Protocol):
    """
    Protocol for widgets that support applying an AppTheme and can be
    re-themed at runtime.

    Any class implementing:
        def apply_theme(self, theme: AppTheme) -> None: ...
    is considered a StyledControl.
    """

    def apply_theme(self, theme: AppTheme) -> None:
        ...


class StyledMixin:
    """
    Mixin for QSS-styled themed widgets (buttons, toggles, checkboxes, etc.).

    Responsibilities:

      - Colour overrides:
          * base (unselected) background
          * selected background
          * hover background (applies to both selected + unselected)
      - Pill shape configuration:
          * global defaults (class-level)
          * per-instance radius and padding
      - Colour resolution helper:
          * _resolve_colors(theme, default_base, default_selected)
            -> (base_bg, selected_bg, hover_base, hover_selected)

    IMPORTANT:
        This is NOT a QWidget. Concrete widgets must:

            * Inherit from a Qt widget (e.g. QPushButton) AND StyledMixin.
            * Call both __init__ methods, for example:

                class MyWidget(QPushButton, StyledMixin):
                    def __init__(self, theme: AppTheme, parent=None):
                        QPushButton.__init__(self, parent)
                        StyledMixin.__init__(self)
                        self.apply_theme(theme)

            * Implement apply_theme(self, theme: AppTheme) themselves,
              using _resolve_colors(...) and the pill attributes
              (_pill_radius, _pill_vpadding, _pill_hpadding) as needed.
    """

    # ------------------------------------------------------------------
    # GLOBAL pill defaults (can be changed at app startup via settings)
    # ------------------------------------------------------------------

    _default_pill_radius: int = 999
    _default_pill_vpadding: int = 6
    _default_pill_hpadding: int = 14

    @classmethod
    def set_global_pill_style(cls, radius: int, vpadding: int, hpadding: int) -> None:
        """
        Set the global default pill shape for all StyledMixin-based controls.

        Typical usage at startup after loading settings:

            StyledMixin.set_global_pill_style(
                radius=settings.control_pill_radius,
                vpadding=settings.control_pill_vpadding,
                hpadding=settings.control_pill_hpadding,
            )
        """
        cls._default_pill_radius = max(radius, 0)
        cls._default_pill_vpadding = max(vpadding, 0)
        cls._default_pill_hpadding = max(hpadding, 0)

    # ------------------------------------------------------------------

    def __init__(self) -> None:
        # Colour overrides (hex strings like "#RRGGBB")
        self._override_base_bg: Optional[str] = None
        self._override_selected_bg: Optional[str] = None
        self._override_hover_bg: Optional[str] = None

        # Last theme used (optional; useful if you want to reapply after a local change)
        self._theme: Optional[AppTheme] = None

        # Instance pill shape starts from GLOBAL defaults
        self._pill_radius: int = self._default_pill_radius
        self._pill_vpadding: int = self._default_pill_vpadding
        self._pill_hpadding: int = self._default_pill_hpadding

    # ---------------------------
    # Per-instance pill shape
    # ---------------------------

    def set_pill_radius(self, radius: int) -> None:
        """
        Override the pill radius for this instance.

        Use a large value (e.g. 999) for fully pill-shaped controls,
        or a smaller value for gentler rounding.
        """
        self._pill_radius = max(radius, 0)

    def set_pill_padding(self, vpadding: int, hpadding: int) -> None:
        """
        Override the vertical and horizontal padding for this instance.

        Higher vertical padding makes the pill taller; higher horizontal
        padding makes it wider.
        """
        self._pill_vpadding = max(vpadding, 0)
        self._pill_hpadding = max(hpadding, 0)

    # ---------------------------
    # Colour override setters
    # ---------------------------

    def set_base_color(self, hex_color: str) -> None:
        """
        Override the base (unselected) background colour for this control.
        """
        self._override_base_bg = hex_color

    def set_selected_color(self, hex_color: str) -> None:
        """
        Override the selected background colour for this control.
        """
        self._override_selected_bg = hex_color

    def set_hover_color(self, hex_color: str) -> None:
        """
        Override the hover background colour for BOTH selected and
        unselected states.

        If unset, hover colours are derived from base/selected via
        AppTheme.with_alpha_hex (if available).
        """
        self._override_hover_bg = hex_color

    def reset_colors_to_theme(self) -> None:
        """
        Clear all colour overrides so the control follows theme defaults again.
        """
        self._override_base_bg = None
        self._override_selected_bg = None
        self._override_hover_bg = None

    # ---------------------------
    # Colour resolution
    # ---------------------------

    def _resolve_colors(
        self,
        theme: AppTheme,
        *,
        default_base: str,
        default_selected: str,
    ) -> tuple[str, str, str, str]:
        """
        Resolve effective colours for this control.

        Args:
            theme:
                The current AppTheme instance.
            default_base:
                The default base (unselected) background for this control,
                e.g. theme.settings.secondary_color.
            default_selected:
                The default selected background for this control,
                e.g. theme.settings.primary_color or theme.settings.accent_confirm.

        Returns:
            (base_bg, selected_bg, hover_base, hover_selected)
        """
        self._theme = theme
        s = theme.settings

        # Base + selected from theme or overrides
        base_bg = self._override_base_bg or default_base
        selected_bg = self._override_selected_bg or default_selected

        # Hover logic
        if self._override_hover_bg:
            hover_base = self._override_hover_bg
            hover_selected = self._override_hover_bg
        else:
            if hasattr(theme, "with_alpha_hex"):
                hover_base = theme.with_alpha_hex(base_bg, 0.9)
                hover_selected = theme.with_alpha_hex(selected_bg, 0.9)
            else:
                hover_base = base_bg
                hover_selected = selected_bg

        return base_bg, selected_bg, hover_base, hover_selected
