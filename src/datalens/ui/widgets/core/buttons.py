# src/datalens/ui/widgets/core/buttons.py
from __future__ import annotations

from enum import Enum
from typing import Optional
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.ui.shortcuts.tooltips import attach_effective_shortcut_tooltip
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.theme.color_utils import contrast_text_color, darken_hex, lighten_hex
from datalens.ui.widgets.core.styled import StyledMixin


log = get_logger(__name__)


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
        *,
        outlined: bool = False,
    ) -> None:
        QPushButton.__init__(self, text, parent)
        StyledMixin.__init__(self)

        self._variant = variant
        self._theme: AppTheme = theme
        self._outlined = outlined
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(32)
        self._shortcut_tooltip_cleanup: Callable[[], None] | None = None

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

    def attach_shortcut_tooltip(
        self,
        *,
        plugin_id: PluginId,
        command_id: str,
        title: str | None = None,
        description: str | None = None,
        include_shortcut: bool = True,
    ) -> Callable[[], None]:
        """
        Keep this button's tooltip in sync with the effective chord for a registered shortcut command.

        This uses the managed shortcuts service (source of truth) rather than `QAction.setShortcut(...)`
        or `QShortcut`, so it avoids double-trigger issues.

        Returns a cleanup function that unsubscribes from shortcut changes.
        """

        prior = self._shortcut_tooltip_cleanup
        self._shortcut_tooltip_cleanup = None
        if callable(prior):
            try:
                prior()
            except Exception:
                log.debug("Failed to cleanup prior shortcut tooltip subscription", exc_info=True)

        cleanup = attach_effective_shortcut_tooltip(
            target=self,
            plugin_id=plugin_id,
            command_id=command_id,
            title=title or self.text(),
            description=description,
            include_shortcut=include_shortcut,
        )
        self._shortcut_tooltip_cleanup = cleanup
        return cleanup

    def set_outlined(self, outlined: bool) -> None:
        """Toggle outlined (border-only) styling for this button."""
        self._outlined = bool(outlined)
        self.apply_theme(self._theme)

    def set_variant(self, variant: ButtonVariant | str) -> None:
        """
        Change this button's semantic variant and re-apply theme styling.

        Accepts either:
        - a `ButtonVariant` enum member, or
        - a string value like `"confirm"` / `"cancel"`.

        This is best-effort: invalid inputs are logged and ignored rather than
        crashing the UI (timers may call this repeatedly).
        """
        try:
            if isinstance(variant, ButtonVariant):
                resolved = variant
            else:
                # Be robust to:
                # - callers passing an Enum from a different module (same values)
                # - callers passing `str(ButtonVariant.X)` (e.g. "ButtonVariant.CONFIRM")
                candidate: object = variant
                try:
                    candidate = getattr(variant, "value")  # type: ignore[attr-defined]
                except Exception:
                    candidate = variant
                resolved = ButtonVariant(str(candidate))
            self._variant = resolved
            self.apply_theme(self._theme)
        except Exception:
            log.warning(
                "Invalid button variant (best-effort): %r",
                variant,
                exc_info=True,
                extra={"operation": "ui", "phase": "variant_error"},
            )

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
            selected_default = secondary
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

        # Use background as default "base" surface
        base_bg, selected_bg, hover_base, hover_selected = self._resolve_colors(
            theme,
            default_base=s.background_color,
            default_selected=selected_default,
        )

        # Apply per-state overrides on top
        if self._outlined:
            normal_bg = self._main_bg_override or base_bg
        else:
            normal_bg = self._main_bg_override or selected_bg
        if self._hover_bg_override:
            hover_bg = self._hover_bg_override
        elif getattr(self, "_override_hover_bg", None):
            hover_bg = hover_selected
        elif self._outlined:
            hover_bg = hover_base
        else:
            hover_bg = lighten_hex(normal_bg, factor=1.12)

        # Pressed: darker version of normal by default
        if self._pressed_bg_override:
            pressed_bg = self._pressed_bg_override
        else:
            pressed_bg = hover_selected if self._outlined else darken_hex(normal_bg, factor=1.15)

        # Border: slightly brighter than normal_bg by default if not overridden
        if self._border_color_override:
            border_color = self._border_color_override
        else:
            if self._outlined:
                if self._variant is ButtonVariant.PRIMARY:
                    border_color = getattr(s, "primary_border", primary)
                elif self._variant is ButtonVariant.SECONDARY:
                    border_color = getattr(s, "secondary_border", secondary)
                elif self._variant is ButtonVariant.TERTIARY:
                    border_color = getattr(s, "tertiary_border", tertiary)
                elif self._variant is ButtonVariant.CONFIRM:
                    border_color = getattr(s, "accent_confirm_border", getattr(s, "accent_confirm", primary))
                elif self._variant is ButtonVariant.CANCEL:
                    border_color = getattr(s, "accent_cancel_border", getattr(s, "accent_cancel", secondary))
                elif self._variant is ButtonVariant.WARNING:
                    border_color = getattr(
                        s,
                        "accent_warning_border",
                        getattr(s, "accent_warning", getattr(s, "accent_cancel", secondary)),
                    )
                else:
                    border_color = selected_default
            else:
                border_color = lighten_hex(normal_bg, factor=1.15)

        # V1-style: use dark text on bright accents, light text on dark surfaces.
        if self._outlined:
            text_color = selected_default
        else:
            text_color = contrast_text_color(
                bg_hex=normal_bg,
                light_text=s.text_color,
                dark_text=s.background_color,
            )

        # Disabled colours: derived from theme opacity policy (consistent across UI)
        disabled_bg = theme.disabled_fill_color(s.background_color)
        disabled_text = theme.with_alpha_hex(text_color, theme.opacity.disabled_text)
        disabled_border = theme.disabled_border_color(s.background_color)

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
                border-radius: {radius}px;
            }}
            QPushButton:pressed:enabled {{
                background-color: {pressed_bg};
                border-radius: {radius}px;
            }}
            QPushButton:disabled {{
                background-color: {disabled_bg};
                color: {disabled_text};
                border: 1px solid {disabled_border};
                border-radius: {radius}px;
            }}
        """)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
