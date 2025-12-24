# Plugin Widget Group Testing Guide

Comprehensive guide for testing widget groups across plugins with automatic discovery and verification.

## Quick Start

### Test a Single Plugin

```bash
# Test the capture plugin
pytest tests/integration/plugins/test_03_plugin_widget_groups.py --plugin=capture

# Test the widget_test plugin
pytest tests/integration/plugins/test_03_plugin_widget_groups.py --plugin=widget_test
```

### Test Multiple Plugins

```bash
# Test both capture and widget_test plugins
pytest tests/integration/plugins/test_03_plugin_widget_groups.py --plugin=capture --plugin=widget_test
```

### Test All Available Plugins

```bash
# Test all plugins in the project
pytest tests/integration/plugins/test_03_plugin_widget_groups.py --test-all-plugins
```

### Generate Widget Inventory

```bash
# Generate detailed widget inventory report
pytest tests/integration/plugins/test_03_plugin_widget_groups.py --plugin=capture --generate-inventory -v
```

---

## Command-Line Options

### `--plugin=PLUGIN_ID`

Test a specific plugin by ID. Can be specified multiple times.

```bash
# Single plugin
pytest ... --plugin=capture

# Multiple plugins
pytest ... --plugin=capture --plugin=widget_test --plugin=another_plugin
```

**Available plugin IDs:**
- `capture` - Capture plugin (webcam/RealSense)
- `widget_test` - Widget test plugin (UI examples)

### `--test-all-plugins`

Test all available plugins automatically.

```bash
pytest tests/integration/plugins/test_03_plugin_widget_groups.py --test-all-plugins
```

This discovers and tests all plugins in the registry without needing to specify them individually.

### `--generate-inventory`

Generate a detailed widget inventory report showing all discovered widgets, their types, and properties.

```bash
pytest tests/integration/plugins/test_03_plugin_widget_groups.py --plugin=capture --generate-inventory -v
```

Output includes:
- Section names (e.g., "RGB Settings", "Device")
- Control names (e.g., "Exposure", "Focus")
- Widget roles (e.g., "slider", "auto_button", "reset_button")
- Widget types (e.g., "DatalensSliderOption", "QPushButton")
- Object names for test identification
- Enabled/visible state

---

## What Gets Tested

### Automatic Widget Discovery

The test system automatically discovers:

1. **QGroupBox sections** (e.g., "RGB Settings", "Device", "Save")
2. **QFormLayout rows** (label-widget pairs)
3. **Composite widgets** (slider + buttons, dropdown + refresh, etc.)
4. **Widget roles** (slider, auto_button, reset_button, dropdown, etc.)

### Standard Interaction Patterns

For each discovered widget group, the system tests:

#### Slider + Auto Button
- Auto button is checkable
- Clicking auto toggles its state
- State changes are persistent

#### Slider + Reset Button
- Reset button is clickable
- Reset button is enabled when it should be

#### Dropdown + Refresh Button
- Refresh button is enabled
- Clicking refresh doesn't crash
- Dropdown remains functional after refresh

#### Input + Browse Button
- Browse button is visible
- Browse button is clickable

---

## Test Modes

### Mode 1: Systematic Testing (Default)

```bash
pytest tests/integration/plugins/test_03_plugin_widget_groups.py --plugin=capture
```

Tests all discovered widget groups systematically:
- Discovers all groups
- Tests each group's interactions
- Reports pass/fail for each group
- Provides summary statistics

**Output:**
```
==================================================
🧪 Testing widget groups for plugins: capture
==================================================

✓ Enabled plugins for testing: capture

──────────────────────────────────────────────────
Testing plugin: capture
──────────────────────────────────────────────────

✓ Discovered 15 widget groups in capture

✓ Plugin capture: 15 passed, 0 failed

==================================================
📊 Test Summary
==================================================

capture             :  15 passed,   0 failed,  15 total
──────────────────────────────────────────────────
TOTAL               :  15 passed,   0 failed,  15 total
==================================================
```

### Mode 2: Parameterized Testing

```bash
# Test individual plugins in isolation
pytest tests/integration/plugins/test_03_plugin_widget_groups.py::test_individual_plugin_widgets[capture]
pytest tests/integration/plugins/test_03_plugin_widget_groups.py::test_individual_plugin_widgets[widget_test]
```

Runs each plugin as a separate test case:
- Useful for isolating failures
- Better for CI/CD pipelines
- Provides individual test results per plugin

### Mode 3: Inventory Generation

```bash
pytest tests/integration/plugins/test_03_plugin_widget_groups.py --plugin=capture --generate-inventory -v
```

Generates comprehensive widget inventory:
- Section → Control → Widget hierarchy
- Widget types and object names
- Enabled/visible state
- Useful for documentation and coverage analysis

**Output:**
```
======================================================================
📋 Widget Inventory Report
======================================================================

──────────────────────────────────────────────────
Plugin: capture
Total Groups: 15
──────────────────────────────────────────────────

  Section: Device
    ├─ Camera
    │  └─ dropdown       : QComboBox                 [CameraDropdown]
    │  └─ refresh_button : QPushButton               [RefreshButton]
    ├─ Resolution
    │  └─ dropdown       : QComboBox                 [ResolutionDropdown]

  Section: RGB Settings
    ├─ Exposure
    │  └─ slider         : DatalensSliderOption      [ExposureSlider]
    │  └─ auto_button    : QToolButton               [CaptureAutoOptionButton]
    ├─ Focus
    │  └─ slider         : DatalensSliderOption      [FocusSlider]
    │  └─ auto_button    : QToolButton               [CaptureAutoOptionButton]
    ...
```

---

## How It Works

### 1. Plugin Enablement

The test system automatically enables the specified plugins before testing:

```python
# Save original state
original_enabled = settings.enabled_plugins

# Enable test plugins
new_enabled = original_enabled | {PluginId("capture"), PluginId("widget_test")}

# Run tests...

# Restore original state
settings.enabled_plugins = original_enabled
```

This ensures:
- Plugins are available for testing
- Original user state is preserved
- Tests don't interfere with each other

### 2. Widget Discovery

Uses convention-based discovery (see [WIDGET_GROUP_TESTING.md](WIDGET_GROUP_TESTING.md)):

```python
groups = WidgetDiscovery.find_groups_in_panel(workspace)
# Returns: [
#   WidgetGroup(section="RGB Settings", control="Exposure",
#               widgets={"slider": ..., "auto_button": ...}),
#   ...
# ]
```

### 3. Pattern Testing

For each group, tests the appropriate pattern:

```python
if "slider" in group.widgets and "auto_button" in group.widgets:
    # Test slider + auto interaction
    test_slider_auto_pattern(...)
```

### 4. Reporting

Generates comprehensive reports:
- Per-plugin statistics
- Overall pass/fail summary
- Detailed widget inventory (if requested)

---

## Adding Support for New Plugins

### Step 1: Add Plugin to Workspace Mapping

Edit `test_03_plugin_widget_groups.py`:

```python
workspace_classes = {
    "widget_test": "datalens.plugins.widget_test.ui.workspace.WorkspaceWidget",
    "capture": "datalens.plugins.capture.ui.workspace.WorkspaceWidget",
    "my_new_plugin": "datalens.plugins.my_new_plugin.ui.workspace.WorkspaceWidget",  # Add this
}
```

### Step 2: Add Plugin-Specific Parameters (if needed)

```python
# Add plugin-specific parameters
if plugin_id == "widget_test":
    kwargs["shortcut_button_bindings"] = None
elif plugin_id == "my_new_plugin":
    kwargs["custom_param"] = some_value
```

### Step 3: Test It

```bash
pytest tests/integration/plugins/test_03_plugin_widget_groups.py --plugin=my_new_plugin
```

That's it! The system will automatically:
- Enable the plugin
- Create the workspace
- Discover all widget groups
- Test standard patterns
- Generate reports

---

## Best Practices

### 1. Use Object Names

Set object names on important widgets for better test identification:

```python
exposure_slider = DatalensSliderOption(...)
exposure_slider.setObjectName("ExposureSlider")

auto_button = QPushButton("Auto")
auto_button.setObjectName("ExposureAutoButton")
```

Benefits:
- Easier to identify widgets in test output
- Better error messages
- Supports future shortcut testing

### 2. Follow Widget Patterns

Use standard widget combinations:
- **Slider + Auto**: `DatalensSliderOption` + checkable `QPushButton`
- **Slider + Reset**: Built into `DatalensSliderOption`
- **Dropdown + Refresh**: `QComboBox` + `QPushButton`
- **Input + Browse**: `QLineEdit` + `QPushButton`

The test system recognizes these patterns automatically.

### 3. Use Consistent Tooltips

The discovery system uses tooltips as fallback for widget categorization:

```python
auto_button.setToolTip("Auto")  # Will be categorized as "auto_button"
reset_button.setToolTip("Reset")  # Will be categorized as "reset_button"
```

### 4. Organize with QGroupBox

Group related controls in `QGroupBox`:

```python
rgb_group = QGroupBox("RGB Settings", parent)
rgb_layout = QFormLayout(rgb_group)
rgb_layout.addRow("Exposure", exposure_widget)
rgb_layout.addRow("Focus", focus_widget)
```

Benefits:
- Clear section organization
- Automatic discovery by section
- Better user experience

---

## Troubleshooting

### Test Can't Find Plugin Workspace

**Error:** `Skipping {plugin_id}: no workspace available`

**Solution:** Add plugin to `workspace_classes` mapping in `test_03_plugin_widget_groups.py`

### No Widget Groups Discovered

**Possible causes:**
1. Plugin doesn't use `QGroupBox` + `QFormLayout` structure
2. Widgets don't follow standard patterns
3. Workspace didn't initialize properly

**Solution:**
- Check plugin UI structure
- Verify workspace shows correctly when run manually
- Add debug prints to see what's being discovered

### Widget Group Test Failures

**Error:** `Auto button should toggle state for {control}`

**Possible causes:**
1. Button isn't checkable (`setCheckable(True)` missing)
2. Button state doesn't persist
3. Button is disabled

**Solution:**
- Verify button is created with `setCheckable(True)`
- Check button enable/disable logic
- Review button signal connections

### Plugin Not Enabled

**Error:** Plugin widgets don't load or appear

**Solution:**
- The test system should automatically enable plugins
- If not working, check that plugin ID matches exactly
- Verify plugin is in the discovery registry

---

## Examples

### Test Capture Plugin with Inventory

```bash
cd datalens/tests
pytest integration/plugins/test_03_plugin_widget_groups.py --plugin=capture --generate-inventory -v
```

### Test All Plugins Quickly

```bash
pytest integration/plugins/test_03_plugin_widget_groups.py --test-all-plugins
```

### Test Specific Plugin in CI

```bash
# In your CI pipeline
pytest integration/plugins/test_03_plugin_widget_groups.py::test_individual_plugin_widgets[capture] -v
```

### Debug Widget Discovery

```bash
# Run with verbose output and inventory
pytest integration/plugins/test_03_plugin_widget_groups.py --plugin=capture --generate-inventory -vv
```

---

## Related Documentation

- [WIDGET_GROUP_TESTING.md](WIDGET_GROUP_TESTING.md) - Widget discovery system architecture
- [KEYBOARD_SHORTCUTS_TESTING.md](KEYBOARD_SHORTCUTS_TESTING.md) - Keyboard shortcut testing
- [README.md](README.md) - General testing guide
- [test_widget_group_discovery.py](examples/test_widget_group_discovery.py) - Discovery examples

---

## Future Enhancements

### Planned Features

1. **Automatic Shortcut Testing**
   - Discover shortcuts from object names
   - Test keyboard activation of widgets
   - Verify shortcut tooltips

2. **Widget State Verification**
   - Check widget enables/disables correctly
   - Verify value ranges and defaults
   - Test state persistence

3. **Cross-Plugin Testing**
   - Test plugin interactions
   - Verify shared resources
   - Check event communication

4. **Performance Testing**
   - Widget creation time
   - Interaction responsiveness
   - Memory usage

5. **Accessibility Testing**
   - ARIA labels
   - Keyboard navigation
   - Screen reader compatibility
