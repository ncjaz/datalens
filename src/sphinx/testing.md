# DataLens Testing Guide

This document describes the testing infrastructure for DataLens V2.

## Philosophy

**All tests MUST run with the full DataLens application loaded.**

Unlike traditional unit tests that test individual components in isolation, DataLens tests are full-application integration tests that:

- Load the complete application with all services initialized
- Interact through the UI (clicks, keyboard shortcuts, menu actions)
- Test real user workflows end-to-end
- Run in isolated environments that don't affect user data

**Why full-app testing?**

DataLens is a complex GUI application with:
- Plugin system with interdependencies
- Event-driven architecture with cross-component communication
- Custom keyboard shortcut system
- Theme and preferences that affect all components
- UI state that depends on loaded projects

Testing isolated widgets cannot verify that these systems work together correctly. Full-app testing ensures:
- Plugins load and initialize properly
- Events propagate correctly across the application
- Keyboard shortcuts work as expected
- UI interactions match real user experience
- Changes don't break existing workflows

## Testing Mode

Tests run in **testing mode**, which provides complete isolation from user data:

### Isolated Settings
- Tests use a separate `settings.json` in a temporary directory
- By default, tests start with fresh/default settings
- User's actual settings are never modified
- Settings changes during tests don't persist to the user's configuration

### Test Projects
- Test projects are created in temporary directories
- Projects are created through the UI (File → New Project, etc.)
- Projects are automatically deleted after tests complete
- If a test project exists when tests start, it's deleted first (ensures clean state)

### Cleanup
- All test data is automatically cleaned up after tests complete
- To preserve test data for debugging: `export DATALENS_KEEP_TEST_DATA=1`
- Preserved test data location is printed to console

## Quick Start

### Running All Tests

**Windows (Recommended - Auto-activates conda environment):**
```bash
cd datalens/tests
run_tests.bat
```

**Cross-platform (Requires manual conda activation):**
```bash
conda activate datalens
cd datalens/tests
python run_tests.py
```

### Running Specific Tests

```bash
# Run a specific test file
python run_tests.py test_preferences.py

# Run a specific test function
python run_tests.py test_preferences.py::test_reset_button

# Run tests matching a keyword
python run_tests.py -k "preferences"
```

### Useful Options

```bash
# Verbose output
python run_tests.py -v

# Exit on first failure
python run_tests.py -x

# Rerun only failed tests from last run
python run_tests.py --lf

# Run with coverage reporting
python run_tests.py --cov

# Preserve test data for debugging
DATALENS_KEEP_TEST_DATA=1 python run_tests.py
```

## Writing Tests

### Basic Test Structure

```python
from PySide6.QtTest import QTest
from datalens.core.context import get_app_context

def test_something(app_context):
    """
    Test description.

    All tests automatically have the full app loaded via app_context fixture.
    """
    # Access application services
    prefs = app_context.preferences
    theme = app_context.theme

    # Interact through UI...
    # Make assertions...
```

### UI Interaction Example

```python
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QTreeWidget
from datalens.ui.menus.edit.preferences.preferences_dialog import PreferencesDialog

@pytest.mark.ui
def test_open_preferences(app_context):
    """Test opening and navigating preferences dialog."""
    # Create dialog (in real tests, trigger via menu action)
    dialog = PreferencesDialog()

    try:
        dialog.show()
        QTest.qWait(100)  # Wait for render

        # Find navigation tree
        nav = dialog.findChild(QTreeWidget, "PreferencesNav")
        assert nav is not None

        # Select an item
        for i in range(nav.topLevelItemCount()):
            item = nav.topLevelItem(i)
            if item and item.text(0) == "Plugins":
                nav.setCurrentItem(item)
                QTest.qWait(50)
                break

        # Find and click a button
        reset_btn = dialog.findChild(QPushButton, "ResetButton")
        if reset_btn:
            QTest.mouseClick(reset_btn, Qt.LeftButton)
            QTest.qWait(50)

    finally:
        dialog.close()
        dialog.deleteLater()
```

### Creating Test Projects

```python
def test_create_project(test_project_root):
    """
    Test project creation through UI.

    test_project_root fixture provides the path where the project should be created.
    """
    # Use UI to create project at test_project_root
    # Example: File → New Project → Select test_project_root

    # The project is automatically cleaned up after test completes
    # (unless DATALENS_KEEP_TEST_DATA=1)
```

### Available Fixtures

#### `app_context`
Function-scoped. Provides access to the application context.

```python
def test_preferences(app_context):
    prefs = app_context.preferences
    theme = app_context.theme
    shortcuts = app_context.shortcuts
```

#### `test_environment`
Session-scoped. Provides the isolated testing environment.

```python
def test_something(test_environment):
    settings_path = test_environment.settings_path
    project_root = test_environment.test_project_root
```

#### `test_project_root`
Function-scoped. Path where test projects should be created.

```python
def test_project_workflow(test_project_root):
    # Create project at test_project_root through UI
    assert test_project_root.exists()
```

#### `main_window`
Function-scoped. The application's main window (if available).

```python
def test_menu_action(main_window):
    edit_menu = main_window.menuBar().findChild(QMenu, "EditMenu")
```

#### `qapp`
Session-scoped. The QApplication instance.

```python
def test_qt_feature(qapp):
    # Access Qt application
    assert qapp is not None
```

## Test Markers

Use pytest markers to categorize tests:

```python
@pytest.mark.ui
def test_button_click():
    """Tests that involve UI interactions (clicks, keyboard)."""
    pass

@pytest.mark.slow
def test_long_running():
    """Tests that take significant time to complete."""
    pass

@pytest.mark.requires_app
def test_with_full_app():
    """Tests that explicitly require the full app (all should have this)."""
    pass
```

## Simulating User Interactions

### Mouse Clicks

```python
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

# Click a button
QTest.mouseClick(button, Qt.LeftButton)

# Double-click
QTest.mouseDClick(widget, Qt.LeftButton)

# Click with modifier
QTest.mouseClick(button, Qt.LeftButton, Qt.ControlModifier)
```

### Keyboard Input

```python
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

# Type text into a widget
QTest.keyClicks(line_edit, "Hello World")

# Press a key
QTest.keyPress(widget, Qt.Key_Enter)

# Press key with modifier
QTest.keyClick(widget, Qt.Key_S, Qt.ControlModifier)  # Ctrl+S
```

### Waiting

```python
from PySide6.QtTest import QTest

# Wait for rendering/animations
QTest.qWait(100)  # Wait 100ms

# Wait for a condition
def condition():
    return widget.isVisible()

QTest.qWaitFor(condition, timeout=5000)  # Wait up to 5 seconds
```

## Best Practices

### 1. Always Clean Up Widgets

```python
def test_dialog():
    dialog = MyDialog()
    try:
        dialog.show()
        # ... test code ...
    finally:
        dialog.close()
        dialog.deleteLater()
```

### 2. Wait for Async Operations

```python
# Wait for dialog to render
dialog.show()
QTest.qWait(100)

# Wait for animation to complete
QTest.qWait(300)
```

### 3. Use Descriptive Test Names

```python
# Good
def test_reset_button_restores_plugin_defaults():
    pass

# Bad
def test_button():
    pass
```

### 4. Test Real User Workflows

```python
# Good: Test the full workflow
def test_user_can_change_theme_through_preferences():
    # 1. Open preferences via menu
    # 2. Navigate to theme section
    # 3. Select new theme
    # 4. Apply changes
    # 5. Verify theme changed
    pass

# Bad: Test implementation details
def test_theme_manager_set_theme():
    theme_mgr.set_theme("dark")  # Bypasses UI
```

### 5. Don't Modify User Data

Tests run in isolated mode, but be defensive:

```python
# Good: Use test project fixture
def test_project_save(test_project_root):
    # Create project at test_project_root
    pass

# Bad: Hardcode paths
def test_project_save():
    # DON'T: project = Path.home() / "my_project"
    pass
```

## Error Detection System

DataLens tests use a comprehensive error detection system that catches errors even when they're handled gracefully by the application code.

### How It Works

The test system installs a custom logging handler (`ErrorCapturingHandler`) that monitors all log messages during widget interactions. This handler:

1. **Captures ERROR and CRITICAL logs**: Any log at ERROR or CRITICAL level is captured
2. **Captures logs with exceptions**: Even WARNING-level logs are captured if they contain exception information (`exc_info`)
3. **Captures error keywords**: Logs containing keywords like "error", "exception", "failed", "traceback" are captured
4. **Fails the test**: If any errors are captured during a button click or widget interaction, the test fails immediately

### Why This Matters

Traditional tests only catch **uncaught exceptions** that crash the test. But well-written application code often catches exceptions and logs them gracefully:

```python
try:
    do_something()
except Exception as e:
    log.error(f"Failed to do something: {e}")  # Logged but not raised
    return  # Function returns normally
```

**Without error detection**: Test passes ✓ (no crash)
**With error detection**: Test fails ✗ (error logged)

This ensures that widget interactions work **correctly**, not just that they don't crash.

### Example Test Failure

When a button click causes an error, you'll see:

```
AssertionError: Button 'button' in 'Toast Demo > Success Toast' caused errors:
[ERROR] datalens.services.notifications.toast_service: Failed to show success toast: Attempt to overwrite 'message' in LogRecord
  Error 1: [ERROR] datalens.services.notifications.toast_service
    Message: Failed to show success toast: Attempt to overwrite 'message' in LogRecord
    Location: e:\GitRepos\rsCapture\datalens\src\datalens\services\notifications\toast_service.py:15
    Exception: KeyError: "Attempt to overwrite 'message' in LogRecord"
```

This provides:
- Which button caused the error
- Which widget group it belongs to
- The error message
- The source code location
- The exception type and value

### Generalized Testing Approach

The test system uses a **generalized approach** that works for any plugin:

1. **Discover all widgets** using the widget discovery system
2. **Find all buttons** in each widget group (QPushButton, QToolButton)
3. **Click every button** that is visible and enabled
4. **Monitor for errors** during and after each click
5. **Fail immediately** if any error is detected

This means you don't need to write custom tests for each plugin - the system automatically tests all interactive widgets.

### Adding Error Detection to Your Tests

To add error detection to a custom test:

```python
import logging
from helpers.widget_discovery import ErrorCapturingHandler

def test_my_widget():
    # Install error handler
    error_handler = ErrorCapturingHandler()
    root_logger = logging.getLogger()
    root_logger.addHandler(error_handler)

    try:
        # Perform widget interactions
        QTest.mouseClick(my_button, Qt.LeftButton)
        QTest.qWait(100)

        # Check for errors
        if error_handler.has_errors():
            error_summary = error_handler.get_error_summary()
            raise AssertionError(f"Widget interaction caused errors:\n{error_summary}")
    finally:
        # Always remove the handler
        root_logger.removeHandler(error_handler)
```

## Test Infrastructure Details

### Directory Structure

```
datalens/
├── tests/
│   ├── conftest.py           # pytest configuration & fixtures
│   ├── run_tests.py          # Main test runner
│   ├── testing_mode.py       # Isolated environment utilities
│   ├── test_preferences.py   # Example: preferences tests
│   └── test_*.py             # Your test files
└── src/
    └── sphinx/
        └── testing.md        # This file
```

### How Testing Mode Works

1. **Environment Setup** (session-scoped)
   - Create temporary directory: `/tmp/datalens_test_XXXX/`
   - Create isolated `settings.json` with defaults
   - Set environment variables to redirect paths

2. **App Initialization** (session-scoped)
   - QApplication starts (one per session)
   - DataLens app initializes using isolated settings
   - All plugins load, services initialize

3. **Test Execution** (function-scoped)
   - Each test gets fixtures (app_context, test_project_root, etc.)
   - Tests interact through UI
   - Changes affect only isolated environment

4. **Cleanup** (session end)
   - App shuts down gracefully
   - Temporary directory deleted (unless DATALENS_KEEP_TEST_DATA=1)
   - Environment variables restored

### Customizing Test Environment

Edit `conftest.py` to customize the test environment:

```python
config = TestingEnvironmentConfig(
    copy_user_settings=True,   # Copy user's settings (default: False)
    keep_test_data=True,       # Never cleanup (default: False)
    test_project_name="my_test_project",  # Project name
)
```

## Troubleshooting

### Tests hang or don't start

- Check that QApplication is created properly
- Verify Qt event loop is running
- Use `QTest.qWait()` to allow events to process

### Tests fail inconsistently

- Add more `QTest.qWait()` calls for async operations
- Check for race conditions in event handling
- Ensure widgets are fully rendered before interaction

### Test data not cleaned up

- Check for exceptions during cleanup
- Verify `DATALENS_KEEP_TEST_DATA` is not set
- Look for file handles that aren't closed

### Can't find widgets in UI

- Use `widget.findChild(ClassName, "objectName")`
- Ensure widgets have object names set: `widget.setObjectName("MyWidget")`
- Wait for dialog to render: `QTest.qWait(100)`

### Settings changes don't persist between tests

This is expected! Tests use isolated settings that are reset for each test session. If you need shared state:
- Use session-scoped fixtures
- Or save state to test_environment paths

## Advanced Topics

### Custom Fixtures

Add to `conftest.py`:

```python
@pytest.fixture
def populated_project(test_project_root):
    """Create a project with sample data."""
    # Create project through UI
    # Add sample data
    yield test_project_root
    # Cleanup if needed
```

### Mocking External Services

```python
from unittest.mock import patch

def test_with_mock(app_context):
    with patch('datalens.services.external.ExternalService.fetch') as mock_fetch:
        mock_fetch.return_value = {"data": "test"}
        # Run test...
```

### Testing Keyboard Shortcuts

```python
from datalens.core.context import get_app_context

def test_keyboard_shortcut(app_context):
    # Verify shortcut is registered
    shortcuts = app_context.shortcuts
    bindings = shortcuts.snapshot()

    # Trigger shortcut programmatically
    # ... or use QTest.keyClick with modifiers
```

## Contributing Tests

When adding new tests:

1. **Follow naming convention**: `test_<feature>_<scenario>.py`
2. **Use markers**: Add `@pytest.mark.ui` for UI tests
3. **Document behavior**: Clear docstrings explaining what's tested
4. **Test real workflows**: Not implementation details
5. **Clean up resources**: Always close/delete widgets
6. **Use fixtures**: Don't reinitialize the app or environment

## Future Enhancements

Planned improvements to the test infrastructure:

- **Visual regression testing**: Screenshot comparison for UI changes
- **Performance benchmarks**: Track rendering and operation performance
- **Parallel test execution**: Run tests across multiple processes
- **CI/CD integration**: Automated testing on push/PR
- **Test coverage reports**: Track which code paths are tested
- **Mock project templates**: Pre-built projects for testing specific scenarios

## Getting Help

For questions about testing:

1. Check this documentation
2. Review example tests in `tests/test_example_preferences.py`
3. Look at `conftest.py` for available fixtures
4. Check pytest-qt documentation: https://pytest-qt.readthedocs.io/

For test failures or infrastructure issues, include:
- Full test output with `-v` flag
- Test environment details (preserved with `DATALENS_KEEP_TEST_DATA=1`)
- Steps to reproduce
- Expected vs actual behavior
