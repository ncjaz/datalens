# src/datalens/ui/widgets/core/toggle.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QToolButton, QButtonGroup, QSizePolicy

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.theme.color_utils import lighten_hex
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

    By default it uses the AppTheme.

    - base (unselected) background: `theme.background_color`
    - selected background: `theme.primary_color`
    - hover: derived via theme opacity settings

    You can override colours at runtime via StyledMixin::

        toggle.set_base_color("#222222")      # unselected background
        toggle.set_selected_color("#00FF00")  # selected background
        toggle.set_hover_color("#333333")     # hover (both states)
        toggle.reset_colors_to_theme()

    And you can adjust the pill shape globally via::

        StyledMixin.set_global_pill_style(radius, vpadding, hpadding)

    Or per instance via::

        toggle.set_pill_radius(...)
        toggle.set_pill_padding(vpad, hpad)

    Additional per-toggle overrides::

        toggle.set_border_color("#FF00FF")

    Enable/disable helpers::

        toggle.disable()
        toggle.enable()
        toggle.set_disabled(True/False)

    Example::

        toggle = Toggle(
            theme=ctx.app_theme,
            left=ToggleOption("global", "Global"),
            right=ToggleOption("project", "Project"),
        )
        toggle.selectionChanged.connect(...)

    """

    # Emits ID of the selected option (exclusive mode only)
    selectionChanged = Signal(str)
    # Emits (id, checked) whenever a segment toggles (both modes)
    optionToggled = Signal(str, bool)

    def __init__(
        self,
        theme: AppTheme,
        left: ToggleOption,
        right: ToggleOption,
        *,
        exclusive: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        QWidget.__init__(self, parent)
        StyledMixin.__init__(self)

        self._theme = theme
        self._left = left
        self._right = right
        self._exclusive = bool(exclusive)

        # Optional border override
        self._border_color_override: Optional[str] = None

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self._group = QButtonGroup(self)
        self._group.setExclusive(bool(self._exclusive))

        # -----------------------------
        # Left button
        # -----------------------------
        self._btn_left = QToolButton(self)
        self._btn_left.setText(left.label)
        self._btn_left.setCheckable(True)
        self._btn_left.setCursor(Qt.PointingHandCursor)
        self._btn_left.setFocusPolicy(Qt.NoFocus)
        self._btn_left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_left.setProperty("segment", "left")
        self._btn_left.toggled.connect(self._make_handler(left.id))
        self._group.addButton(self._btn_left)
        layout.addWidget(self._btn_left, 1)

        # -----------------------------
        # Right button
        # -----------------------------
        self._btn_right = QToolButton(self)
        self._btn_right.setText(right.label)
        self._btn_right.setCheckable(True)
        self._btn_right.setCursor(Qt.PointingHandCursor)
        self._btn_right.setFocusPolicy(Qt.NoFocus)
        self._btn_right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_right.setProperty("segment", "right")
        self._btn_right.toggled.connect(self._make_handler(right.id))
        self._group.addButton(self._btn_right)
        layout.addWidget(self._btn_right, 1)

        # Default selection:
        # - exclusive: left selected (legacy behavior)
        # - non-exclusive: nothing selected by default
        if self._exclusive:
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

        Uses the `StyledMixin` pill radius / padding for shape.
        """
        self._theme = theme
        s = theme.settings

        base_bg, selected_bg, hover_unselected, hover_selected = self._resolve_colors(
            theme,
            default_base=s.background_secondary_color,  # Use secondary background for unselected state
            default_selected=s.primary_color,
        )

        radius = self._pill_radius
        vpad = self._pill_vpadding
        hpad = self._pill_hpadding

        # Border: different for selected vs unselected
        if self._border_color_override:
            border_selected = self._border_color_override
            border_unselected = self._border_color_override
        else:
            # Selected: slightly brighter than selected color
            border_selected = lighten_hex(selected_bg, factor=1.15)
            # Unselected: subtle border at 50% opacity (less eye-popping)
            border_unselected = theme.with_alpha_hex(s.primary_border, 0.50)

        text_color = s.text_color

        # Disabled colours: derived from theme opacity policy (consistent across UI)
        disabled_bg = theme.disabled_fill_color(s.background_secondary_color)
        disabled_text = theme.disabled_text_color()
        disabled_border = theme.disabled_border_color(s.accent_cancel_border)

        qss = f"""
        QToolButton[segment="left"],
        QToolButton[segment="right"] {{
            background-color: {base_bg};
            color: {text_color};
            border: 1px solid {border_unselected};
            padding: {vpad}px {hpad}px;
            border-radius: {radius}px;
        }}

        /* Fix inner edges so segments join cleanly */
        QToolButton[segment="left"] {{
            border-top-right-radius: 0px;
            border-bottom-right-radius: 0px;
            /* Keep a 1px divider between segments (avoid double thickness by
               disabling the left border on the right segment). */
            border-right-width: 1px;
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
            border: 1px solid {border_selected};
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

    @property
    def checked_ids(self) -> set[str]:
        """
        Return the set of checked segment IDs.

        - In exclusive mode this will always be a single id.
        - In non-exclusive mode it may contain 0, 1, or 2 ids.
        """
        out: set[str] = set()
        if self._btn_left.isChecked():
            out.add(self._left.id)
        if self._btn_right.isChecked():
            out.add(self._right.id)
        return out

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

    def is_checked(self, id: str) -> bool:
        """Return whether the segment `id` is checked."""
        if id == self._left.id:
            return bool(self._btn_left.isChecked())
        if id == self._right.id:
            return bool(self._btn_right.isChecked())
        raise ValueError(f"Unknown toggle id: {id}")

    def set_checked(self, id: str, checked: bool, *, emit: bool = True) -> None:
        """
        Set the checked state for a segment.

        In exclusive mode this behaves like `set_current_id` when `checked=True`.
        """
        if id == self._left.id:
            self._btn_left.setChecked(bool(checked))
        elif id == self._right.id:
            self._btn_right.setChecked(bool(checked))
        else:
            raise ValueError(f"Unknown toggle id: {id}")

        if emit:
            self.optionToggled.emit(str(id), bool(checked))
            if self._exclusive and bool(checked):
                self.selectionChanged.emit(str(id))

    def set_option_enabled(self, id: str, enabled: bool) -> None:
        """Enable/disable a single segment."""
        if id == self._left.id:
            self._btn_left.setEnabled(bool(enabled))
            return
        if id == self._right.id:
            self._btn_right.setEnabled(bool(enabled))
            return
        raise ValueError(f"Unknown toggle id: {id}")

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

    def set_size(self, size: str) -> None:
        """
        Set toggle size from preset: "small", "medium" (default), or "large".

        This is a convenience method that sets radius and padding proportionally
        to maintain the pill shape at different scales.

        Sizes:
            - "small":  24px tall (vpad=4, hpad=12, radius=12)
            - "medium": 32px tall (vpad=6, hpad=18, radius=16) [default]
            - "large":  40px tall (vpad=8, hpad=24, radius=20)

        Example:
            toggle.set_size("small")
            toggle.apply_theme(theme)
        """
        sizes = {
            "tiny":   (8,  2,  8),   # 20px tall - very compact
            "small":  (10, 3, 10),   # 22px tall - compact
            "medium": (12, 4, 12),   # 24px tall - balanced
            "default":(16, 6, 18),   # 32px tall - V1 style
            "large":  (20, 8, 24),   # 40px tall - prominent
        }

        if size not in sizes:
            raise ValueError(f"Invalid size '{size}'. Choose 'small', 'medium', or 'large'.")

        radius, vpad, hpad = sizes[size]
        self._pill_radius = radius
        self._pill_vpadding = vpad
        self._pill_hpadding = hpad

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _make_handler(self, segment_id: str):
        def handler(checked: bool) -> None:
            self.optionToggled.emit(segment_id, bool(checked))
            if self._exclusive and checked:
                self.selectionChanged.emit(segment_id)
        return handler


# Alias for readability in UI code: "segmented" describes the control better than
# a generic "Toggle", and avoids Qt's own QAbstractButton::toggle naming clash.
DatalensSegmentedToggle = Toggle
DatalensSegmentedToggleOption = ToggleOption
