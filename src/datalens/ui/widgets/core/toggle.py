# src/datalens/ui/widgets/core/toggle.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QToolButton, QButtonGroup

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.styled import StyledMixin


@dataclass(frozen=True)
class ToggleOption:
    """
    Represents one side of a 2-button toggle.
    Example: ToggleOption(id="global", label="Global")
    """
    id: str
    label: str


class Toggle(QWidget, StyledMixin):
    """
    A themed 2-button toggle, matching the style used in DataLens V1
    (e.g., Keyboard Config window).

    By default it uses the AppTheme:

      - base (unselected) background: theme.settings.secondary_color
      - selected background:         theme.settings.primary_color
      - hover: derived via AppTheme.with_alpha_hex if available

    You can override colours at runtime via StyledMixin:

        toggle.set_base_color("#222222")      # unselected background
        toggle.set_selected_color("#00FF00")  # selected background
        toggle.set_hover_color("#333333")     # hover (both states)
        toggle.reset_colors_to_theme()

    And you can adjust the pill shape globally via:

        StyledMixin.set_global_pill_style(radius, vpadding, hpadding)

    Or per instance via:

        toggle.set_pill_radius(...)
        toggle.set_pill_padding(vpad, hpad)

    Additional per-toggle overrides:

        toggle.set_border_color("#FF00FF")

    Enable/disable helpers:

        toggle.disable()
        toggle.enable()
        toggle.set_disabled(True/False)

    Example:
        toggle = Toggle(
            theme=ctx.app_theme,
            left=ToggleOption("global", "Global"),
            right=ToggleOption("project", "Project"),
        )
        toggle.selectionChanged.connect(...)
    """

    # Emits ID of the selected option
    selectionChanged = Signal(str)

    def __init__(
        self,
        theme: AppTheme,
        left: ToggleOption,
        right: ToggleOption,
        parent: Optional[QWidget] = None,
    ) -> None:
        QWidget.__init__(self, parent)
        StyledMixin.__init__(self)

        self._theme = theme
        self._left = left
        self._right = right

        # Optional border override
        self._border_color_override: Optional[str] = None

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        # -----------------------------
        # Left button
        # -----------------------------
        self._btn_left = QToolButton(self)
        self._btn_left.setText(left.label)
        self._btn_left.setCheckable(True)
        self._btn_left.setCursor(Qt.PointingHandCursor)
        self._btn_left.setFocusPolicy(Qt.NoFocus)
        self._btn_left.setProperty("segment", "left")
        self._btn_left.toggled.connect(self._make_handler(left.id))
        self._group.addButton(self._btn_left)
        layout.addWidget(self._btn_left)

        # -----------------------------
        # Right button
        # -----------------------------
        self._btn_right = QToolButton(self)
        self._btn_right.setText(right.label)
        self._btn_right.setCheckable(True)
        self._btn_right.setCursor(Qt.PointingHandCursor)
        self._btn_right.setFocusPolicy(Qt.NoFocus)
        self._btn_right.setProperty("segment", "right")
        self._btn_right.toggled.connect(self._make_handler(right.id))
        self._group.addButton(self._btn_right)
        layout.addWidget(self._btn_right)

        # Default to "left" selected
        self._btn_left.setChecked(True)

        # Initial theme application
        self.apply_theme(theme)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def apply_theme(self, theme: AppTheme) -> None:
        """
        Apply theme colours to the widget.
        Called when theme changes or on construction.

        Respects any user-defined overrides for:
          - base (unselected) background
          - selected background
          - hover background
        And uses the StyledMixin pill radius / padding for shape.
        """
        self._theme = theme
        s = theme.settings

        base_bg, selected_bg, hover_unselected, hover_selected = self._resolve_colors(
            theme,
            default_base=s.secondary_color,
            default_selected=s.primary_color,
        )

        radius = self._pill_radius
        vpad = self._pill_vpadding
        hpad = self._pill_hpadding

        # Border: slightly brighter than selected/background unless overridden
        if self._border_color_override:
            border_color = self._border_color_override
        else:
            # Lighten selected colour a bit for border; fallback to base if invalid
            border_color = self._lighten_hex(selected_bg or base_bg, factor=1.15)

        text_color = s.text_color

        # Disabled colours: theme-provided, or generic grey
        disabled_bg = getattr(s, "disabled_bg_color", "#4B5563")        # slate-ish grey
        disabled_text = getattr(s, "disabled_text_color", "#9CA3AF")    # lighter grey
        disabled_border = getattr(s, "disabled_border_color", disabled_bg)

        qss = f"""
        QToolButton[segment="left"],
        QToolButton[segment="right"] {{
            background-color: {base_bg};
            color: {text_color};
            border: 1px solid {border_color};
            padding: {vpad}px {hpad}px;
            border-radius: {radius}px;
        }}

        /* Fix inner edges so segments join cleanly */
        QToolButton[segment="left"] {{
            border-top-right-radius: 0px;
            border-bottom-right-radius: 0px;
            border-right-width: 0px;
        }}

        QToolButton[segment="right"] {{
            border-top-left-radius: 0px;
            border-bottom-left-radius: 0px;
            border-left-width: 0px;
        }}

        /* Hover (unselected) */
        QToolButton[segment="left"]:!checked:hover:enabled,
        QToolButton[segment="right"]:!checked:hover:enabled {{
            background-color: {hover_unselected};
        }}

        /* Selected state */
        QToolButton[segment="left"]:checked:enabled,
        QToolButton[segment="right"]:checked:enabled {{
            background-color: {selected_bg};
            color: {text_color};
        }}

        /* Hover while selected */
        QToolButton[segment="left"]:checked:hover:enabled,
        QToolButton[segment="right"]:checked:hover:enabled {{
            background-color: {hover_selected};
        }}

        /* Disabled state */
        QToolButton[segment="left"]:disabled,
        QToolButton[segment="right"]:disabled {{
            background-color: {disabled_bg};
            color: {disabled_text};
            border: 1px solid {disabled_border};
        }}
        """

        self.setStyleSheet(qss)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current_id(self) -> str:
        """Returns the ID of the currently selected option."""
        return self._left.id if self._btn_left.isChecked() else self._right.id

    def set_current_id(self, id: str, emit: bool = True) -> None:
        """
        Programmatically set the selected option.

        If emit is False, selectionChanged will not be emitted.
        """
        if id == self._left.id:
            self._btn_left.setChecked(True)
        elif id == self._right.id:
            self._btn_right.setChecked(True)
        else:
            raise ValueError(f"Unknown toggle id: {id}")

        if emit:
            self.selectionChanged.emit(id)

    def set_border_color(self, hex_color: str) -> None:
        """
        Override the border colour of this toggle. If not set, the border
        colour is derived automatically as a slightly lighter version of
        the selected/base colour.
        """
        self._border_color_override = hex_color
        self.apply_theme(self._theme)

    def set_disabled(self, disabled: bool) -> None:
        """Convenience wrapper to enable/disable the toggle."""
        self.setEnabled(not disabled)

    def disable(self) -> None:
        """Disable the toggle (greyed out)."""
        self.setEnabled(False)

    def enable(self) -> None:
        """Enable the toggle."""
        self.setEnabled(True)

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _make_handler(self, segment_id: str):
        def handler(checked: bool) -> None:
            if checked:
                self.selectionChanged.emit(segment_id)
        return handler

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
            pct = int(100 * factor)  # 100 = same, 150 = 1.5x lighter
            return c.lighter(pct).name()
        except Exception:
            return hex_color
