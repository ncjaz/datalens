# Systematic Widget Group Testing

This document outlines a systematic approach for testing groups of UI widgets that work together (e.g., slider + auto button + reset button), applicable across all plugins.

## Problem Statement

Plugins have **control groups** where multiple widgets work together:
- **Exposure control**: Slider + Auto button + Reset button
- **Camera selection**: Dropdown + Refresh button
- **Save settings**: Path input + Browse button
- **Format options**: Toggle + Checkboxes

We need a **systematic, scalable** approach to:
1. Discover and enumerate widget groups
2. Test interactions within each group
3. Verify keyboard/mouse/modifier shortcuts
4. Work across all current and future plugins

---

## Current State

### What Exists ✅

1. **Widget Organization Patterns**:
   - `QGroupBox` + `QFormLayout` for settings sections
   - Composite widgets (e.g., `QHBoxLayout` with slider + buttons)
   - `setObjectName()` for widget identification

2. **Testing Utilities**:
   - `findChild(Type, "ObjectName")` for widget discovery
   - `findChildren(Type)` for bulk discovery
   - Event and state watchers for verification

3. **Preference Schema**:
   - Manifest-driven preferences (but no UI structure metadata)
   - Field types: bool, enum, toggle, int, float, string, path

### What's Missing ❌

1. **No widget group metadata** - No way to know "these 3 widgets work together"
2. **No declarative UI structure** - Widget hierarchy not in manifest
3. **No automatic widget discovery** - Must manually find each widget type
4. **No built-in interaction testing** - Each test must manually click/type/verify

---

## Proposed Solution: Multi-Level Approach

We'll implement **three complementary strategies** that work together:

### Level 1: Convention-Based Discovery (Quick Win)
Use naming conventions and Qt's widget hierarchy

### Level 2: Metadata Annotations (Medium Term)
Add optional metadata to widgets for grouping

### Level 3: Declarative UI Schema (Long Term)
Extend manifest to declare UI structure

---

## Level 1: Convention-Based Discovery

### Strategy

Leverage existing patterns without changing plugin code:

1. **Object name conventions**: `{Plugin}_{Section}_{Control}_{Type}`
   - Example: `Capture_RGB_Exposure_Slider`
   - Example: `Capture_RGB_Exposure_AutoButton`
   - Example: `Capture_RGB_Exposure_ResetButton`

2. **Widget type patterns**: Known widget combinations
   - `DatalensSliderOption` often has auto/reset buttons
   - `QComboBox` often has refresh button
   - `QLineEdit` (path) often has browse button

3. **Layout hierarchy**: Use Qt's parent-child relationships
   - Find `QGroupBox` sections
   - Enumerate children within each section
   - Group by row in `QFormLayout`

### Implementation

```python
# tests/helpers/widget_discovery.py

from dataclasses import dataclass
from typing import Type
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QFormLayout, QHBoxLayout,
    QVBoxLayout, QLayout
)

@dataclass
class WidgetGroup:
    """Represents a group of widgets that work together."""
    section: str  # e.g., "RGB Settings"
    control: str  # e.g., "Exposure"
    widgets: dict[str, QWidget]  # e.g., {"slider": ..., "auto_button": ...}
    layout: QLayout | None  # The containing layout

class WidgetDiscovery:
    """Discover and enumerate widget groups in a plugin UI."""

    @staticmethod
    def find_groups_in_panel(panel: QWidget) -> list[WidgetGroup]:
        """
        Find all widget groups in a panel.

        Returns groups like:
        - Exposure: {slider, auto_button, reset_button}
        - Focus: {slider, auto_button}
        - Camera: {dropdown, refresh_button}
        """
        groups = []

        # Find all QGroupBox sections
        sections = panel.findChildren(QGroupBox)

        for section in sections:
            section_name = section.title()
            layout = section.layout()

            if isinstance(layout, QFormLayout):
                # Form layout: each row is a potential group
                groups.extend(
                    WidgetDiscovery._discover_form_layout_groups(
                        section_name, layout
                    )
                )
            elif isinstance(layout, QVBoxLayout):
                # Vertical layout: scan for nested groups
                groups.extend(
                    WidgetDiscovery._discover_vbox_groups(
                        section_name, layout
                    )
                )

        return groups

    @staticmethod
    def _discover_form_layout_groups(
        section: str,
        layout: QFormLayout
    ) -> list[WidgetGroup]:
        """Discover groups within a QFormLayout (label-widget pairs)."""
        groups = []

        for row in range(layout.rowCount()):
            label_item = layout.itemAt(row, QFormLayout.LabelRole)
            field_item = layout.itemAt(row, QFormLayout.FieldRole)

            if not field_item:
                continue

            # Get the label text (control name)
            label = ""
            if label_item and label_item.widget():
                label = label_item.widget().text()

            # Check if field is a composite widget (HBox with multiple widgets)
            field_widget = field_item.widget()
            if not field_widget:
                continue

            widgets = WidgetDiscovery._extract_widgets_from_container(
                field_widget
            )

            if widgets:
                groups.append(WidgetGroup(
                    section=section,
                    control=label,
                    widgets=widgets,
                    layout=field_widget.layout()
                ))

        return groups

    @staticmethod
    def _extract_widgets_from_container(
        container: QWidget
    ) -> dict[str, QWidget]:
        """
        Extract categorized widgets from a container.

        Returns dict like:
        - {"slider": DatalensSliderOption, "auto_button": QPushButton}
        - {"dropdown": QComboBox, "refresh_button": QPushButton}
        """
        from datalens.ui.widgets.core.slider_option import DatalensSliderOption
        from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton

        widgets = {}

        # Check if container itself is a known widget
        if isinstance(container, DatalensSliderOption):
            widgets["slider"] = container
            # Slider option has built-in reset
            return widgets

        # Check if container has layout with children
        layout = container.layout()
        if not layout:
            # Single widget, not a group
            if isinstance(container, (QComboBox, QLineEdit)):
                widgets["input"] = container
            return widgets

        # Scan layout for widgets
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if not item:
                continue

            widget = item.widget()
            if not widget:
                continue

            # Categorize by type and object name
            widget_type = WidgetDiscovery._categorize_widget(widget)
            if widget_type:
                widgets[widget_type] = widget

        return widgets

    @staticmethod
    def _categorize_widget(widget: QWidget) -> str | None:
        """
        Categorize a widget by type and object name.

        Returns category like:
        - "slider", "auto_button", "reset_button"
        - "dropdown", "refresh_button"
        - "input", "browse_button"
        """
        from datalens.ui.widgets.core.slider_option import DatalensSliderOption
        from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton, QToolButton

        obj_name = widget.objectName().lower()

        # Check by type first
        if isinstance(widget, DatalensSliderOption):
            return "slider"
        elif isinstance(widget, QComboBox):
            return "dropdown"
        elif isinstance(widget, QLineEdit):
            return "input"

        # Check buttons by object name or tooltip
        if isinstance(widget, (QPushButton, QToolButton)):
            if "auto" in obj_name:
                return "auto_button"
            elif "reset" in obj_name:
                return "reset_button"
            elif "refresh" in obj_name:
                return "refresh_button"
            elif "browse" in obj_name:
                return "browse_button"

            # Check tooltip as fallback
            tooltip = widget.toolTip().lower()
            if "auto" in tooltip:
                return "auto_button"
            elif "reset" in tooltip:
                return "reset_button"
            elif "refresh" in tooltip:
                return "refresh_button"

        return None
```

### Usage Example

```python
from tests.helpers.widget_discovery import WidgetDiscovery

def test_all_widget_groups_in_capture_plugin(datalens_app):
    """Test all widget groups in the capture plugin systematically."""
    from datalens.plugins.capture.ui.workspace import WorkspaceWidget

    # Create the capture plugin workspace
    workspace = WorkspaceWidget(theme=datalens_app.app_theme, parent=None)
    workspace.show()
    QTest.qWait(100)

    try:
        # Discover all widget groups
        groups = WidgetDiscovery.find_groups_in_panel(workspace)

        print(f"\n✓ Discovered {len(groups)} widget groups")

        for group in groups:
            print(f"\n{group.section} > {group.control}:")
            for widget_type, widget in group.widgets.items():
                print(f"  - {widget_type}: {widget.__class__.__name__}")

            # Test this group
            test_widget_group_interactions(group)

    finally:
        workspace.close()
        workspace.deleteLater()

def test_widget_group_interactions(group: WidgetGroup):
    """Test all interactions within a widget group."""
    # Test slider + auto button
    if "slider" in group.widgets and "auto_button" in group.widgets:
        test_slider_auto_interaction(
            group.widgets["slider"],
            group.widgets["auto_button"]
        )

    # Test dropdown + refresh
    if "dropdown" in group.widgets and "refresh_button" in group.widgets:
        test_dropdown_refresh_interaction(
            group.widgets["dropdown"],
            group.widgets["refresh_button"]
        )

    # Test input + browse
    if "input" in group.widgets and "browse_button" in group.widgets:
        test_input_browse_interaction(
            group.widgets["input"],
            group.widgets["browse_button"]
        )
```

---

## Level 2: Metadata Annotations

### Strategy

Add **optional metadata** to widgets for explicit grouping without changing core architecture.

```python
# In plugin code (e.g., capture/ui/webcam_controls.py)

# Create the slider
exposure_slider = DatalensSliderOption(...)

# Create the auto button
auto_button = create_icon_button(...)

# Create the composite row
row = QWidget()
row_layout = QHBoxLayout(row)
row_layout.addWidget(exposure_slider)
row_layout.addWidget(auto_button)

# ADD METADATA (new)
row.setProperty("widget_group_id", "rgb_exposure")
row.setProperty("widget_group_role", "container")
exposure_slider.setProperty("widget_group_role", "primary")
auto_button.setProperty("widget_group_role", "toggle")

# Register the group (new helper)
from datalens.ui.testing import register_widget_group
register_widget_group(
    group_id="rgb_exposure",
    widgets={
        "slider": exposure_slider,
        "auto_button": auto_button,
    },
    interactions=[
        ("auto_button", "toggle", "slider", "enable/disable"),
    ]
)
```

### Discovery with Metadata

```python
def find_widget_groups_with_metadata(panel: QWidget) -> list[WidgetGroup]:
    """Find groups using Qt properties."""
    groups_by_id = {}

    # Find all widgets with group metadata
    for widget in panel.findChildren(QWidget):
        group_id = widget.property("widget_group_id")
        if group_id:
            role = widget.property("widget_group_role")
            if group_id not in groups_by_id:
                groups_by_id[group_id] = {}
            groups_by_id[group_id][role] = widget

    return [
        WidgetGroup(
            section="",  # Could add section property
            control=group_id,
            widgets=widgets,
            layout=None
        )
        for group_id, widgets in groups_by_id.items()
    ]
```

---

## Level 3: Declarative UI Schema (Future)

### Strategy

Extend manifest.json to declare UI structure and widget groups.

```json
// manifest.json
{
  "ui_schema": {
    "workspace": {
      "sections": [
        {
          "id": "rgb_settings",
          "title": "RGB Settings",
          "groups": [
            {
              "id": "exposure",
              "label": "Exposure",
              "widgets": [
                {
                  "type": "slider",
                  "id": "exposure_slider",
                  "range": [-13, 0],
                  "default": -6,
                  "shortcuts": ["Ctrl+E"]
                },
                {
                  "type": "auto_button",
                  "id": "exposure_auto",
                  "toggles": "exposure_slider",
                  "shortcuts": ["Ctrl+Shift+E"]
                }
              ]
            },
            {
              "id": "focus",
              "label": "Focus",
              "widgets": [
                {
                  "type": "slider",
                  "id": "focus_slider"
                },
                {
                  "type": "auto_button",
                  "id": "focus_auto"
                }
              ]
            }
          ]
        }
      ]
    }
  }
}
```

### Benefits

- **Automatic UI generation** from schema
- **Built-in test generation** for all groups
- **Documentation generation** for plugin UI
- **Accessibility metadata** (ARIA labels, etc.)

---

## Testing Strategy: Systematic Approach

### 1. Discovery Phase

```python
def test_discover_all_plugin_widgets(plugin_id: str):
    """Discover and catalog all widgets in a plugin."""
    workspace = create_plugin_workspace(plugin_id)

    # Try all discovery methods
    groups_convention = WidgetDiscovery.find_groups_in_panel(workspace)
    groups_metadata = find_widget_groups_with_metadata(workspace)

    # Merge results
    all_groups = merge_discovered_groups(groups_convention, groups_metadata)

    # Generate report
    print(f"\n📊 Widget Discovery Report: {plugin_id}")
    print(f"Groups found: {len(all_groups)}")
    for group in all_groups:
        print(f"\n  {group.section} > {group.control}")
        for role, widget in group.widgets.items():
            print(f"    - {role}: {widget.__class__.__name__}")
```

### 2. Interaction Testing

```python
def test_widget_group_interactions(group: WidgetGroup):
    """Test all standard interactions for a widget group."""

    # Pattern: Slider + Auto Button
    if "slider" in group.widgets and "auto_button" in group.widgets:
        slider = group.widgets["slider"]
        auto_btn = group.widgets["auto_button"]

        # Test: Auto button toggles slider
        QTest.mouseClick(auto_btn, Qt.LeftButton)
        QTest.qWait(50)
        assert not slider.isEnabled(), "Slider should be disabled when auto is on"

        QTest.mouseClick(auto_btn, Qt.LeftButton)
        QTest.qWait(50)
        assert slider.isEnabled(), "Slider should be enabled when auto is off"

    # Pattern: Slider + Reset Button
    if "slider" in group.widgets and "reset_button" in group.widgets:
        slider = group.widgets["slider"]
        reset_btn = group.widgets["reset_button"]

        # Change value
        original_value = slider.value()
        slider.setValue(slider.maximum())
        QTest.qWait(50)

        # Reset
        QTest.mouseClick(reset_btn, Qt.LeftButton)
        QTest.qWait(50)
        assert slider.value() == original_value, "Reset should restore default"

    # Pattern: Dropdown + Refresh
    if "dropdown" in group.widgets and "refresh_button" in group.widgets:
        dropdown = group.widgets["dropdown"]
        refresh_btn = group.widgets["refresh_button"]

        # Refresh should reload options
        original_count = dropdown.count()
        QTest.mouseClick(refresh_btn, Qt.LeftButton)
        QTest.qWait(100)
        # Count may change if devices added/removed
```

### 3. Keyboard Shortcut Testing

```python
def test_widget_group_shortcuts(group: WidgetGroup, app_context):
    """Test keyboard shortcuts for a widget group."""

    for widget_type, widget in group.widgets.items():
        # Try to find shortcut via object name pattern
        obj_name = widget.objectName()

        # Extract command_id from object name
        # e.g., "Capture_RGB_Exposure_Auto" -> "rgb_exposure_auto"
        command_id = extract_command_id(obj_name)

        if command_id:
            # Query the shortcut
            chord = app_context.shortcuts.get_effective_command_chord(
                plugin_id=extract_plugin_id(obj_name),
                command_id=command_id
            )

            if chord:
                # Simulate the shortcut
                modifiers, key = parse_chord(chord)
                QTest.keyClick(widget, key, modifiers)
                QTest.qWait(50)

                # Verify action happened
                verify_widget_action(widget, widget_type)
```

---

## Recommended Implementation Plan

### Phase 1: Quick Wins (Week 1)
1. ✅ Implement `WidgetDiscovery` helper class
2. ✅ Add convention-based discovery for common patterns
3. ✅ Create example tests for capture plugin widget groups

### Phase 2: Add Metadata (Week 2-3)
1. Add `setProperty("widget_group_*")` to key widgets in capture plugin
2. Update discovery to use metadata where available
3. Document metadata conventions

### Phase 3: Systematic Testing (Week 4)
1. Create parameterized tests that run on all discovered groups
2. Add shortcut verification for all interactive widgets
3. Generate widget inventory report

### Phase 4: Schema Extension (Future)
1. Design UI schema extension for manifest.json
2. Implement schema-based UI generation
3. Auto-generate tests from schema

---

## Next Steps

Would you like me to:
1. **Implement Level 1** (WidgetDiscovery helper class)?
2. **Create example tests** for the capture plugin?
3. **Design the metadata system** (Level 2)?
4. **Prototype the UI schema** (Level 3)?

Choose one or more, and I'll build it out!
