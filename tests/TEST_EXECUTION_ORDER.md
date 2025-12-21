# Test Execution Order

## Overview

DataLens tests are organized to run in a specific order that mirrors the typical user workflow and application lifecycle. This ensures that:

1. **Foundation tests** (welcome screen, preferences) run first
2. **Workflow tests** (app navigation, project lifecycle) run second
3. **Plugin-specific tests** run third
4. **Example/reference tests** run last

## Test Categories and Order

### 1. Welcome Screen & UI Tests (test_01*.py)

**Location**: `integration/ui/`

These tests verify the initial user experience and core UI components:

- **test_01a_welcome_screen.py** (2 tests)
  - Enable all plugins workflow
  - Selective plugin enablement

- **test_01b_preferences.py** (5 tests)
  - Preferences dialog opening
  - Plugin preferences (reset button)
  - Keyboard shortcuts page
  - Theme switching
  - Preferences persistence

**Why First**: These tests establish that the basic application UI and user onboarding work correctly before testing more complex workflows.

### 2. App Workflow Tests (test_02*.py)

**Location**: `integration/workflows/`

These tests verify end-to-end application workflows and state management:

- **test_02_app_workflows.py** (8 tests)
  - Welcome screen quit button
  - All plugin combinations
  - Project creation and recent projects
  - Complete single-plugin workflow
  - Plugin enable/verify
  - Plugin switching on restart
  - All plugins + project workflow
  - Recent projects multiple loads

- **test_02_project_lifecycle.py** (3 tests)
  - Project load/unload workflow
  - Multiple project loads
  - Project unload cleanup

**Why Second**: After verifying basic UI works, these tests ensure the core application workflows (project management, plugin switching, state persistence) function correctly.

### 3. Plugin Widget Tests (test_03*.py)

**Location**: `integration/plugins/`

These tests systematically discover and test all widgets in plugin workspaces:

- **test_03_plugin_widget_groups.py** (4 tests)
  - Plugin widget groups discovery
  - Widget inventory generation
  - Individual plugin widget tests (widget_test)
  - Individual plugin widget tests (capture)

**Why Third**: Plugin-specific testing requires both UI infrastructure and workflow systems to be validated first. These tests exercise plugin-specific functionality and widget interactions.

### 4. Example Tests (test_*.py)

**Location**: `examples/`

Reference implementations and comprehensive feature demonstrations:

- **test_example_events_and_state.py** (7 tests)
  - Event watcher patterns
  - State watcher patterns
  - Combined events and state
  - Wait-for-condition patterns
  - Visual indicator changes
  - Camera streaming template

- **test_keyboard_shortcuts.py** (8 tests)
  - Shortcut registration queries
  - Modifier key combinations
  - Shortcut-triggered buttons
  - Hold vs toggle modes
  - All plugin shortcuts
  - Shortcut overrides in preferences
  - Complex shortcut simulation
  - Shortcut-button integration

- **test_widget_group_discovery.py** (4 tests)
  - Widget group discovery
  - Systematic widget interactions
  - Widget group shortcuts
  - Enumeration of testable widgets

**Why Last**: Examples serve as documentation and reference implementations. They test comprehensive feature combinations and advanced patterns that build on all previous test categories.

## File Naming Convention

Files are prefixed with numerical codes to control execution order:

- `test_01a_*.py` - Core UI tests (welcome screen first)
- `test_01b_*.py` - Core UI tests (preferences second)
- `test_02_*.py` - Workflow tests
- `test_03_*.py` - Plugin tests
- `test_*.py` (examples/) - Example tests (no prefix needed)

## Configuration

Test execution order is controlled by:

1. **pytest.ini** - Defines `testpaths` in order:
   ```ini
   testpaths =
       integration/ui
       integration/workflows
       integration/plugins
       examples
   ```

2. **File naming** - Alphabetical ordering within each directory
3. **run_tests.py** - Honors pytest.ini configuration when no specific path is given

## Running Tests

### Run all tests in order
```bash
python run_tests.py
```

### Run specific category
```bash
# Welcome screen only
python run_tests.py integration/ui/test_01a_welcome_screen.py

# All workflow tests
python run_tests.py integration/workflows/

# Plugin tests only
python run_tests.py integration/plugins/
```

### Run specific plugin tests
```bash
# Test widget_test plugin
python run_tests.py integration/plugins/test_03_plugin_widget_groups.py --plugin=widget_test

# Test all plugins
python run_tests.py integration/plugins/test_03_plugin_widget_groups.py --test-all-plugins
```

## Verification

To verify the execution order without running tests:

```bash
cd datalens/tests
python -m pytest --collect-only -q
```

This will show all tests in the order they will execute.

## Benefits of This Organization

1. **Logical progression**: Tests flow from simple to complex, foundation to features
2. **Fast failure**: Core UI issues are caught immediately
3. **Clear dependencies**: Later tests can assume earlier categories passed
4. **Maintainability**: Easy to understand test organization
5. **Debugging**: When a test fails, you know which system component is affected
6. **CI/CD friendly**: Can run subsets (e.g., only welcome + workflows for quick checks)

## Summary

```
Test Execution Flow:
┌─────────────────────────────────────┐
│ 1. Welcome Screen & Preferences     │  Foundation
│    (Can I launch and configure?)    │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│ 2. App Workflows & Projects         │  Core Features
│    (Can I use the app?)             │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│ 3. Plugin-Specific Features         │  Extended Features
│    (Do plugins work correctly?)     │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│ 4. Examples & Reference Patterns    │  Documentation
│    (How to use advanced features?)  │
└─────────────────────────────────────┘
```
