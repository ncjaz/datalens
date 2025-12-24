"""
Simple color picker widget inspired by DataLens V1.

Provides a color box button + dropdown combo for selecting colors.
Users can either pick a custom color via QColorDialog or select from theme colors.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from datalens.ui.theme.app_theme import AppTheme


@dataclass
class ColorValue:
    """
    Represents a color selection with optional theme reference.

    Attributes:
        color: The actual QColor value (RGB only, alpha not stored here)
        theme_reference: Optional theme color key (e.g., "primary_color", "secondary_color")
                        None if it's a custom color
        opacity: Opacity value from 0.0 to 1.0 (separate from QColor alpha)
    """

    color: QColor
    theme_reference: str | None = None
    opacity: float = 1.0

    def to_dict(self) -> dict:
        """
        Serialize to dictionary for preferences storage.

        Returns:
            Dict with 'r', 'g', 'b', 'opacity', and optional 'theme_reference'
        """
        return {
            "r": self.color.red(),
            "g": self.color.green(),
            "b": self.color.blue(),
            "opacity": self.opacity,
            "theme_reference": self.theme_reference,
        }

    @staticmethod
    def from_dict(data: dict) -> ColorValue:
        """
        Deserialize from dictionary.

        Args:
            data: Dict with 'r', 'g', 'b', 'opacity', and optional 'theme_reference'

        Returns:
            ColorValue instance
        """
        r = int(data.get("r", 0))
        g = int(data.get("g", 0))
        b = int(data.get("b", 0))
        opacity = float(data.get("opacity", 1.0))
        theme_ref = data.get("theme_reference")
        return ColorValue(
            color=QColor(r, g, b),
            theme_reference=theme_ref if isinstance(theme_ref, str) else None,
            opacity=opacity,
        )

    def with_opacity(self) -> QColor:
        """
        Get a QColor with the opacity applied to the alpha channel.

        Returns:
            QColor with alpha set based on opacity value
        """
        result = QColor(self.color)
        result.setAlphaF(self.opacity)
        return result


class ColorPickerWidget(QWidget):
    """
    Simple color picker: color box button + dropdown.

    Features:
    - Click color box to open QColorDialog for custom color
    - Dropdown shows current color as hex/RGBA
    - Dropdown can be expanded to select from theme colors
    - Remembers last selection (custom or theme)

    Signals:
        color_changed: Emitted when color changes, passes ColorValue
    """

    color_changed = Signal(object)  # ColorValue

    # Theme color options with display names
    THEME_COLORS = [
        ("primary_color", "Primary"),
        ("secondary_color", "Secondary"),
        ("tertiary_color", "Tertiary"),
        ("background_color", "Background"),
        ("text_color", "Text"),
        ("confirm_color", "Confirm"),
        ("cancel_color", "Cancel"),
        ("warning_color", "Warning"),
        ("accent_confirm_border", "Confirm border"),
        ("accent_cancel_border", "Cancel border"),
        ("accent_warning_border", "Warning border"),
    ]

    def __init__(
        self,
        *,
        theme: AppTheme | None = None,
        initial_color: QColor | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._theme = theme
        self._current_color = initial_color or QColor(255, 255, 255)
        self._theme_reference: str | None = None
        self._opacity: float = 1.0

        self._setup_ui()
        self._populate_dropdown()
        self._update_color_button()

    def _setup_ui(self):
        """Create the UI: color button + dropdown + opacity slider."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # Top row: color button + dropdown
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        # Color box button
        self._color_button = QToolButton(self)
        self._color_button.setAutoRaise(True)
        self._color_button.setFixedSize(64, 24)
        self._color_button.setToolTip("Click to choose a custom color")
        self._color_button.clicked.connect(self._choose_custom_color)
        top_row.addWidget(self._color_button)

        # Dropdown showing hex/RGBA and theme colors
        self._dropdown = QComboBox(self)
        self._dropdown.setMinimumWidth(180)
        self._dropdown.setEditable(False)
        self._dropdown.currentIndexChanged.connect(self._on_dropdown_changed)
        top_row.addWidget(self._dropdown, 1)

        main_layout.addLayout(top_row)

        # Bottom row: opacity label + slider + value label
        opacity_row = QHBoxLayout()
        opacity_row.setContentsMargins(0, 0, 0, 0)
        opacity_row.setSpacing(8)

        opacity_label = QLabel("Opacity:", self)
        opacity_label.setFixedWidth(64)
        opacity_row.addWidget(opacity_label)

        self._opacity_slider = QSlider(Qt.Horizontal, self)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(100)
        self._opacity_slider.setSingleStep(1)
        self._opacity_slider.setPageStep(5)
        self._opacity_slider.setToolTip("Adjust color opacity (0% = transparent, 100% = opaque)")
        self._opacity_slider.valueChanged.connect(self._on_opacity_slider_changed)
        opacity_row.addWidget(self._opacity_slider, 1)

        self._opacity_value_label = QLabel("100%", self)
        self._opacity_value_label.setFixedWidth(40)
        self._opacity_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        opacity_row.addWidget(self._opacity_value_label)

        main_layout.addLayout(opacity_row)

    def _populate_dropdown(self):
        """Populate dropdown with current color and theme options."""
        self._dropdown.blockSignals(True)
        self._dropdown.clear()

        # Add current custom color as first item
        hex_str = self._current_color.name(QColor.HexRgb).upper()
        rgba_str = f"RGBA({self._current_color.red()}, {self._current_color.green()}, {self._current_color.blue()}, 255)"
        self._dropdown.addItem(f"Custom: {hex_str}", None)  # None = no theme reference
        self._dropdown.setItemData(0, f"Custom color: {rgba_str}", Qt.ToolTipRole)

        # Add separator
        self._dropdown.insertSeparator(1)

        # Add theme colors
        if self._theme:
            for theme_key, display_name in self.THEME_COLORS:
                theme_color_hex = getattr(self._theme, theme_key, "#FFFFFF")
                self._dropdown.addItem(f"Theme: {display_name}", theme_key)
                idx = self._dropdown.count() - 1
                self._dropdown.setItemData(idx, f"Theme color: {display_name} ({theme_color_hex})", Qt.ToolTipRole)

        # Select the appropriate item
        if self._theme_reference:
            # Find and select the theme color
            for i in range(self._dropdown.count()):
                if self._dropdown.itemData(i) == self._theme_reference:
                    self._dropdown.setCurrentIndex(i)
                    break
        else:
            # Select custom color (index 0)
            self._dropdown.setCurrentIndex(0)

        self._dropdown.blockSignals(False)

    def _update_color_button(self):
        """Update the color button's appearance to show current color."""
        hex_color = self._current_color.name(QColor.HexRgb)
        self._color_button.setStyleSheet(
            "QToolButton {"
            f"background-color: {hex_color};"
            "border: 1px solid rgba(255, 255, 255, 0.2);"
            "border-radius: 4px;"
            "}"
            "QToolButton:hover {"
            "border: 1px solid rgba(255, 255, 255, 0.4);"
            "}"
            "QToolButton:pressed {"
            "border: 2px solid rgba(255, 255, 255, 0.6);"
            "}"
        )

    def _choose_custom_color(self):
        """Open QColorDialog to choose a custom color."""
        chosen = QColorDialog.getColor(self._current_color, self, "Select Color")
        if chosen.isValid():
            self._current_color = chosen
            self._theme_reference = None  # Custom color, no theme reference
            self._update_color_button()
            self._populate_dropdown()  # Update dropdown to show new hex value
            self.color_changed.emit(self.current_value())

    def _on_dropdown_changed(self, index: int):
        """Handle dropdown selection change."""
        if index < 0:
            return

        theme_key = self._dropdown.itemData(index)

        if theme_key is None:
            # Custom color selected (index 0)
            # Color is already set, just clear theme reference
            self._theme_reference = None
        else:
            # Theme color selected
            self._theme_reference = theme_key
            if self._theme:
                # Update current color from theme
                theme_color_hex = getattr(self._theme, theme_key, "#FFFFFF")
                self._current_color = QColor(theme_color_hex)
                self._update_color_button()

        self.color_changed.emit(self.current_value())

    def _on_opacity_slider_changed(self, value: int):
        """Handle opacity slider change."""
        opacity = value / 100.0
        self._opacity = opacity
        self._opacity_value_label.setText(f"{value}%")
        self.color_changed.emit(self.current_value())

    def current_color(self) -> QColor:
        """Get the current color."""
        result = QColor(self._current_color)
        result.setAlphaF(self._opacity)
        return result

    def current_value(self) -> ColorValue:
        """Get the current ColorValue with theme reference if applicable."""
        return ColorValue(
            color=QColor(self._current_color),
            theme_reference=self._theme_reference,
            opacity=self._opacity,
        )

    def set_opacity(self, opacity: float):
        """
        Set the opacity value.

        Args:
            opacity: Opacity from 0.0 (transparent) to 1.0 (opaque)
        """
        self._set_opacity(opacity, emit=True)

    def _set_opacity(self, opacity: float, *, emit: bool) -> None:
        self._opacity = max(0.0, min(1.0, float(opacity)))
        # Update slider and label
        slider_value = int(round(self._opacity * 100))
        self._opacity_slider.blockSignals(True)
        self._opacity_slider.setValue(slider_value)
        self._opacity_slider.blockSignals(False)
        self._opacity_value_label.setText(f"{slider_value}%")
        if emit:
            self.color_changed.emit(self.current_value())

    def set_color(self, color: QColor, theme_reference: str | None = None):
        """
        Set the color and optional theme reference.

        Args:
            color: The color to set
            theme_reference: Optional theme color key
        """
        next_color = QColor(color)
        if theme_reference is None and next_color.alpha() != 255:
            self._set_opacity(next_color.alphaF(), emit=False)
            next_color.setAlpha(255)
        self._current_color = next_color
        self._theme_reference = theme_reference
        self._update_color_button()
        self._populate_dropdown()

    def set_value(self, value: ColorValue):
        """Set from a ColorValue."""
        self.set_color(value.color, value.theme_reference)
        self._set_opacity(value.opacity, emit=False)

    def to_dict(self) -> dict:
        """Serialize current value to dict for preferences."""
        return self.current_value().to_dict()

    def from_dict(self, data: dict):
        """Load value from dict (from preferences)."""
        value = ColorValue.from_dict(data)
        self.set_value(value)
        self._set_opacity(value.opacity, emit=False)


class ColorPickerButton(QToolButton):
    """
    A button that opens a color picker dialog when clicked.

    This is a simpler alternative to ColorPickerWidget when you just need
    a button that opens a color picker, without the dropdown.

    Signals:
        color_changed: Emitted when color changes, passes ColorValue
    """

    color_changed = Signal(object)  # ColorValue

    def __init__(
        self,
        *,
        theme: AppTheme | None = None,
        initial_color: QColor | None = None,
        text: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._theme = theme
        self._current_color = initial_color or QColor(255, 255, 255)
        self._theme_reference: str | None = None
        self._opacity: float = 1.0

        if text:
            self.setText(text)
        self.setAutoRaise(True)
        self.setFixedSize(64, 24)
        self.setToolTip("Click to choose a color")
        self.clicked.connect(self._choose_color)
        self._update_button_appearance()

    def _update_button_appearance(self):
        """Update button background to show current color."""
        hex_color = self._current_color.name(QColor.HexRgb)
        self.setStyleSheet(
            "QToolButton {"
            f"background-color: {hex_color};"
            "border: 1px solid rgba(255, 255, 255, 0.2);"
            "border-radius: 4px;"
            "}"
            "QToolButton:hover {"
            "border: 1px solid rgba(255, 255, 255, 0.4);"
            "}"
            "QToolButton:pressed {"
            "border: 2px solid rgba(255, 255, 255, 0.6);"
            "}"
        )

    def _choose_color(self):
        """Open QColorDialog."""
        chosen = QColorDialog.getColor(self._current_color, self, "Select Color")
        if chosen.isValid():
            self._current_color = chosen
            self._theme_reference = None
            self._update_button_appearance()
            self.color_changed.emit(self.current_value())

    def current_color(self) -> QColor:
        """Get current color."""
        result = QColor(self._current_color)
        result.setAlphaF(self._opacity)
        return result

    def current_value(self) -> ColorValue:
        """Get current ColorValue."""
        return ColorValue(
            color=QColor(self._current_color),
            theme_reference=self._theme_reference,
            opacity=self._opacity,
        )

    def set_opacity(self, opacity: float):
        """
        Set the opacity value.

        Args:
            opacity: Opacity from 0.0 (transparent) to 1.0 (opaque)
        """
        self._set_opacity(opacity, emit=True)

    def _set_opacity(self, opacity: float, *, emit: bool) -> None:
        self._opacity = max(0.0, min(1.0, float(opacity)))
        if emit:
            self.color_changed.emit(self.current_value())

    def set_color(self, color: QColor, theme_reference: str | None = None):
        """Set the color."""
        next_color = QColor(color)
        if theme_reference is None and next_color.alpha() != 255:
            self._set_opacity(next_color.alphaF(), emit=False)
            next_color.setAlpha(255)
        self._current_color = next_color
        self._theme_reference = theme_reference
        self._update_button_appearance()

    def set_value(self, value: ColorValue) -> None:
        self.set_color(value.color, value.theme_reference)
        self._set_opacity(value.opacity, emit=False)

    def to_dict(self) -> dict:
        return self.current_value().to_dict()

    def from_dict(self, data: dict) -> None:
        self.set_value(ColorValue.from_dict(data))


class ColorPreviewWidget(QWidget):
    """
    Small, non-interactive color swatch widget.

    Useful anywhere we want to display a color choice without exposing a full
    picker UI (e.g., preview next to a setting row).
    """

    def __init__(
        self,
        *,
        initial_value: ColorValue | None = None,
        size_px: int = 22,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._value = initial_value or ColorValue(color=QColor(255, 255, 255), opacity=1.0)
        size = max(8, int(size_px))
        self.setFixedSize(size, size)
        self._apply_style()

    def _apply_style(self) -> None:
        c = self._value.with_opacity()
        rgba = f"rgba({c.red()}, {c.green()}, {c.blue()}, {int(round(c.alphaF() * 255.0))})"
        self.setStyleSheet(
            "QWidget {"
            f"background-color: {rgba};"
            "border: 1px solid rgba(255, 255, 255, 0.20);"
            "border-radius: 4px;"
            "}"
        )

    def current_value(self) -> ColorValue:
        return self._value

    def set_value(self, value: ColorValue) -> None:
        self._value = value
        self._apply_style()

    def set_color(self, color: QColor, *, theme_reference: str | None = None) -> None:
        self._value = ColorValue(color=QColor(color), theme_reference=theme_reference, opacity=self._value.opacity)
        self._apply_style()

    def set_opacity(self, opacity: float) -> None:
        self._value = ColorValue(
            color=QColor(self._value.color),
            theme_reference=self._value.theme_reference,
            opacity=max(0.0, min(1.0, float(opacity))),
        )
        self._apply_style()


class ColorPickerDialog(QDialog):
    """
    Modal dialog wrapper around ColorPickerWidget + opacity slider.

    This is used by tests and by preference UIs that want an explicit "OK/Cancel"
    confirmation flow.
    """

    def __init__(
        self,
        *,
        theme: AppTheme | None = None,
        initial_value: ColorValue | None = None,
        title: str = "Select Color",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(str(title))

        self._picker = ColorPickerWidget(theme=theme, parent=self)
        self._opacity = QSlider(Qt.Horizontal, self)
        self._opacity.setRange(0, 100)
        self._opacity.setSingleStep(1)
        self._opacity.setPageStep(5)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self._picker)

        opacity_row = QHBoxLayout()
        opacity_row.setContentsMargins(0, 0, 0, 0)
        opacity_row.setSpacing(10)
        opacity_row.addWidget(QLabel("Opacity", self), 0)
        opacity_row.addWidget(self._opacity, 1)
        layout.addLayout(opacity_row)
        layout.addWidget(buttons)

        self._opacity.valueChanged.connect(self._on_opacity_changed)

        if initial_value is not None:
            self._picker.set_value(initial_value)
            self._picker.set_opacity(float(initial_value.opacity))
            self._opacity.setValue(int(round(max(0.0, min(1.0, float(initial_value.opacity))) * 100.0)))
        else:
            self._opacity.setValue(100)

    def _on_opacity_changed(self, value: int) -> None:
        self._picker.set_opacity(float(max(0, min(100, int(value)))) / 100.0)

    def current_value(self) -> ColorValue:
        return self._picker.current_value()

    def set_value(self, value: ColorValue):
        """Set from ColorValue."""
        self._picker.set_value(value)
        self._picker.set_opacity(float(value.opacity))
        self._opacity.setValue(int(round(max(0.0, min(1.0, float(value.opacity))) * 100.0)))

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return self.current_value().to_dict()

    def from_dict(self, data: dict):
        """Load from dict."""
        value = ColorValue.from_dict(data)
        self.set_value(value)


__all__ = [
    "ColorValue",
    "ColorPickerWidget",
    "ColorPickerButton",
    "ColorPreviewWidget",
    "ColorPickerDialog",
]
