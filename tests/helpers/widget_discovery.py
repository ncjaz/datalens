"""
Widget discovery and enumeration for systematic testing.

This module provides tools to automatically discover and test groups of widgets
that work together (e.g., slider + auto button + reset button).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


@dataclass
class WidgetGroup:
    """
    Represents a group of widgets that work together.

    Example groups:
    - Exposure: {slider, auto_button, reset_button}
    - Camera: {dropdown, refresh_button}
    - Save path: text input + browse button
    """

    section: str  # Section name (e.g., "RGB Settings")
    control: str  # Control name (e.g., "Exposure")
    widgets: dict[str, QWidget] = field(default_factory=dict)  # Role -> widget mapping
    layout: QLayout | None = None  # The containing layout
    row_index: int | None = None  # Row index in form layout (if applicable)


class WidgetDiscovery:
    """
    Discover and enumerate widget groups in a plugin UI.

    This enables systematic testing of all controls across plugins without
    manually finding each widget.
    """

    @staticmethod
    def find_groups_in_panel(panel: QWidget) -> list[WidgetGroup]:
        """
        Find all widget groups in a panel.

        Returns groups like:
        - Exposure: {slider, auto_button, reset_button}
        - Focus: {slider, auto_button}
        - Camera: {dropdown, refresh_button}

        Args:
            panel: The root panel widget to search

        Returns:
            List of discovered widget groups
        """
        groups = []

        # Find all QGroupBox sections
        sections = panel.findChildren(QGroupBox)
        if not sections:
            # If no group boxes, treat the whole panel as a single section
            layout = panel.layout()
            if layout:
                section_name = panel.windowTitle() or "Root"
                if isinstance(layout, QFormLayout):
                    groups.extend(WidgetDiscovery._discover_form_layout_groups(section_name, layout))
                elif isinstance(layout, QGridLayout):
                    groups.extend(WidgetDiscovery._discover_grid_layout_groups(section_name, layout))
                elif isinstance(layout, (QVBoxLayout, QHBoxLayout)):
                    groups.extend(WidgetDiscovery._discover_box_layout_groups(section_name, layout))
            return groups

        for section in sections:
            section_name = section.title()
            layout = section.layout()

            if not layout:
                continue

            if isinstance(layout, QFormLayout):
                groups.extend(WidgetDiscovery._discover_form_layout_groups(section_name, layout))
            elif isinstance(layout, QGridLayout):
                groups.extend(WidgetDiscovery._discover_grid_layout_groups(section_name, layout))
            elif isinstance(layout, (QVBoxLayout, QHBoxLayout)):
                groups.extend(WidgetDiscovery._discover_box_layout_groups(section_name, layout))

        return groups

    @staticmethod
def _discover_form_layout_groups(section: str, layout: QFormLayout) -> list[WidgetGroup]:
    """Discover groups within a QFormLayout (label-widget pairs)."""
    groups = []
    for row in range(layout.rowCount()):
        label_item = layout.itemAt(row, QFormLayout.LabelRole)
        field_item = layout.itemAt(row, QFormLayout.FieldRole)

        if not field_item:
            continue

        label_text = ""
        if label_item and label_item.widget() and hasattr(label_item.widget(), "text"):
            label_text = label_item.widget().text()

        field_widget = field_item.widget()
        if not field_widget:
            continue

        widgets = WidgetDiscovery._extract_widgets_from_container(field_widget)
        if widgets:
            groups.append(
                WidgetGroup(
                    section=section,
                    control=label_text,
                    widgets=widgets,
                    layout=field_widget.layout() if hasattr(field_widget, "layout") else None,
                    row_index=row,
                )
            )
    return groups

    @staticmethod
    def _discover_grid_layout_groups(section: str, layout: QGridLayout) -> list[WidgetGroup]:
        """
        Discover groups within a QGridLayout.
        Assumes a pattern where column 0 is a label and subsequent columns are widgets.
        """
        groups = []
        for row in range(layout.rowCount()):
            # Find the label for the row (usually in column 0)
            label_item = layout.itemAtPosition(row, 0)
            label_text = ""
            if label_item and label_item.widget():
                widget = label_item.widget()
                if isinstance(widget, QLabel) and hasattr(widget, "text"):
                    label_text = widget.text().strip().replace(":", "")

            # Collect widgets in the rest of the row
            row_widgets = {}
            for col in range(layout.columnCount()):
                item = layout.itemAtPosition(row, col)
                if not item:
                    continue
                
                # Skip the label widget itself
                if item == label_item:
                    continue

                widget = item.widget()
                if not widget:
                    # Handle nested layouts in grid cells
                    if item.layout():
                        nested_widgets = WidgetDiscovery._extract_widgets_from_layout(item.layout())
                        for key, val in nested_widgets.items():
                            if key not in row_widgets:
                                row_widgets[key] = val
                            else:
                                i = 2
                                while f"{key}_{i}" in row_widgets:
                                    i += 1
                                row_widgets[f"{key}_{i}"] = val
                    continue
                
                category = WidgetDiscovery._categorize_widget(widget)
                if category:
                    if category not in row_widgets:
                        row_widgets[category] = widget
                    else:
                        i = 2
                        while f"{category}_{i}" in row_widgets:
                            i += 1
                        row_widgets[f"{category}_{i}"] = widget

            if row_widgets:
                control_name = label_text or f"Row {row}"
                groups.append(
                    WidgetGroup(
                        section=section,
                        control=control_name,
                        widgets=row_widgets,
                        layout=layout,
                        row_index=row,
                    )
                )
        return groups

    @staticmethod
    def _discover_box_layout_groups(section: str, layout: QLayout) -> list[WidgetGroup]:
        """
        Discover groups within a QVBoxLayout or QHBoxLayout.
        This method iterates through items, handling nested layouts and individual widgets.
        """
        groups = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if not item:
                continue

            # Case 1: Nested Layout
            if item.layout():
                nested_layout = item.layout()
                if isinstance(nested_layout, QFormLayout):
                    groups.extend(WidgetDiscovery._discover_form_layout_groups(section, nested_layout))
                elif isinstance(nested_layout, QGridLayout):
                    groups.extend(WidgetDiscovery._discover_grid_layout_groups(section, nested_layout))
                elif isinstance(nested_layout, (QVBoxLayout, QHBoxLayout)):
                    groups.extend(WidgetDiscovery._discover_box_layout_groups(section, nested_layout)) # Recursive call
                continue

            # Case 2: Widget
            widget = item.widget()
            if not widget:
                continue
            
            # Check if the widget has an explicit group ID property
            group_id = widget.property("widget_group_id")
            if group_id:
                # Logic to handle explicit groups (can be enhanced later)
                pass

            # If no explicit grouping, treat as an individual widget group
            # We often find simple widgets like buttons or checkboxes directly in box layouts.
            widgets = WidgetDiscovery._extract_widgets_from_container(widget)
            if widgets:
                # Determine a sensible control name
                control_name = widget.objectName()
                if not control_name:
                    # For buttons, use text. For others, use class name.
                    if hasattr(widget, "text") and callable(widget.text) and widget.text():
                        control_name = widget.text()
                    else:
                        control_name = f"{widget.__class__.__name__}_{i}"

                groups.append(
                    WidgetGroup(
                        section=section,
                        control=control_name.strip().replace(":", ""),
                        widgets=widgets,
                        layout=layout,
                        row_index=i,
                    )
                )
        return groups
        
    @staticmethod
    def _extract_widgets_from_layout(layout: QLayout) -> dict[str, QWidget]:
        """Helper to extract all widgets from any layout type."""
        widgets = {}
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if not item:
                continue
            
            if item.widget():
                widget = item.widget()
                category = WidgetDiscovery._categorize_widget(widget)
                if category:
                    if category not in widgets:
                        widgets[category] = widget
                    else:
                        j = 2
                        while f"{category}_{j}" in widgets:
                            j += 1
                        widgets[f"{category}_{j}"] = widget

            elif item.layout():
                # Recursive call for nested layouts
                nested_widgets = WidgetDiscovery._extract_widgets_from_layout(item.layout())
                for key, val in nested_widgets.items():
                    if key not in widgets:
                        widgets[key] = val
                    else:
                        j = 2
                        while f"{key}_{j}" in widgets:
                            j += 1
                        widgets[f"{key}_{j}"] = val
        return widgets

    @staticmethod
    def _extract_widgets_from_container(container: QWidget) -> dict[str, QWidget]:
        """
        Extract categorized widgets from a container widget.
        A container could be a simple widget or one with its own layout.
        """
        # If the container has a layout, extract widgets from it
        if container.layout():
            return WidgetDiscovery._extract_widgets_from_layout(container.layout())

        # If it's a single widget, categorize and return it
        category = WidgetDiscovery._categorize_widget(container)
        if category:
            return {category: container}
        
        return {}

    @staticmethod
    def _categorize_widget(widget: QWidget) -> str | None:
        """
        Categorize a widget by type and properties for role-based identification.
        """
        # Try to import custom widgets safely
        try:
            from datalens.ui.widgets.core.slider_option import DatalensSliderOption
        except ImportError:
            DatalensSliderOption = None

        obj_name = widget.objectName().lower()
        tooltip = widget.toolTip().lower()

        # Type-based categorization
        if DatalensSliderOption and isinstance(widget, DatalensSliderOption):
            return "slider"
        if isinstance(widget, QComboBox):
            return "dropdown"
        if isinstance(widget, QLineEdit):
            return "input"
        if isinstance(widget, (QPushButton, QToolButton)):
            # Property-based categorization for buttons
            if "auto" in obj_name or "auto" in tooltip:
                return "auto_button"
            if "reset" in obj_name or "reset" in tooltip:
                return "reset_button"
            if "refresh" in obj_name or "refresh" in tooltip:
                return "refresh_button"
            if "browse" in obj_name or "browse" in tooltip:
                return "browse_button"
            if "apply" in obj_name or "apply" in tooltip:
                return "apply_button"
            if "clear" in obj_name or "clear" in tooltip:
                return "clear_button"
            # Return a generic 'button' if no specific role found
            return "button"
        
        # Fallback for other known types
        if isinstance(widget, QLabel):
            return "label"
        if isinstance(widget, QGroupBox):
            return "groupbox"

        return None

    @staticmethod
    def print_discovery_report(groups: list[WidgetGroup], plugin_name: str = "Plugin") -> None:
        """
        Print a formatted discovery report.
        """
        print(f"\n{'='*70}")
        print(f"📊 Widget Discovery Report: {plugin_name}")
        print(f"{'='*70}")
        print(f"\nTotal groups found: {len(groups)}\n")

        if not groups:
            print("No widget groups were discovered. The UI might be empty or the discovery patterns need updates.")
            print(f"{'='*70}\n")
            return

        for i, group in enumerate(groups, 1):
            print(f"{i}. {group.section} > {group.control}")
            for role, widget in group.widgets.items():
                widget_class = widget.__class__.__name__
                obj_name = widget.objectName() or "(no name)"
                print(f"   └─ {role:20s} : {widget_class:30s} [{obj_name}]")
            print()

        print(f"{'='*70}\n")


__all__ = ["WidgetGroup", "WidgetDiscovery"]
