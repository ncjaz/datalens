from __future__ import annotations

"""
Toast notification demo section for widget_test plugin.

Demonstrates toast notifications with different types, positions, and durations.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QGridLayout, QLabel, QSpinBox, QWidget

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton
from datalens.ui.widgets.notifications import ToastIconType, ToastPosition
from datalens.services.notifications import show_error, show_info, show_success, show_warning

from .common import make_section_box


def build_toast_demo_section(
    parent: QWidget,
    *,
    theme: AppTheme,
) -> QWidget:
    """
    Build the toast notification demo section.

    Args:
        parent: Parent widget
        theme: Application theme

    Returns:
        Widget containing toast demo UI
    """
    box = make_section_box(parent, "Toast Notifications")
    layout = QGridLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setHorizontalSpacing(10)
    layout.setVerticalSpacing(10)

    # --- Toast Type Buttons ---
    row = 0

    layout.addWidget(QLabel("Quick Test:", box), row, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)

    success_btn = DatalensButton("Success", theme, ButtonVariant.CONFIRM, box)
    success_btn.clicked.connect(
        lambda: show_success("Operation Successful", "The task completed without errors")
    )
    layout.addWidget(success_btn, row, 1)

    warning_btn = DatalensButton("Warning", theme, ButtonVariant.WARNING, box)
    warning_btn.clicked.connect(
        lambda: show_warning("Memory Low", "Consider closing unused projects")
    )
    layout.addWidget(warning_btn, row, 2)

    error_btn = DatalensButton("Error", theme, ButtonVariant.CANCEL, box)
    error_btn.clicked.connect(
        lambda: show_error("Export Failed", "Disk full or permission denied")
    )
    layout.addWidget(error_btn, row, 3)

    info_btn = DatalensButton("Info", theme, ButtonVariant.PRIMARY, box)
    info_btn.clicked.connect(
        lambda: show_info("Processing Started", "This may take a few minutes")
    )
    layout.addWidget(info_btn, row, 4)

    # --- Custom Toast Configuration ---
    row += 1

    layout.addWidget(QLabel("Custom Toast:", box), row, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)

    # Duration spinner
    duration_label = QLabel("Duration (ms):", box)
    layout.addWidget(duration_label, row, 1, alignment=Qt.AlignRight | Qt.AlignVCenter)

    duration_spinner = QSpinBox(box)
    duration_spinner.setRange(0, 30000)
    duration_spinner.setValue(5000)
    duration_spinner.setSingleStep(1000)
    duration_spinner.setToolTip("0 = manual close only")
    layout.addWidget(duration_spinner, row, 2)

    # Position dropdown
    row += 1
    layout.addWidget(QLabel("Position:", box), row, 1, alignment=Qt.AlignRight | Qt.AlignVCenter)

    position_combo = QComboBox(box)
    position_options = [
        ("Bottom Right", ToastPosition.BOTTOM_RIGHT),
        ("Bottom Center", ToastPosition.BOTTOM_CENTER),
        ("Bottom Left", ToastPosition.BOTTOM_LEFT),
        ("Top Right", ToastPosition.TOP_RIGHT),
        ("Top Center", ToastPosition.TOP_CENTER),
        ("Top Left", ToastPosition.TOP_LEFT),
        ("Center", ToastPosition.CENTER),
        ("Center Left", ToastPosition.CENTER_LEFT),
        ("Center Right", ToastPosition.CENTER_RIGHT),
    ]
    for label, position in position_options:
        position_combo.addItem(label, position)
    layout.addWidget(position_combo, row, 2)

    # Icon type dropdown
    row += 1
    layout.addWidget(QLabel("Type:", box), row, 1, alignment=Qt.AlignRight | Qt.AlignVCenter)

    type_combo = QComboBox(box)
    type_options = [
        ("Success", ToastIconType.SUCCESS),
        ("Warning", ToastIconType.WARNING),
        ("Error", ToastIconType.ERROR),
        ("Info", ToastIconType.INFO),
    ]
    for label, icon_type in type_options:
        type_combo.addItem(label, icon_type)
    layout.addWidget(type_combo, row, 2)

    # Show Custom Toast button
    row += 1
    layout.addWidget(QLabel("", box), row, 0)  # Empty label for spacing

    show_custom_btn = DatalensButton("Show Custom Toast", theme, ButtonVariant.SECONDARY, box)

    def show_custom_toast() -> None:
        """Show toast with custom configuration."""
        from datalens.ui.widgets.notifications.toast_manager import ToastManager

        duration = duration_spinner.value()
        position = position_combo.currentData()
        icon_type = type_combo.currentData()

        try:
            manager = ToastManager.get_instance()
            manager.show_toast(
                title="Custom Toast",
                message=f"Duration: {duration}ms, Position: {position_combo.currentText()}",
                icon_type=icon_type,
                duration=duration,
                position=position,
            )
        except Exception as e:
            # Fallback if manager not initialized
            show_error("Toast Error", f"Failed to show toast: {e}")

    show_custom_btn.clicked.connect(show_custom_toast)
    layout.addWidget(show_custom_btn, row, 1, 1, 2)

    # --- Stress Test ---
    row += 1
    layout.addWidget(QLabel("Stress Test:", box), row, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)

    queue_test_btn = DatalensButton("Show 5 Toasts (Queue Test)", theme, ButtonVariant.TERTIARY, box)

    def show_queue_test() -> None:
        """Show multiple toasts to test queue system."""
        show_info("Toast 1", "First toast (should appear immediately)")
        show_success("Toast 2", "Second toast (should appear immediately)")
        show_warning("Toast 3", "Third toast (should appear immediately)")
        show_error("Toast 4", "Fourth toast (should be queued)")
        show_info("Toast 5", "Fifth toast (should be queued)")

    queue_test_btn.clicked.connect(show_queue_test)
    layout.addWidget(queue_test_btn, row, 1, 1, 2)

    # --- Long Text Test ---
    row += 1
    layout.addWidget(QLabel("Edge Cases:", box), row, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)

    long_text_btn = DatalensButton("Long Text Test", theme, ButtonVariant.TERTIARY, box)

    def show_long_text_toast() -> None:
        """Show toast with very long text to test eliding."""
        show_warning(
            "This is an extremely long title that should be truncated with an ellipsis to fit within the toast width constraints",
            "This is a very long message that spans multiple lines. It should wrap to multiple lines but be capped at the maximum height. "
            "If the message is too long, it will be truncated. This tests the text eliding and size constraint system. "
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
        )

    long_text_btn.clicked.connect(show_long_text_toast)
    layout.addWidget(long_text_btn, row, 1, 1, 2)

    # Add stretch to push everything to the top
    layout.setRowStretch(row + 1, 1)

    return box


__all__ = ["build_toast_demo_section"]
