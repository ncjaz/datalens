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
    Represents one segment in a multi-button toggle.
    Example: ToggleOption(id="global", label="Global")
    """
    id: str
    label: str


class Toggle(QWidget, StyledMixin):
    """
    A themed multi-button segmented control with pill shape, matching DataLens V1 style.

    Supports 2 or more segments. With 2 segments, creates a pill shape with rounded ends.
    With 3+ segments, the middle segments have square corners and only the ends are rounded.

    By default it uses the AppTheme.

    - base (unselected) background: `theme.background_secondary_color`
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

    Example (2 segments - classic pill)::

        toggle = Toggle(
            theme=ctx.app_theme,
            ToggleOption("global", "Global"),
            ToggleOption("project", "Project"),
        )
        toggle.selectionChanged.connect(...)

    Example (3+ segments - extended pill)::

        toggle = Toggle(
            theme=ctx.app_theme,
            ToggleOption("rgb", "RGB"),
            ToggleOption("depth", "Depth"),
            ToggleOption("ir", "Infrared"),
        )

    Legacy constructor (2 segments only)::

        toggle = Toggle(
            theme=ctx.app_theme,
            left=ToggleOption("global", "Global"),
            right=ToggleOption("project", "Project"),
        )

    """

    # Emits ID of the selected option (exclusive mode only)
    selectionChanged = Signal(str)
    # Emits (id, checked) whenever a segment toggles (both modes)
    optionToggled = Signal(str, bool)

    def __init__(
        self,
        theme: AppTheme,
        *options: ToggleOption,
        left: Optional[ToggleOption] = None,
        right: Optional[ToggleOption] = None,
        exclusive: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        QWidget.__init__(self, parent)
        StyledMixin.__init__(self)

        self._theme = theme
        self._exclusive = bool(exclusive)

        # Support both new varargs style and legacy left/right kwargs
        if options:
            if left is not None or right is not None:
                raise ValueError("Cannot mix positional options with left/right kwargs")
            if len(options) < 2:
                raise ValueError("Toggle requires at least 2 options")
            self._options = list(options)
        elif left is not None and right is not None:
            # Legacy 2-button mode
            self._options = [left, right]
        else:
            raise ValueError("Toggle requires either 2+ positional options or left/right kwargs")

        # Optional border override
        self._border_color_override: Optional[str] = None

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self._group = QButtonGroup(self)
        self._group.setExclusive(bool(self._exclusive))

        # Create buttons for each option
        self._buttons: dict[str, QToolButton] = {}
        for i, option in enumerate(self._options):
            btn = QToolButton(self)
            btn.setText(option.label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            # Assign segment position for styling
            if len(self._options) == 2:
                # 2-button mode: left and right
                segment = "left" if i == 0 else "right"
            else:
                # 3+ button mode: left, middle(s), right
                if i == 0:
                    segment = "left"
                elif i == len(self._options) - 1:
                    segment = "right"
                else:
                    segment = "middle"

            btn.setProperty("segment", segment)
            btn.toggled.connect(self._make_handler(option.id))
            self._group.addButton(btn)
            layout.addWidget(btn, 1)
            self._buttons[option.id] = btn

        # Default selection:
        # - exclusive: first option selected (legacy behavior)
        # - non-exclusive: nothing selected by default
        if self._exclusive:
            self._buttons[self._options[0].id].setChecked(True)

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

        # Disabled selected state: use disabled version of selected color (maintains visual distinction)
        disabled_selected_bg = theme.disabled_fill_color(selected_bg)
        disabled_selected_border = theme.disabled_border_color(border_selected)

        qss = f"""
        QToolButton[segment="left"],
        QToolButton[segment="middle"],
        QToolButton[segment="right"] {{
            background-color: {base_bg};
            color: {text_color};
            border: 1px solid {border_unselected};
            padding: {vpad}px {hpad}px;
            border-radius: {radius}px;
        }}

        /* Left segment: rounded left side only */
        QToolButton[segment="left"] {{
            border-top-right-radius: 0px;
            border-bottom-right-radius: 0px;
            border-right-width: 1px;
        }}

        /* Middle segment(s): no rounding, connect to neighbors */
        QToolButton[segment="middle"] {{
            border-radius: 0px;
            border-left-width: 0px;
            border-right-width: 1px;
        }}

        /* Right segment: rounded right side only */
        QToolButton[segment="right"] {{
            border-top-left-radius: 0px;
            border-bottom-left-radius: 0px;
            border-left-width: 0px;
        }}

        /* Hover (unselected) */
        QToolButton[segment="left"]:!checked:hover:enabled,
        QToolButton[segment="middle"]:!checked:hover:enabled,
        QToolButton[segment="right"]:!checked:hover:enabled {{
            background-color: {hover_unselected};
        }}

        /* Selected state */
        QToolButton[segment="left"]:checked:enabled,
        QToolButton[segment="middle"]:checked:enabled,
        QToolButton[segment="right"]:checked:enabled {{
            background-color: {selected_bg};
            color: {text_color};
            border: 1px solid {border_selected};
        }}

        /* Hover while selected */
        QToolButton[segment="left"]:checked:hover:enabled,
        QToolButton[segment="middle"]:checked:hover:enabled,
        QToolButton[segment="right"]:checked:hover:enabled {{
            background-color: {hover_selected};
        }}

        /* Disabled state (unselected) */
        QToolButton[segment="left"]:!checked:disabled,
        QToolButton[segment="middle"]:!checked:disabled,
        QToolButton[segment="right"]:!checked:disabled {{
            background-color: {disabled_bg};
            color: {disabled_text};
            border: 1px solid {disabled_border};
        }}

        /* Disabled state (selected) - maintain visual distinction */
        QToolButton[segment="left"]:checked:disabled,
        QToolButton[segment="middle"]:checked:disabled,
        QToolButton[segment="right"]:checked:disabled {{
            background-color: {disabled_selected_bg};
            color: {disabled_text};
            border: 1px solid {disabled_selected_border};
        }}
        """

        self.setStyleSheet(qss)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current_id(self) -> str:
        """Returns the ID of the currently selected option (exclusive mode only)."""
        for option in self._options:
            if self._buttons[option.id].isChecked():
                return option.id
        # Fallback: return first option if none selected (shouldn't happen in exclusive mode)
        return self._options[0].id

    @property
    def checked_ids(self) -> set[str]:
        """
        Return the set of checked segment IDs.

        - In exclusive mode this will always be a single id.
        - In non-exclusive mode it may contain 0 to N ids.
        """
        out: set[str] = set()
        for option in self._options:
            if self._buttons[option.id].isChecked():
                out.add(option.id)
        return out

    def set_current_id(self, id: str, emit: bool = True) -> None:
        """
        Programmatically set the selected option.

        If emit is False, selectionChanged will not be emitted.
        """
        if id not in self._buttons:
            raise ValueError(f"Unknown toggle id: {id}")

        self._buttons[id].setChecked(True)

        if emit:
            self.selectionChanged.emit(id)

    def is_checked(self, id: str) -> bool:
        """Return whether the segment `id` is checked."""
        if id not in self._buttons:
            raise ValueError(f"Unknown toggle id: {id}")
        return bool(self._buttons[id].isChecked())

    def set_checked(self, id: str, checked: bool, *, emit: bool = True) -> None:
        """
        Set the checked state for a segment.

        In exclusive mode this behaves like `set_current_id` when `checked=True`.
        """
        if id not in self._buttons:
            raise ValueError(f"Unknown toggle id: {id}")

        self._buttons[id].setChecked(bool(checked))

        if emit:
            self.optionToggled.emit(str(id), bool(checked))
            if self._exclusive and bool(checked):
                self.selectionChanged.emit(str(id))

    def set_option_enabled(self, id: str, enabled: bool) -> None:
        """Enable/disable a single segment."""
        if id not in self._buttons:
            raise ValueError(f"Unknown toggle id: {id}")
        self._buttons[id].setEnabled(bool(enabled))

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
        Set toggle size from preset: "tiny", "small", "medium", "default", or "large".

        This is a convenience method that sets radius and padding proportionally
        to maintain the pill shape at different scales.

        Sizes:
            - "tiny":    20px tall (vpad=2, hpad=8,  radius=8)  - very compact
            - "small":   22px tall (vpad=3, hpad=10, radius=10) - compact
            - "medium":  24px tall (vpad=4, hpad=12, radius=12) - balanced
            - "default": 32px tall (vpad=6, hpad=18, radius=16) - V1 style
            - "large":   40px tall (vpad=8, hpad=24, radius=20) - prominent

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
            raise ValueError(f"Invalid size '{size}'. Choose from: {', '.join(sizes.keys())}")

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
