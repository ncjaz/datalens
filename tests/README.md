# DataLens Testing Suite

Full-application integration tests for DataLens V2.

## Quick Start

**IMPORTANT: Activate the conda datalens environment first!**

```bash
# Activate the conda environment
conda activate datalens

# Run all tests
python run_tests.py

# Run tests in a category
python run_tests.py integration/ui/              # UI tests only
python run_tests.py integration/workflows/       # Workflow tests only
python run_tests.py examples/                    # Examples only

# Run specific test file
python run_tests.py integration/ui/test_welcome_screen.py

# Run specific test
python run_tests.py integration/ui/test_welcome_screen.py::test_welcome_screen_enable_all_plugins

# Run with options
python run_tests.py -v                          # Verbose output
python run_tests.py --keep-app-open             # Keep app open after tests
python run_tests.py -vv --keep-app-open         # Both options
```

📖 **See [STRUCTURE.md](STRUCTURE.md) for complete directory organization and conventions**

---

## Table of Contents

1. [Testing Philosophy](#testing-philosophy)
2. [Available Test Helpers](#available-test-helpers)
3. [UI Interactions Guide](#ui-interactions-guide)
4. [Testing with Events and State](#testing-with-events-and-state)
5. [Project Testing](#project-testing)
6. [Plugin Navigation](#plugin-navigation)
7. [Test Ordering and Dependencies](#test-ordering-and-dependencies)
8. [Adding Your Tests](#adding-your-tests)
9. [Complete Examples](#complete-examples)
10. [Debugging](#debugging)

---

## Testing Philosophy

**All tests run with the FULL DataLens application loaded.**

This is not traditional unit testing. These are full-application integration tests that:
- ✅ Load the complete application with all services
- ✅ Interact through the UI (clicks, keyboard, menus)
- ✅ Test real user workflows end-to-end
- ✅ Run in isolated environments (user data is never touched)
- ✅ Use DataLens event system and state management for verification

### Testing Mode Isolation

Tests run in **isolated testing mode**:
- ✅ Separate settings.json in temporary directory
- ✅ Test projects in temporary directories
- ✅ Automatic cleanup after tests
- ✅ User's actual data is NEVER modified
- ✅ Set `DATALENS_KEEP_TEST_DATA=1` to preserve test data for debugging

---

## Available Test Helpers

All helpers are in `helpers/workflow_helpers.py`. Import them like:

```python
from helpers.workflow_helpers import (
    WelcomeScreenHelper,
    MainWindowHelper,
    ProjectHelper,
    EventWatcher,
    StateWatcher,
    wait_for_condition,
)
```

### 1. **WelcomeScreenHelper**

Interact with the welcome screen:

```python
helper = WelcomeScreenHelper(welcome_window)

# Find buttons
quit_btn = helper.find_quit_button()
continue_btn = helper.find_continue_button()

# Plugin management
helper.enable_plugins([0, 2])        # Enable plugins by index
helper.enable_all_plugins()          # Enable all
helper.disable_all_plugins()         # Disable all
helper.verify_plugin_count(3)        # Assert exact count

# Get enabled plugins
enabled = helper.get_enabled_plugins()  # Returns frozenset of plugin IDs

# Click buttons
helper.click_quit()      # Note: Actually closes app
helper.click_continue()  # Note: Loads main window
```

### 2. **MainWindowHelper**

Interact with the main window and File menu:

```python
helper = MainWindowHelper(main_window)

# File menu actions
helper.file_quit()                              # File → Quit
helper.file_restart()                           # File → Restart
helper.file_new_project()                       # File → New Project
helper.file_open_project()                      # File → Open Project
helper.file_close_project()                     # File → Close Project
helper.file_open_recent_project(project_path)   # File → Recent Projects → [project]

# Navigate to plugins (TODO: Implementation needed)
helper.switch_to_plugin(plugin_index)           # Switch to plugin workspace
helper.verify_plugin_accessible(plugin_index)   # Verify plugin loads without error
```

### 3. **ProjectHelper**

Create and manage test projects:

```python
# Create a test project
project_path = test_project_root / "my_test_project"
ProjectHelper.create_test_project(project_path, "My Test Project")

# This creates:
# - project_path/ directory
# - project_path/project.json with basic metadata

# Delete test project
ProjectHelper.delete_test_project(project_path)
```

### 4. **EventWatcher**

Monitor DataLens events to verify actions occurred:

```python
from datalens.core.context import get_app_context

app_ctx = get_app_context()
event_watcher = EventWatcher(app_ctx)

# Watch for events
event_watcher.watch("capture.streaming_started")
event_watcher.watch("capture.frame_received")

# Perform action
click_start_button()

# Verify events received
event_watcher.assert_received("capture.streaming_started", timeout_ms=3000)
event_watcher.assert_received("capture.frame_received", timeout_ms=2000)

# Get event data
event_data = event_watcher.get_event_data("capture.streaming_started")

# Check if received (non-blocking)
if event_watcher.was_received("capture.frame_received"):
    print("Frame received!")

# IMPORTANT: Always cleanup!
try:
    # Test code
    pass
finally:
    event_watcher.cleanup()
```

### 5. **StateWatcher**

Monitor DataLens state changes:

```python
from datalens.core.context import get_app_context

app_ctx = get_app_context()
state_watcher = StateWatcher(app_ctx)

# Get current state
state = state_watcher.get_snapshot()
print(f"Is streaming: {state.capture.is_streaming}")

# Wait for state condition
success = state_watcher.wait_for_state(
    lambda s: s.capture.is_streaming,
    timeout_ms=3000
)

# Assert state condition
state_watcher.assert_state(
    lambda s: s.capture.frame_count > 0,
    timeout_ms=2000,
    message="Should have received frames"
)

# Check multiple conditions
state_watcher.assert_state(
    lambda s: s.capture.is_streaming and s.capture.frame_count > 10,
    timeout_ms=5000
)
```

### 6. **wait_for_condition()**

Generic polling utility for any condition:

```python
# Wait for widget visibility
success = wait_for_condition(
    lambda: my_widget.isVisible(),
    timeout_ms=2000,
    check_interval_ms=50  # Check every 50ms
)
assert success, "Widget should become visible"

# Wait for property change
success = wait_for_condition(
    lambda: button.text() == "Stop",
    timeout_ms=1000
)

# Wait for value to change
initial_count = get_frame_count()
success = wait_for_condition(
    lambda: get_frame_count() > initial_count,
    timeout_ms=3000
)
```

---

## UI Interactions Guide

### Basic Button Clicks

```python
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

# Find button by object name (recommended)
button = window.findChild(QPushButton, "start_stream_button")
assert button is not None, "Button should exist"

# Find button by text
for btn in window.findChildren(QPushButton):
    if btn.text() == "Start Stream":
        button = btn
        break

# Click the button
QTest.mouseClick(button, Qt.LeftButton)
QTest.qWait(100)  # Wait for action to process
```

### Testing Video Streaming (Example)

```python
@pytest.mark.ui
def test_camera_streaming(datalens_app):
    """Test that clicking Start Stream actually starts streaming."""
    from datalens.core.context import get_app_context

    app_ctx = get_app_context()

    # Setup watchers
    event_watcher = EventWatcher(app_ctx)
    event_watcher.watch("capture.streaming_started")
    event_watcher.watch("capture.frame_received")

    state_watcher = StateWatcher(app_ctx)

    try:
        # Find and click start button
        start_button = find_start_stream_button()
        QTest.mouseClick(start_button, Qt.LeftButton)

        # Verify event emitted
        event_watcher.assert_received("capture.streaming_started", timeout_ms=3000)
        print("✓ Streaming started event received")

        # Verify state changed
        state_watcher.assert_state(
            lambda s: s.capture.is_streaming,
            timeout_ms=1000,
            message="State should indicate streaming"
        )
        print("✓ State confirms streaming")

        # Verify frames arriving
        event_watcher.assert_received("capture.frame_received", timeout_ms=2000)
        print("✓ Frame data received")

        # Verify frame count increasing
        initial_count = state_watcher.get_snapshot().capture.frame_count
        QTest.qWait(500)
        current_count = state_watcher.get_snapshot().capture.frame_count
        assert current_count > initial_count, "Frame count should increase"
        print(f"✓ Frames streaming ({current_count} frames)")

        # Verify visual indicator (if applicable)
        indicator = find_stream_indicator()
        if indicator:
            # Check color changed to green
            success = wait_for_condition(
                lambda: "green" in indicator.styleSheet().lower(),
                timeout_ms=1000
            )
            assert success, "Indicator should turn green"
            print("✓ Visual indicator shows streaming (green)")

        # Stop streaming
        QTest.mouseClick(start_button, Qt.LeftButton)  # Now shows "Stop"

        # Verify stopped
        state_watcher.assert_state(
            lambda s: not s.capture.is_streaming,
            timeout_ms=2000
        )
        print("✓ Streaming stopped")

    finally:
        event_watcher.cleanup()
```

### Keyboard Input

```python
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

# Type text
QTest.keyClicks(text_field, "Hello World")

# Press specific keys
QTest.keyPress(widget, Qt.Key_Enter)
QTest.keyPress(widget, Qt.Key_Escape)
QTest.keyPress(widget, Qt.Key_Tab)

# Key combinations
QTest.keyClick(widget, Qt.Key_S, Qt.ControlModifier)  # Ctrl+S
QTest.keyClick(widget, Qt.Key_A, Qt.ControlModifier)  # Ctrl+A
```

### Finding Widgets

```python
from PySide6.QtWidgets import QPushButton, QLabel, QLineEdit

# By object name (recommended - set with setObjectName())
button = window.findChild(QPushButton, "my_button")

# By type (first match)
label = window.findChild(QLabel)

# All of type
all_buttons = window.findChildren(QPushButton)

# Filter by property
for btn in window.findChildren(QPushButton):
    if btn.text() == "Start":
        start_button = btn
        break

# Nested search
panel = window.findChild(QWidget, "control_panel")
button = panel.findChild(QPushButton, "start_button")
```

---

## Testing with Events and State

### Why Use Events and State?

**Don't just check UI - verify actual behavior!**

❌ **Bad**: Only check UI changed
```python
# Button text changed, but did streaming actually start?
assert button.text() == "Stop"
```

✅ **Good**: Check events, state, AND UI
```python
# Verify event was emitted
event_watcher.assert_received("capture.streaming_started")

# Verify state updated
assert state_watcher.get_snapshot().capture.is_streaming

# Verify UI reflects state
assert button.text() == "Stop"
```

### Available DataLens Events

Common events you can watch for:

```python
# Project lifecycle
"ProjectOpened"
"ProjectClosing"
"ProjectClosed"
"ActiveProjectChanged"

# Plugin lifecycle
"PluginEnabled"
"PluginDisabled"
"PluginsEnabledChanged"
"FocusedWorkspaceChanged"

# Capture plugin (example - replace with actual events)
"capture.streaming_started"
"capture.streaming_stopped"
"capture.frame_received"
"capture.error"
```

See `datalens/src/datalens/core/events.py` for all available events.

---

## Project Testing

### Creating Test Projects

```python
from pathlib import Path
from helpers.workflow_helpers import ProjectHelper

@pytest.mark.ui
def test_project_creation(test_project_root: Path):
    """Test project creation workflow."""
    project_path = test_project_root / "my_project"

    # Create test project
    ProjectHelper.create_test_project(project_path, "My Project")

    # Verify project structure
    assert project_path.exists(), "Project directory should exist"
    assert (project_path / "project.json").exists(), "project.json should exist"

    # Verify project.json content
    import json
    project_data = json.loads((project_path / "project.json").read_text())
    assert project_data["name"] == "My Project"
    assert "version" in project_data

    # Add more verification as needed
    # For example, check for other expected files:
    # assert (project_path / "annotations").exists()
    # assert (project_path / "media").exists()

    # Cleanup
    ProjectHelper.delete_test_project(project_path)

    # Verify deletion
    assert not project_path.exists(), "Project should be deleted"
```

### Verifying Project Files

When creating projects through UI, always verify the expected files:

```python
@pytest.mark.ui
def test_new_project_creates_correct_structure(datalens_app, test_project_root: Path):
    """Test that File → New Project creates correct structure."""
    from helpers.workflow_helpers import MainWindowHelper

    # Assume main window is open
    main_window = get_main_window()
    helper = MainWindowHelper(main_window)

    # Trigger File → New Project
    helper.file_new_project()

    # TODO: Fill out project creation dialog
    # (This depends on your actual project creation UI)

    # Wait for project to be created
    QTest.qWait(500)

    # Get project path (from app state or dialog)
    project_path = get_current_project_path()

    # Verify required files exist
    assert project_path.exists(), "Project directory should exist"
    assert (project_path / "project.json").exists(), "project.json required"
    assert (project_path / ".datalens").exists(), ".datalens metadata dir required"

    # Verify project.json has required fields
    import json
    project_json = json.loads((project_path / "project.json").read_text())

    required_fields = ["name", "version", "created"]
    for field in required_fields:
        assert field in project_json, f"project.json must have '{field}' field"

    # Verify directory structure
    assert (project_path / "annotations").exists(), "annotations/ dir required"
    assert (project_path / "media").exists(), "media/ dir required"
    assert (project_path / "exports").exists(), "exports/ dir required"

    # Verify permissions (files are writable)
    assert os.access(project_path / "project.json", os.W_OK), "project.json should be writable"

    print(f"✓ Project created with correct structure: {project_path}")
```

---

## Plugin Navigation

### Switching Between Plugins in UI

```python
@pytest.mark.ui
def test_switch_between_plugins(datalens_app):
    """Test navigating between different plugin workspaces."""
    from helpers.workflow_helpers import MainWindowHelper

    main_window = get_main_window()
    helper = MainWindowHelper(main_window)

    # TODO: Implement in MainWindowHelper based on actual UI
    # For now, this shows the intended API:

    # Switch to first plugin (e.g., Capture)
    helper.switch_to_plugin(0)
    QTest.qWait(200)

    # Verify plugin is active
    helper.verify_plugin_accessible(0)

    # Switch to second plugin (e.g., Annotation)
    helper.switch_to_plugin(1)
    QTest.qWait(200)

    # Verify plugin is active
    helper.verify_plugin_accessible(1)

    # Switch back to first
    helper.switch_to_plugin(0)
    QTest.qWait(200)

    print("✓ Successfully navigated between plugins")
```

### Testing All Plugin Combinations

Test that all plugins work together:

```python
@pytest.mark.ui
def test_all_plugin_combinations_accessible(datalens_app):
    """Test that all plugin combinations can be switched without errors."""
    import itertools
    from helpers.workflow_helpers import MainWindowHelper

    plugins = get_enabled_plugins()
    plugin_count = len(plugins)

    main_window = get_main_window()
    helper = MainWindowHelper(main_window)

    # Test all pairs of plugins
    for i, j in itertools.combinations(range(plugin_count), 2):
        print(f"Testing switch: {plugins[i].name} → {plugins[j].name}")

        helper.switch_to_plugin(i)
        QTest.qWait(100)
        helper.verify_plugin_accessible(i)

        helper.switch_to_plugin(j)
        QTest.qWait(100)
        helper.verify_plugin_accessible(j)

        print(f"  ✓ Switch successful")

    print(f"✓ Tested {len(list(itertools.combinations(range(plugin_count), 2)))} plugin switches")
```

---

## Test Ordering and Dependencies

### Test Execution Order

Tests run in **alphabetical order by default** within each file.

```python
# These run in alphabetical order:
def test_aaa_first():
    pass

def test_bbb_second():
    pass

def test_zzz_last():
    pass
```

### Making Tests Run in Specific Order

#### Option 1: Use Descriptive Names (Recommended)

```python
# integration/workflows/test_capture_workflow.py

def test_01_start_streaming():
    """Step 1: Start streaming."""
    pass

def test_02_verify_frames():
    """Step 2: Verify frames are received."""
    pass

def test_03_stop_streaming():
    """Step 3: Stop streaming."""
    pass
```

#### Option 2: Use pytest-order Plugin

```bash
pip install pytest-order
```

```python
import pytest

@pytest.mark.order(1)
def test_this_runs_first():
    pass

@pytest.mark.order(2)
def test_this_runs_second():
    pass

@pytest.mark.order(3)
def test_this_runs_last():
    pass
```

#### Option 3: Use Fixtures for Setup

```python
@pytest.fixture
def streaming_started(datalens_app):
    """Fixture that starts streaming - dependent tests can use this."""
    start_streaming()
    yield
    stop_streaming()

def test_needs_streaming_first(streaming_started):
    """This test requires streaming to be started."""
    # streaming_started fixture runs first
    verify_streaming()
```

### Running Tests in Specific Files First

Control file execution order using file names:

```
integration/workflows/
├── test_01_app_startup.py         # Runs first
├── test_02_plugin_loading.py      # Runs second
├── test_03_project_creation.py    # Runs third
└── test_99_cleanup.py             # Runs last
```

Or run manually in order:

```bash
python run_tests.py \
    integration/workflows/test_app_startup.py \
    integration/workflows/test_plugin_loading.py \
    integration/workflows/test_project_creation.py
```

### Running Single Test with Dependencies

```bash
# Run a specific test (but note: fixtures still run)
python run_tests.py integration/workflows/test_capture.py::test_02_verify_frames

# If test depends on test_01_start_streaming having run,
# you may need to run both:
python run_tests.py integration/workflows/test_capture.py::test_01_start_streaming integration/workflows/test_capture.py::test_02_verify_frames
```

---

## Adding Your Tests

### Step 1: Choose Location

- **Testing a UI component?** → `integration/ui/test_your_component.py`
- **Testing an end-to-end workflow?** → `integration/workflows/test_your_workflow.py`
- **Creating an example/template?** → `examples/test_example_your_feature.py`

### Step 2: Create Test File

```python
# integration/workflows/test_my_feature.py
"""
Tests for My Feature.

This test suite covers:
- Feature setup
- Feature operation
- Feature cleanup
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from helpers.workflow_helpers import EventWatcher, StateWatcher, wait_for_condition

@pytest.mark.ui
def test_my_feature_basic(datalens_app):
    """Test basic my feature functionality."""
    # Test implementation
    pass

@pytest.mark.ui
def test_my_feature_advanced(datalens_app):
    """Test advanced my feature functionality."""
    # Test implementation
    pass
```

### Step 3: Import Helpers

```python
from helpers.workflow_helpers import (
    WelcomeScreenHelper,
    MainWindowHelper,
    ProjectHelper,
    EventWatcher,
    StateWatcher,
    wait_for_condition,
)
```

### Step 4: Write Test

```python
@pytest.mark.ui
def test_my_feature(datalens_app):
    """
    Test description explaining what this verifies.

    Steps:
    1. Setup test conditions
    2. Perform action
    3. Verify results
    """
    from datalens.core.context import get_app_context

    app_ctx = get_app_context()

    # Setup
    event_watcher = EventWatcher(app_ctx)
    event_watcher.watch("my_feature.started")

    try:
        # Perform action
        click_my_feature_button()

        # Verify
        event_watcher.assert_received("my_feature.started", timeout_ms=2000)
        print("✓ My feature test passed")

    finally:
        event_watcher.cleanup()
```

### Step 5: Run Your Test

```bash
# Run just your new test file
python run_tests.py integration/workflows/test_my_feature.py

# Run specific test
python run_tests.py integration/workflows/test_my_feature.py::test_my_feature_basic

# Run with verbose output
python run_tests.py integration/workflows/test_my_feature.py -vv
```

### Step 6: Verify Test is in Suite

```bash
# List all tests (your test should appear)
python run_tests.py --collect-only

# Run all tests to ensure your test runs
python run_tests.py
```

---

## Complete Examples

### Example 1: Simple Button Click Test

```python
@pytest.mark.ui
def test_preferences_button_opens_dialog(datalens_app):
    """Test that clicking Edit → Preferences opens the dialog."""
    from PySide6.QtWidgets import QApplication
    from datalens.ui.menus.edit.preferences import PreferencesDialog

    # Get main window
    main_window = get_main_window()

    # Trigger Edit → Preferences
    # (Implementation depends on your menu structure)
    trigger_preferences_menu()

    # Wait for dialog
    QTest.qWait(200)

    # Find dialog
    dialog = QApplication.activeWindow()
    assert dialog is not None, "Dialog should open"
    assert isinstance(dialog, PreferencesDialog), "Should be PreferencesDialog"
    assert dialog.isVisible(), "Dialog should be visible"

    # Cleanup
    dialog.close()
    dialog.deleteLater()

    print("✓ Preferences dialog opens correctly")
```

### Example 2: Complete Streaming Test

```python
@pytest.mark.ui
def test_complete_camera_streaming_workflow(datalens_app):
    """
    Complete test of camera streaming workflow.

    Tests:
    - Start button click
    - Events are emitted
    - State is updated
    - Frames are received
    - Visual indicator changes
    - Stop button click
    - Cleanup is correct
    """
    from datalens.core.context import get_app_context
    from helpers.workflow_helpers import EventWatcher, StateWatcher, wait_for_condition

    app_ctx = get_app_context()

    # Setup watchers
    event_watcher = EventWatcher(app_ctx)
    event_watcher.watch("capture.streaming_started")
    event_watcher.watch("capture.frame_received")
    event_watcher.watch("capture.streaming_stopped")

    state_watcher = StateWatcher(app_ctx)

    try:
        # Verify initial state
        initial_state = state_watcher.get_snapshot()
        assert not initial_state.capture.is_streaming, "Should not be streaming initially"
        print("✓ Initial state: not streaming")

        # Find UI elements
        start_button = find_widget_by_name("start_stream_button")
        stream_indicator = find_widget_by_name("stream_indicator")

        # Verify initial UI state
        assert start_button.text() == "Start", "Button should show Start"
        if stream_indicator:
            assert "red" in stream_indicator.styleSheet().lower(), "Indicator should be red"

        # Click start button
        print("Clicking Start Stream button...")
        QTest.mouseClick(start_button, Qt.LeftButton)

        # Verify streaming started event
        event_watcher.assert_received("capture.streaming_started", timeout_ms=3000)
        print("✓ streaming_started event received")

        # Verify state updated
        state_watcher.assert_state(
            lambda s: s.capture.is_streaming,
            timeout_ms=1000,
            message="State should indicate streaming"
        )
        print("✓ State confirms streaming")

        # Verify frame event
        event_watcher.assert_received("capture.frame_received", timeout_ms=2000)
        print("✓ Frame data received")

        # Verify frame count increases
        initial_count = state_watcher.get_snapshot().capture.frame_count
        QTest.qWait(500)
        current_count = state_watcher.get_snapshot().capture.frame_count
        assert current_count > initial_count, \
            f"Frame count should increase ({initial_count} → {current_count})"
        print(f"✓ Frames streaming ({current_count} frames)")

        # Verify UI updated
        success = wait_for_condition(
            lambda: start_button.text() == "Stop",
            timeout_ms=1000
        )
        assert success, "Button should show Stop"

        if stream_indicator:
            success = wait_for_condition(
                lambda: "green" in stream_indicator.styleSheet().lower(),
                timeout_ms=1000
            )
            assert success, "Indicator should turn green"
            print("✓ Visual indicator shows streaming (green)")

        # Stop streaming
        print("Clicking Stop Stream button...")
        QTest.mouseClick(start_button, Qt.LeftButton)

        # Verify stopped event
        event_watcher.assert_received("capture.streaming_stopped", timeout_ms=2000)
        print("✓ streaming_stopped event received")

        # Verify state updated
        state_watcher.assert_state(
            lambda s: not s.capture.is_streaming,
            timeout_ms=1000,
            message="State should indicate stopped"
        )
        print("✓ State confirms stopped")

        # Verify UI updated
        success = wait_for_condition(
            lambda: start_button.text() == "Start",
            timeout_ms=1000
        )
        assert success, "Button should show Start again"

        if stream_indicator:
            success = wait_for_condition(
                lambda: "red" in stream_indicator.styleSheet().lower(),
                timeout_ms=1000
            )
            assert success, "Indicator should turn red"
            print("✓ Visual indicator shows stopped (red)")

        print("\n✅ Complete streaming workflow test passed!")

    finally:
        event_watcher.cleanup()
```

### Example 3: Project Creation with Verification

```python
@pytest.mark.ui
def test_project_creation_complete(datalens_app, test_project_root: Path):
    """
    Test complete project creation workflow.

    Verifies:
    - UI interaction
    - Files are created correctly
    - Project appears in recent projects
    - Project can be loaded
    """
    from helpers.workflow_helpers import MainWindowHelper, ProjectHelper

    project_path = test_project_root / "complete_test_project"

    # Get main window
    main_window = get_main_window()
    helper = MainWindowHelper(main_window)

    try:
        # File → New Project
        print("Creating new project via File menu...")
        helper.file_new_project()
        QTest.qWait(200)

        # TODO: Fill out project creation dialog
        # (This depends on your actual UI)
        # fill_project_dialog(name="Complete Test Project", path=project_path)

        # Wait for project to be created
        success = wait_for_condition(
            lambda: project_path.exists(),
            timeout_ms=5000
        )
        assert success, f"Project directory should be created: {project_path}"
        print(f"✓ Project directory created: {project_path}")

        # Verify required files
        required_files = [
            "project.json",
            ".datalens/metadata.json",
        ]

        for file_path in required_files:
            full_path = project_path / file_path
            assert full_path.exists(), f"Required file missing: {file_path}"
            print(f"  ✓ {file_path} exists")

        # Verify required directories
        required_dirs = [
            "annotations",
            "media",
            "exports",
            ".datalens",
        ]

        for dir_path in required_dirs:
            full_path = project_path / dir_path
            assert full_path.exists(), f"Required directory missing: {dir_path}"
            assert full_path.is_dir(), f"Should be directory: {dir_path}"
            print(f"  ✓ {dir_path}/ exists")

        # Verify project.json content
        import json
        project_json = json.loads((project_path / "project.json").read_text())

        required_fields = {
            "name": str,
            "version": str,
            "created": str,
        }

        for field, expected_type in required_fields.items():
            assert field in project_json, f"project.json missing field: {field}"
            assert isinstance(project_json[field], expected_type), \
                f"project.json['{field}'] should be {expected_type.__name__}"
            print(f"  ✓ project.json has '{field}': {project_json[field]}")

        # Verify files are writable
        assert os.access(project_path / "project.json", os.W_OK), \
            "project.json should be writable"
        print("  ✓ Files are writable")

        # Verify project appears in app state
        from datalens.core.context import get_app_context
        app_ctx = get_app_context()

        # TODO: Verify project is in recent projects
        # recent_projects = app_ctx.get_recent_projects()
        # assert project_path in recent_projects

        print("\n✅ Project created with complete structure!")

    finally:
        # Cleanup
        if project_path.exists():
            ProjectHelper.delete_test_project(project_path)
            assert not project_path.exists(), "Project should be deleted"
            print("✓ Cleanup complete")
```

---

## Debugging

### Keep Test Data for Inspection

```bash
# Windows
set DATALENS_KEEP_TEST_DATA=1
python run_tests.py

# Linux/Mac
export DATALENS_KEEP_TEST_DATA=1
python run_tests.py

# Check where test data is stored
# (Printed in test output)
```

### Run Single Test with Full Output

```bash
python run_tests.py integration/workflows/test_my_feature.py::test_specific -vv
```

### Keep App Open After Tests

```bash
# App stays open so you can inspect UI state
python run_tests.py --keep-app-open

# Run specific test and keep open
python run_tests.py integration/workflows/test_streaming.py --keep-app-open
```

### Show Local Variables on Failure

```bash
python run_tests.py --showlocals
```

### Drop into Debugger on Failure

```bash
python run_tests.py --pdb
```

### pytest Commands

```bash
# Exit on first failure
python run_tests.py -x

# Rerun only failed tests
python run_tests.py --lf

# Run tests matching keyword
python run_tests.py -k "streaming"

# Show test durations
python run_tests.py --durations=10
```

---

## Common Patterns

### Pattern: Setup → Action → Verify → Cleanup

```python
@pytest.mark.ui
def test_my_feature(datalens_app):
    """Test template."""
    event_watcher = EventWatcher(get_app_context())
    event_watcher.watch("my_event")

    try:
        # Setup
        setup_test_conditions()

        # Action
        perform_action()

        # Verify
        event_watcher.assert_received("my_event")
        verify_state()
        verify_ui()

    finally:
        # Cleanup
        event_watcher.cleanup()
        cleanup_resources()
```

### Pattern: Verify Before and After

```python
# Before
initial_state = get_state()
assert initial_state.is_idle

# Action
perform_action()

# After
final_state = get_state()
assert final_state.is_active
assert final_state != initial_state
```

### Pattern: Wait for Multiple Conditions

```python
# All must be true
state_watcher.assert_state(
    lambda s: s.is_streaming and s.frame_count > 0 and s.camera is not None,
    timeout_ms=3000
)
```

---

## Help & Resources

- **Structure Guide**: [STRUCTURE.md](STRUCTURE.md)
- **Example Tests**: [examples/test_example_events_and_state.py](examples/test_example_events_and_state.py)
- **Helpers Reference**: [helpers/workflow_helpers.py](helpers/workflow_helpers.py)
- **Full Documentation**: [../src/sphinx/testing.md](../src/sphinx/testing.md)
- **pytest-qt docs**: https://pytest-qt.readthedocs.io/

---

## Quick Reference

```bash
# Run all tests
python run_tests.py

# Run category
python run_tests.py integration/ui/

# Run file
python run_tests.py integration/ui/test_welcome_screen.py

# Run test
python run_tests.py integration/ui/test_welcome_screen.py::test_enable_all_plugins

# Verbose
python run_tests.py -v

# Keep app open
python run_tests.py --keep-app-open

# Keep test data
DATALENS_KEEP_TEST_DATA=1 python run_tests.py

# Debug on failure
python run_tests.py --pdb
```
