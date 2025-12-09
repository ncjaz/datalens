# src/datalens/theme/app_theme.py

from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor


class AppTheme(QObject):
    """
    Central theme definition for Datalens V2.

    - Holds all primary, secondary, tertiary color values
    - Holds semantic accent colors (confirm, cancel, warning)
    - Provides helpers for opacity and disabled states
    - Emits theme_changed when any color is updated
    """

    theme_changed = Signal()

    def __init__(
        self,
        *,
        primary_color: str = "#4DA3FF",
        secondary_color: str = "#20232A",
        tertiary_color: str = "#8B9BCC",

        text_color: str = "#FFFFFF",

        confirm_color: str = "#4CAF50",
        cancel_color: str = "#F44336",
        warning_color: str = "#FFC107",
    ) -> None:
        super().__init__()

        # Core palettes
        self.primary_color = primary_color
        self.secondary_color = secondary_color
        self.tertiary_color = tertiary_color

        # Text / foreground
        self.text_color = text_color

        # Semantic accents
        self.confirm_color = confirm_color
        self.cancel_color = cancel_color
        self.warning_color = warning_color

    # ------------------------------------------------------ #
    # Convenience: convert any stored hex string → QColor
    # ------------------------------------------------------ #

    def qcolor(self, hex_value: str) -> QColor:
        return QColor(hex_value)

    @property
    def primary(self) -> QColor:
        return QColor(self.primary_color)

    @property
    def secondary(self) -> QColor:
        return QColor(self.secondary_color)

    @property
    def tertiary(self) -> QColor:
        return QColor(self.tertiary_color)

    @property
    def text(self) -> QColor:
        return QColor(self.text_color)

    @property
    def confirm(self) -> QColor:
        return QColor(self.confirm_color)

    @property
    def cancel(self) -> QColor:
        return QColor(self.cancel_color)

    @property
    def warning(self) -> QColor:
        return QColor(self.warning_color)

    # ------------------------------------------------------ #
    # Helpers for opacity + disabled variants
    # ------------------------------------------------------ #

    @staticmethod
    def with_alpha(color: QColor, alpha: float) -> QColor:
        """
        Return a version of color with alpha multiplied by `alpha` (0–1).
        """
        c = QColor(color)
        c.setAlphaF(alpha)
        return c

    def disabled_color(self, base: QColor) -> QColor:
        """
        A softened / low-contrast version of a base color.
        Used for disabled buttons, checkboxes, toggles.
        """
        c = QColor(base)
        c.setAlphaF(0.4)
        return c

    # ------------------------------------------------------ #
    # Updating theme values
    # ------------------------------------------------------ #

    def update(
        self,
        *,
        primary_color: Optional[str] = None,
        secondary_color: Optional[str] = None,
        tertiary_color: Optional[str] = None,

        text_color: Optional[str] = None,

        confirm_color: Optional[str] = None,
        cancel_color: Optional[str] = None,
        warning_color: Optional[str] = None,
    ) -> None:
        """
        Update one or more theme colors and emit theme_changed.
        Widgets must re-apply theme via ThemedWidget.apply_theme().
        """

        if primary_color is not None:
            self.primary_color = primary_color

        if secondary_color is not None:
            self.secondary_color = secondary_color

        if tertiary_color is not None:
            self.tertiary_color = tertiary_color

        if text_color is not None:
            self.text_color = text_color

        if confirm_color is not None:
            self.confirm_color = confirm_color

        if cancel_color is not None:
            self.cancel_color = cancel_color

        if warning_color is not None:
            self.warning_color = warning_color

        self.theme_changed.emit()
