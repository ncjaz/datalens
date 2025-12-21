# Test Directory Structure

This document explains the organization of the DataLens test suite.

## Directory Layout

```
tests/
├── run_tests.py              # Main test runner script
├── conftest.py               # pytest configuration and global fixtures
├── pytest.ini                # pytest settings
├── README.md                 # Quick start guide
├── STRUCTURE.md              # This file
│
├── helpers/                  # Test helper utilities
│   ├── __init__.py
│   └── workflow_helpers.py   # UI interaction helpers (EventWatcher, StateWatcher, etc.)
│
├── fixtures/                 # pytest fixtures and test utilities
│   ├── __init__.py
│   └── testing_mode.py       # Isolated testing environment setup
│
├── integration/              # Integration tests (full app loaded)
│   ├── __init__.py
│   │
│   ├── ui/                   # UI component integration tests
│   │   ├── __init__.py
│   │   ├── test_welcome_screen.py        # Welcome screen tests
│   │   └── test_example_preferences.py   # Preferences dialog tests
│   │
│   └── workflows/            # End-to-end workflow tests
│       ├── __init__.py
│       ├── test_app_workflows.py         # Comprehensive app workflows
│       └── test_project_lifecycle.py     # Project management workflows
│
├── unit/                     # Unit tests (future - individual components)
│   └── __init__.py
│
└── examples/                 # Example tests showing testing patterns
    ├── __init__.py
    └── test_example_events_and_state.py  # Event/State watcher examples
```

## Directory Purposes

### Root Level

- **`run_tests.py`**: Main entry point for running tests
  - Run all tests: `python run_tests.py`
  - Run specific file: `python run_tests.py integration/ui/test_welcome_screen.py`
  - With options: `python run_tests.py -vv --keep-app-open`

- **`conftest.py`**: Global pytest configuration
  - Session-scoped fixtures (`qapp`, `datalens_app`, `test_environment`)
  - Function-scoped fixtures (`project_lifecycle`, `test_project_root`)
  - Shared test setup/teardown

- **`pytest.ini`**: pytest configuration file
  - Test discovery patterns
  - Marker definitions
  - Output settings

### `helpers/`

**Purpose**: Reusable helper utilities for writing tests

**Contents**:
- **`workflow_helpers.py`**: Core testing utilities
  - `WelcomeScreenHelper`: Interact with welcome screen
  - `MainWindowHelper`: Interact with main window and menus
  - `ProjectHelper`: Create/delete test projects
  - `EventWatcher`: Monitor DataLens events
  - `StateWatcher`: Monitor DataLens state changes
  - `wait_for_condition()`: Generic polling utility

**When to add here**:
- Reusable UI interaction helpers
- Common assertion utilities
- Widget finders and verifiers

### `fixtures/`

**Purpose**: pytest fixtures and test environment setup

**Contents**:
- **`testing_mode.py`**: Isolated test environment
  - `TestingEnvironment`: Manages temp directories
  - `TestingEnvironmentConfig`: Configuration options
  - `isolated_test_environment()`: Context manager for test isolation

**When to add here**:
- pytest fixtures that set up test data
- Database/project initialization
- Mock data generators
- Test environment configuration

### `integration/`

**Purpose**: Integration tests that run against the full DataLens application

**Key Principle**: All tests here must run with the complete app loaded (via `datalens_app` fixture)

#### `integration/ui/`

**Purpose**: Tests for individual UI components/dialogs in context of full app

**Examples**:
- Welcome screen functionality
- Preferences dialog
- Menu interactions
- Plugin UI components

**When to add here**:
- Testing a specific dialog or window
- Verifying UI component behavior
- Testing user interactions with specific widgets

#### `integration/workflows/`

**Purpose**: End-to-end workflow tests spanning multiple UI areas

**Examples**:
- Complete app startup → plugin selection → project creation → use
- Plugin switching workflows
- Project lifecycle workflows
- File menu operations

**When to add here**:
- Multi-step user journeys
- Cross-component workflows
- State transitions across app areas
- Complex user scenarios

### `unit/`

**Purpose**: Unit tests for individual functions/classes (FUTURE)

**Not currently used** - All current tests are integration tests with full app loaded.

**Future use**:
- Testing pure functions
- Testing individual classes in isolation
- Testing utilities without Qt/UI
- Fast-running focused tests

### `examples/`

**Purpose**: Example tests demonstrating testing patterns and best practices

**Contents**:
- **`test_example_events_and_state.py`**: Shows how to use EventWatcher and StateWatcher
  - Event monitoring examples
  - State verification examples
  - Visual indicator testing examples
  - Complete streaming test template

**When to add here**:
- Tutorial/documentation tests
- Testing pattern examples
- Templates for common scenarios
- Reference implementations

## File Naming Conventions

### Test Files
- **Must start with `test_`**: `test_welcome_screen.py`
- **Descriptive names**: `test_app_workflows.py` not `test_1.py`
- **Group related tests**: All workflow tests in `test_app_workflows.py`

### Helper Files
- **Descriptive suffixes**: `workflow_helpers.py`, `ui_helpers.py`
- **No `test_` prefix**: These are utilities, not test files

## Test Organization Principles

### 1. Integration Over Unit
Currently, all tests are integration tests with the full app loaded. This ensures:
- Real-world behavior testing
- Proper event propagation
- Actual state management
- Complete plugin integration

### 2. Logical Grouping
Tests are grouped by:
- **UI area** (`ui/`) - tests for specific dialogs/windows
- **Workflow** (`workflows/`) - tests spanning multiple areas
- **Purpose** (`examples/`) - teaching/reference

### 3. Reusability
Common code goes in `helpers/`:
- Widget finders
- Action helpers (click, type, etc.)
- Verification helpers
- Wait utilities

### 4. Isolation
Each test runs in isolation via `testing_mode.py`:
- Separate settings.json
- Temporary test projects
- No contamination of user data
- Automatic cleanup

## Adding New Tests

### For a New UI Component

1. Create file in `integration/ui/`:
   ```python
   # integration/ui/test_my_dialog.py
   import pytest
   from helpers.workflow_helpers import wait_for_condition

   @pytest.mark.ui
   def test_my_dialog_opens(datalens_app):
       # Test implementation
       pass
   ```

2. Add helper to `helpers/workflow_helpers.py` if needed:
   ```python
   class MyDialogHelper:
       def __init__(self, dialog):
           self.dialog = dialog

       def click_ok(self):
           # Helper implementation
           pass
   ```

### For a New Workflow

1. Create file in `integration/workflows/`:
   ```python
   # integration/workflows/test_export_workflow.py
   import pytest
   from helpers.workflow_helpers import EventWatcher, StateWatcher

   @pytest.mark.ui
   def test_export_complete_workflow(datalens_app):
       # Test implementation
       pass
   ```

### For a New Helper

1. Add to appropriate file in `helpers/`:
   ```python
   # helpers/workflow_helpers.py

   class ExportHelper:
       """Helper for export operations."""

       def export_to_format(self, format: str):
           # Implementation
           pass
   ```

2. Export in `__all__`:
   ```python
   __all__ = [
       "WelcomeScreenHelper",
       "ExportHelper",  # Add new helper
       # ...
   ]
   ```

## Running Tests

### Run Everything
```bash
conda activate datalens
cd datalens/tests
python run_tests.py
```

### Run Specific Category
```bash
# All UI tests
python run_tests.py integration/ui/

# All workflow tests
python run_tests.py integration/workflows/

# All examples
python run_tests.py examples/
```

### Run Specific File
```bash
python run_tests.py integration/ui/test_welcome_screen.py
```

### Run Specific Test
```bash
python run_tests.py integration/ui/test_welcome_screen.py::test_welcome_screen_enable_all_plugins
```

### With Options
```bash
# Extra verbose
python run_tests.py -vv

# Keep app open after tests
python run_tests.py --keep-app-open

# Both
python run_tests.py integration/workflows/ -vv --keep-app-open
```

## Best Practices

### 1. Use Helpers
Don't duplicate widget-finding code - create a helper:
```python
# ❌ Bad - duplicated in every test
widget = window.findChild(QPushButton, "my_button")

# ✅ Good - reusable helper
helper = MyDialogHelper(window)
helper.click_my_button()
```

### 2. Use Event/State Watchers
Don't just check UI - verify actual behavior:
```python
# ✅ Good - verifies events and state
event_watcher = EventWatcher(app_ctx)
event_watcher.watch("capture.streaming_started")
click_start_button()
event_watcher.assert_received("capture.streaming_started")

state_watcher = StateWatcher(app_ctx)
state_watcher.assert_state(lambda s: s.capture.is_streaming)
```

### 3. Use wait_for_condition
Don't use fixed waits - poll for conditions:
```python
# ❌ Bad
QTest.qWait(2000)  # Hope it's done

# ✅ Good
success = wait_for_condition(
    lambda: widget.isVisible(),
    timeout_ms=2000
)
assert success
```

### 4. Clean Up
Always clean up in test teardown:
```python
try:
    # Test code
    pass
finally:
    window.close()
    window.deleteLater()
    event_watcher.cleanup()
```

## Future Expansion

As the test suite grows, consider:

1. **Plugin-Specific Tests**:
   ```
   integration/plugins/
   ├── test_capture_plugin.py
   ├── test_annotation_plugin.py
   └── test_training_plugin.py
   ```

2. **Performance Tests**:
   ```
   performance/
   ├── test_startup_time.py
   ├── test_plugin_load_time.py
   └── test_memory_usage.py
   ```

3. **Regression Tests**:
   ```
   regression/
   ├── test_issue_123.py  # Specific bug fixes
   └── test_pr_456.py     # PR validations
   ```

4. **Plugin Helpers**:
   ```
   helpers/
   ├── workflow_helpers.py
   ├── capture_helpers.py      # Capture plugin specific
   ├── annotation_helpers.py   # Annotation plugin specific
   └── training_helpers.py     # Training plugin specific
   ```

## Questions?

See also:
- [README.md](README.md) - Quick start guide
- [helpers/workflow_helpers.py](helpers/workflow_helpers.py) - Helper documentation
- [examples/test_example_events_and_state.py](examples/test_example_events_and_state.py) - Usage examples
