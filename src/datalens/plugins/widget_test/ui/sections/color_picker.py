from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.color_picker import ColorPickerButton, ColorPickerWidget, ColorValue

from .common import make_section_box


def build_color_picker_section(
    parent: QWidget,
    *,
    theme: AppTheme,
) -> QWidget:
    """Build the color picker demo section."""
    box = make_section_box(parent, "Color Picker")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(16)

    # Description
    desc = QLabel(
        "Color picker widget with RGB/HSV controls, opacity, and theme color selection.",
        box,
    )
    desc.setWordWrap(True)
    desc.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
    layout.addWidget(desc)

    # Full picker widget
    picker_label = QLabel("Color Picker Widget:", box)
    picker_label.setStyleSheet("font-weight: 700; font-size: 12px;")
    layout.addWidget(picker_label)

    picker = ColorPickerWidget(
        theme=theme,
        initial_color=QColor(theme.primary_color),
        parent=box,
    )
    picker.setMaximumHeight(300)
    layout.addWidget(picker)

    # Current value display
    value_label = QLabel("Current value: (no selection yet)", box)
    value_label.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.85)}; font-size: 11px;")
    layout.addWidget(value_label)

    def on_color_changed(value: ColorValue) -> None:
        """Update the value display when color changes."""
        color_hex = value.color.name()
        if value.theme_reference:
            value_label.setText(
                f"Current value: {color_hex} (theme: {value.theme_reference}, opacity: {value.opacity:.2f})"
            )
        else:
            value_label.setText(f"Current value: {color_hex} (custom, opacity: {value.opacity:.2f})")

    picker.color_changed.connect(on_color_changed)

    # Button pickers
    buttons_label = QLabel("Color Picker Buttons:", box)
    buttons_label.setStyleSheet("font-weight: 700; font-size: 12px; margin-top: 8px;")
    layout.addWidget(buttons_label)

    buttons_grid = QGridLayout()
    buttons_grid.setContentsMargins(0, 0, 0, 0)
    buttons_grid.setHorizontalSpacing(10)
    buttons_grid.setVerticalSpacing(8)
    layout.addLayout(buttons_grid)

    # Primary color button
    buttons_grid.addWidget(
        QLabel("Primary:", box),
        0,
        0,
        alignment=Qt.AlignRight | Qt.AlignVCenter,
    )
    primary_btn = ColorPickerButton(
        theme=theme,
        initial_color=QColor(theme.primary_color),
        parent=box,
    )
    primary_btn.setText("Choose Primary")
    buttons_grid.addWidget(primary_btn, 0, 1)

    # Secondary color button
    buttons_grid.addWidget(
        QLabel("Secondary:", box),
        1,
        0,
        alignment=Qt.AlignRight | Qt.AlignVCenter,
    )
    secondary_btn = ColorPickerButton(
        theme=theme,
        initial_color=QColor(theme.secondary_color),
        parent=box,
    )
    secondary_btn.setText("Choose Secondary")
    buttons_grid.addWidget(secondary_btn, 1, 1)

    # Warning color button
    buttons_grid.addWidget(
        QLabel("Warning:", box),
        2,
        0,
        alignment=Qt.AlignRight | Qt.AlignVCenter,
    )
    warning_btn = ColorPickerButton(
        theme=theme,
        initial_color=QColor(theme.warning_color),
        parent=box,
    )
    warning_btn.setText("Choose Warning")
    buttons_grid.addWidget(warning_btn, 2, 1)

    buttons_grid.setColumnStretch(1, 1)

    layout.addStretch(1)
    return box


__all__ = ["build_color_picker_section"]
