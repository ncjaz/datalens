from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from datalens.domain.ui.theme import (
    DEFAULT_THEME,
    DEFAULT_THEME_OPACITY,
    ThemeOpacitySettings,
    ThemeSettings,
)
from datalens.ui.theme.color_utils import contrast_text_color, darken_color, lighten_color


class AppTheme(QObject):
    """
    Canonical V2 application theme wrapper.

    This is the single source of truth used by UI widgets. It wraps a frozen
    :class:`datalens.domain.ui.theme.ThemeSettings` instance and exposes:

    - QSS-friendly hex strings via ``*_color`` properties
    - QColor helpers for custom painting
    - ``theme_changed`` for future runtime re-theming
    """

    theme_changed = Signal()

    def __init__(
        self,
        settings: ThemeSettings | None = None,
        opacity: ThemeOpacitySettings | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings or DEFAULT_THEME
        self._opacity = opacity or DEFAULT_THEME_OPACITY

    @property
    def settings(self) -> ThemeSettings:
        return self._settings

    def set_settings(self, settings: ThemeSettings) -> None:
        self._settings = settings
        self.theme_changed.emit()

    def update_settings(self, **kwargs) -> None:
        self.set_settings(replace(self._settings, **kwargs))

    @property
    def opacity(self) -> ThemeOpacitySettings:
        return self._opacity

    def set_opacity(self, opacity: ThemeOpacitySettings) -> None:
        self._opacity = opacity
        self.theme_changed.emit()

    def update_opacity(self, **kwargs) -> None:
        self.set_opacity(replace(self._opacity, **kwargs))

    @property
    def primary_color(self) -> str:
        return self._settings.primary_color

    @property
    def background_color(self) -> str:
        return self._settings.background_color

    @property
    def secondary_color(self) -> str:
        """Secondary brand accent (not used for window surfaces)."""
        return self._settings.secondary_color

    @property
    def tertiary_color(self) -> str:
        return self._settings.tertiary_color

    @property
    def text_color(self) -> str:
        return self._settings.text_color

    @property
    def chart_grid_color(self) -> str:
        return self._settings.chart_grid_color

    @property
    def confirm_color(self) -> str:
        return self._settings.accent_confirm

    @property
    def cancel_color(self) -> str:
        return self._settings.accent_cancel

    @property
    def warning_color(self) -> str:
        return self._settings.accent_warning

    @property
    def primary_border(self) -> str:
        return self._settings.primary_border

    @property
    def secondary_border(self) -> str:
        return self._settings.secondary_border

    @property
    def tertiary_border(self) -> str:
        return self._settings.tertiary_border

    @property
    def confirm_border(self) -> str:
        return self._settings.accent_confirm_border

    @property
    def cancel_border(self) -> str:
        return self._settings.accent_cancel_border

    @property
    def warning_border(self) -> str:
        return self._settings.accent_warning_border

    def qcolor(self, hex_value: str) -> QColor:
        return QColor(hex_value)

    @property
    def primary(self) -> QColor:
        return QColor(self.primary_color)

    @property
    def background(self) -> QColor:
        return QColor(self.background_color)

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

    @staticmethod
    def _clamp_alpha(alpha: float) -> float:
        return max(0.0, min(float(alpha), 1.0))

    def with_alpha_hex(self, hex_color: str, alpha: float) -> str:
        """
        Return a Qt stylesheet-compatible colour string with alpha applied.

        Qt's stylesheet engine understands ``rgba(r, g, b, a)`` where ``a`` is
        an integer 0..255 (matching V1).
        """
        a = self._clamp_alpha(alpha)
        c = QColor(hex_color)
        a255 = int(round(a * 255))
        return f"rgba({c.red()},{c.green()},{c.blue()},{a255})"

    def qcolor_with_alpha(self, hex_color: str, alpha: float) -> QColor:
        c = QColor(hex_color)
        c.setAlphaF(self._clamp_alpha(alpha))
        return c

    # ------------------------------------------------------------------
    # Qt application palette (V1-style)
    # ------------------------------------------------------------------

    def apply_to(self, app: QApplication | None) -> None:
        """
        Apply this theme to a QApplication via the global palette.

        This mirrors the V1 approach:
        - Window surfaces derive from ``background_color`` (dark UI background).
        - Viewports (lists/trees/inputs) use slightly different roles (Base /
          AlternateBase) derived from the same background to create the "two
          shade" look in tabs like Annotation.
        - Selection highlight uses ``primary_color``.
        """
        if app is None:
            return

        app.setStyle("Fusion")

        palette = QPalette()
        background = QColor(self.background_color)
        text = QColor(self.text_color)

        palette.setColor(QPalette.Window, background)

        base = QColor(self._settings.surface_base) if self._settings.surface_base else darken_color(background, 0.90)
        alt = (
            QColor(self._settings.surface_alt)
            if self._settings.surface_alt
            else lighten_color(background, 1.10)
        )
        button = (
            QColor(self._settings.surface_button)
            if self._settings.surface_button
            else lighten_color(background, 1.05)
        )

        palette.setColor(QPalette.Base, base)
        palette.setColor(QPalette.AlternateBase, alt)
        palette.setColor(QPalette.Button, button)

        palette.setColor(QPalette.WindowText, text)
        palette.setColor(QPalette.Text, text)
        palette.setColor(QPalette.ButtonText, text)

        palette.setColor(QPalette.Highlight, QColor(self.primary_color))
        palette.setColor(
            QPalette.HighlightedText,
            QColor(contrast_text_color(bg_hex=self.primary_color, light_text=self.text_color, dark_text="#000000")),
        )

        palette.setColor(QPalette.ToolTipBase, lighten_color(background, 1.20))
        palette.setColor(QPalette.ToolTipText, text)
        palette.setColor(QPalette.Link, QColor(self.primary_color))
        palette.setColor(QPalette.BrightText, QColor("#FF5252"))

        app.setPalette(palette)

        # Keep tooltips consistent even if widgets use per-control QSS.
        app.setStyleSheet(
            "QToolTip {"
            f"background-color: {self.with_alpha_hex(self.primary_color, 0.85)};"
            "color: #ffffff;"
            "border: 1px solid rgba(255, 255, 255, 40);"
            "padding: 4px 6px;"
            "border-radius: 4px;"
            "}"
        )

    # ------------------------------------------------------------------
    # Standard "recipes" (consistent defaults across the UI)
    # ------------------------------------------------------------------

    def selected_fill(self, hex_color: str | None = None, *, alpha: float | None = None) -> str:
        return self.with_alpha_hex(
            hex_color or self.primary_color,
            self.opacity.selected_fill if alpha is None else alpha,
        )

    def subtle_fill(self, hex_color: str | None = None, *, alpha: float | None = None) -> str:
        return self.with_alpha_hex(
            hex_color or self.background_color,
            self.opacity.subtle_fill if alpha is None else alpha,
        )

    def hover_fill(self, hex_color: str, *, alpha: float | None = None) -> str:
        return self.with_alpha_hex(hex_color, self.opacity.hover_fill if alpha is None else alpha)

    def disabled_text_color(self, *, alpha: float | None = None) -> str:
        return self.with_alpha_hex(
            self.text_color,
            self.opacity.disabled_text if alpha is None else alpha,
        )

    def disabled_fill_color(self, hex_color: str | None = None, *, alpha: float | None = None) -> str:
        return self.with_alpha_hex(
            hex_color or self.background_color,
            self.opacity.disabled_fill if alpha is None else alpha,
        )

    def disabled_border_color(self, hex_color: str | None = None, *, alpha: float | None = None) -> str:
        return self.with_alpha_hex(
            hex_color or self.background_color,
            self.opacity.disabled_border if alpha is None else alpha,
        )
