# Settings and User Data Isolation in Tests

## Overview

DataLens tests run in a **fully isolated environment** that never touches the user's actual settings, projects, or data. This document explains how isolation works and what guarantees are provided.

## Isolation Mechanism

### Environment Variables

The test framework uses environment variables to override default paths:

1. **`DATALENS_USER_DATA_DIR`** - Overrides the entire user data directory
   - Default (production): `%LOCALAPPDATA%\datalens` (Windows) or `~/.local/share/datalens` (Linux/Mac)
   - Test override: Temporary directory like `C:\Users\...\AppData\Local\Temp\datalens_test_xyz123`

2. **`DATALENS_SETTINGS_PATH`** - Overrides the settings.json file location
   - Default (production): `{user_data_dir}/settings.json`
   - Test override: `{temp_dir}/settings/settings.json`

### Isolation Setup

```python
# In conftest.py test_environment fixture

with isolated_test_environment(config) as env:
    # Set environment variables before loading app
    os.environ["DATALENS_USER_DATA_DIR"] = str(temp_dir / "settings")
    os.environ["DATALENS_SETTINGS_PATH"] = str(temp_dir / "settings" / "settings.json")

    # Now when the app loads, it uses isolated paths
    app = DatalensApplication()
    # app.load_settings() -> reads from temp_dir, not user's actual settings
```

### What Gets Isolated

✅ **Fully Isolated:**
- `settings.json` (app settings, plugin preferences, shortcuts)
- Plugin metadata overrides
- Enabled plugins list
- Recent projects list
- Theme settings
- Keyboard shortcuts
- Plugin-specific preferences
- User plugins directory
- Test projects

❌ **Not Isolated (Shared):**
- Shipped plugins (in `datalens/src/datalens/plugins/`)
- Application code
- Python environment

## Isolation Lifecycle

### 1. Test Session Start

```
pytest starts
│
├─ test_environment fixture (session scope)
│  ├─ Create temp directory: /tmp/datalens_test_abc123/
│  ├─ Create settings dir: /tmp/datalens_test_abc123/settings/
│  ├─ Create settings.json with defaults:
│  │  {
│  │    "enabled_plugins": [],
│  │    "recent_projects": [],
│  │    "keyboard_shortcuts": {},
│  │    ...
│  │  }
│  ├─ Set environment variables:
│  │  DATALENS_USER_DATA_DIR=/tmp/datalens_test_abc123/settings
│  │  DATALENS_SETTINGS_PATH=/tmp/datalens_test_abc123/settings/settings.json
│  │
│  └─ Create DatalensApplication
│     └─ Loads settings from isolated path
```

### 2. During Tests

```
Tests run
│
├─ App reads settings
│  └─ settings_json_path()
│     └─ Checks DATALENS_SETTINGS_PATH
│        └─ Returns isolated temp path
│
├─ Tests modify settings
│  └─ Changes written to temp settings.json
│     └─ User's actual settings UNTOUCHED
│
└─ Plugin enablement
   └─ Plugins loaded/unloaded in isolated environment
      └─ Changes saved to temp settings.json
```

### 3. Test Session End

```
pytest finishing
│
├─ test_environment fixture cleanup
│  └─ Delete temp directory
│     └─ /tmp/datalens_test_abc123/ removed
│        (unless DATALENS_KEEP_TEST_DATA=1)
│
└─ User's actual settings unchanged
```

## Configuration Options

### Keep Test Data

By default, test data is cleaned up automatically. To preserve it for debugging:

```bash
# Set environment variable before running tests
export DATALENS_KEEP_TEST_DATA=1
python datalens/tests/run_tests.py

# Or in Windows
set DATALENS_KEEP_TEST_DATA=1
python datalens/tests/run_tests.py
```

Output will show:
```
Test data preserved at: C:\Users\...\AppData\Local\Temp\datalens_test_xyz123
```

### Copy User Settings

By default, tests start with fresh default settings. To test against a copy of user's actual settings:

```python
# In conftest.py
config = TestingEnvironmentConfig(
    copy_user_settings=True,  # Copy user's settings.json to temp
    keep_test_data=False,
)
```

⚠️ **Important**: Even when copying user settings, tests still run in isolation - the COPY is modified, not the original.

## Path Resolution

### Production (Normal App Launch)

```python
from datalens.infra.paths import settings_json_path, datalens_user_data_dir

# Returns user's actual path
user_data_dir()  # -> C:\Users\username\AppData\Local\datalens
settings_json_path()  # -> C:\Users\username\AppData\Local\datalens\settings.json
```

### Testing (With Environment Variables Set)

```python
import os
os.environ["DATALENS_USER_DATA_DIR"] = "/tmp/datalens_test_xyz/settings"
os.environ["DATALENS_SETTINGS_PATH"] = "/tmp/datalens_test_xyz/settings/settings.json"

from datalens.infra.paths import settings_json_path, datalens_user_data_dir

# Returns isolated test paths
user_data_dir()  # -> /tmp/datalens_test_xyz/settings
settings_json_path()  # -> /tmp/datalens_test_xyz/settings/settings.json
```

## Plugin State Isolation

### Plugin Enablement During Tests

When tests enable plugins:

```python
# Test code
ensure_plugins_enabled(datalens_app, ["capture", "widget_test"])

# What happens:
# 1. Reads current enabled plugins from temp settings.json
# 2. Merges with new plugins to enable
# 3. Calls plugin_host.set_enabled() to load plugins
# 4. Writes updated state to temp settings.json
# 5. User's actual settings.json NEVER touched
```

### Plugin State Restoration

```python
# Test code
try:
    original = ensure_plugins_enabled(app, ["capture"])
    # Test the capture plugin...
finally:
    restore_plugin_state(app, original)

# What happens:
# 1. Disables test-enabled plugins
# 2. Restores original enabled set
# 3. Writes restored state to temp settings.json
# 4. User's actual settings STILL untouched
```

## Verification

### Check Isolation is Working

You can verify isolation by checking which settings file is loaded:

```python
def test_isolation_working(datalens_app):
    from datalens.infra.paths import settings_json_path

    settings_path = settings_json_path()
    print(f"Settings path: {settings_path}")

    # Should be in a temp directory
    assert "datalens_test_" in str(settings_path)
    assert "Temp" in str(settings_path) or "tmp" in str(settings_path)
```

### Manually Check User Settings

After running tests, check your actual user settings:

**Windows:**
```
C:\Users\YourName\AppData\Local\datalens\settings.json
```

**Linux/Mac:**
```
~/.local/share/datalens/settings.json
```

The modified date should NOT change when tests run (assuming you had settings before).

## Implementation Details

### paths.py Implementation

```python
# datalens/src/datalens/infra/paths.py

def datalens_user_data_dir(*, app_name: str = "datalens") -> Path:
    """Return the per-user DataLens data directory."""

    # Check for testing/override environment variable FIRST
    override = os.environ.get("DATALENS_USER_DATA_DIR")
    if override:
        return Path(override)  # Use test path if set

    # Fall back to platform-specific defaults
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or ...
        return Path(root) / app_name
    ...

def settings_json_path() -> Path:
    """Default path for persisted AppSettings."""

    # Check for testing/override FIRST
    override = os.environ.get("DATALENS_SETTINGS_PATH")
    if override:
        return Path(override)  # Use test path if set

    # Fall back to default
    return datalens_user_data_dir() / "settings.json"
```

The key is checking environment variables **before** falling back to defaults.

## Best Practices

### 1. Never Hardcode Paths

```python
# ❌ BAD - Hardcoded path
settings = load_settings(Path.home() / ".local" / "share" / "datalens" / "settings.json")

# ✅ GOOD - Use path utilities
from datalens.infra.paths import settings_json_path
settings = load_settings(settings_json_path())
```

### 2. Trust the Isolation

```python
# ✅ Good - Trust that settings are isolated
def test_change_theme(datalens_app):
    # Modify settings freely - they're in a temp directory
    settings = load_settings()
    settings.theme_opacity = 0.5
    save_settings(settings)
    # Changes saved to temp settings.json, not user's actual file
```

### 3. Restore State in Tests

```python
# ✅ Good - Restore state even though it's isolated
def test_plugin_loading(datalens_app):
    original_enabled = datalens_app._test_settings.enabled_plugins
    try:
        enable_plugins(["capture"])
        # Test...
    finally:
        restore_plugins(original_enabled)
        # Keeps test environment clean for next test
```

### 4. Use Keep Data for Debugging

```bash
# When debugging test failures
export DATALENS_KEEP_TEST_DATA=1
python datalens/tests/run_tests.py --plugin=capture

# Check what was written
cat /tmp/datalens_test_xyz123/settings/settings.json
```

## Troubleshooting

### Problem: "My actual settings were modified!"

**Diagnosis:**
```python
# Add this to conftest.py temporarily
def test_environment(...):
    print(f"DATALENS_USER_DATA_DIR = {os.environ.get('DATALENS_USER_DATA_DIR')}")
    print(f"DATALENS_SETTINGS_PATH = {os.environ.get('DATALENS_SETTINGS_PATH')}")
    print(f"Actual settings path = {settings_json_path()}")
```

**Expected output:**
```
DATALENS_USER_DATA_DIR = C:\Users\...\Temp\datalens_test_abc123\settings
DATALENS_SETTINGS_PATH = C:\Users\...\Temp\datalens_test_abc123\settings\settings.json
Actual settings path = C:\Users\...\Temp\datalens_test_abc123\settings\settings.json
```

**If different:** Environment variables aren't being set correctly - check conftest.py.

### Problem: "Tests are interfering with each other"

**Solution:** Ensure proper state restoration:

```python
# In test
original_enabled = ensure_plugins_enabled(app, ["capture"])
try:
    # Run test
finally:
    restore_plugin_state(app, original_enabled)  # CRITICAL
```

### Problem: "I need to debug what settings tests are using"

**Solution:**
```bash
# Keep test data
export DATALENS_KEEP_TEST_DATA=1
python datalens/tests/run_tests.py

# Output shows temp directory
# Test data preserved at: /tmp/datalens_test_xyz123

# Inspect files
ls -la /tmp/datalens_test_xyz123/settings/
cat /tmp/datalens_test_xyz123/settings/settings.json
```

## Summary

✅ **Isolation Guarantees:**

1. **User settings NEVER modified** during tests
2. **Each test session** uses a fresh temporary directory
3. **Settings changes** only affect the isolated environment
4. **Plugin state changes** only persist in test settings
5. **Automatic cleanup** removes all test data (unless explicitly kept)
6. **Environment variables** provide complete path override
7. **All path utilities** respect test environment

This provides **complete confidence** that running tests will never corrupt or modify your actual DataLens configuration, plugins, or user data.
