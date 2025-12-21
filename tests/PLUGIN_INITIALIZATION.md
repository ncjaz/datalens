# Plugin Initialization and State Management in Tests

## Overview

When testing plugins in DataLens, it's critical to ensure that plugins are fully initialized before testing their UI components. This document explains how plugin initialization works and what guarantees the test framework provides.

## Plugin Lifecycle

### 1. Plugin Discovery (App Startup)

```python
# In conftest.py
plugin_discovery = discover_plugins()
plugin_host = PluginHost(plugin_discovery.registry)
app.app_context.plugin_host = plugin_host
```

At this stage:
- ✅ Plugin metadata is loaded
- ✅ Plugin registry is available
- ❌ Plugin code is NOT imported yet
- ❌ Plugin instances are NOT created yet

### 2. Plugin Enabling (On-Demand)

```python
# When enabling plugins
plugin_host.set_enabled(
    app_ctx=app_context,
    plugin_ids=new_enabled,
    project=None,
)
```

This triggers:
1. **Import** of plugin module code
2. **Creation** of plugin instance via `get_plugin()`
3. **`on_load(ctx)`** hook call (synchronous)
4. **`register_shortcuts(ctx)`** hook call (best-effort)
5. **Event publication**: `PLUGIN_ENABLED` event
6. **`on_focus(ctx)`** hook if workspace already selected (rare)

⚠️ **Important**: The plugin host documentation states: "Do not call it on the UI thread" because it imports code.

### 3. Workspace Creation (Test Time)

```python
# Creating workspace for testing
workspace = plugin_class(**kwargs)
workspace.show()
QTest.qWait(100)
```

This happens AFTER plugin enabling:
- Workspace widget is instantiated
- UI hierarchy is built
- Widget discovery can find all controls

## Test Framework Guarantees

### Current Implementation

The test framework in `test_03_plugin_widget_groups.py` ensures:

1. **Plugin Enablement Before Testing**
   ```python
   original_enabled, _ = ensure_plugins_enabled(datalens_app, plugin_ids)
   # Plugins are now loaded and on_load hooks have been called
   ```

2. **Event Processing After Enable**
   ```python
   # Inside ensure_plugins_enabled()
   plugin_host.set_enabled(...)
   QApplication.processEvents()  # Process pending Qt events
   QTest.qWait(200)  # Wait for async initialization
   ```

3. **Workspace Initialization**
   ```python
   workspace = create_plugin_workspace(plugin_id, datalens_app)
   workspace.show()
   QTest.qWait(100)  # Wait for UI to render
   ```

4. **Clean Teardown**
   ```python
   # After tests complete
   restore_plugin_state(datalens_app, original_enabled)
   # Calls on_unload hooks and processes events
   ```

### Why Event Processing is Critical

Plugin initialization may trigger:
- **Event subscriptions** (e.g., listening to project events)
- **UI updates** (e.g., registering shortcuts in preferences)
- **Async operations** (e.g., device scanning in capture plugin)
- **Timer starts** (e.g., periodic refresh timers)

Without `QApplication.processEvents()` and `QTest.qWait()`:
- Events may still be queued but not processed
- Timers may not have fired their first callback
- Event subscriptions may not be fully connected
- UI state may be incomplete

## Navigation Between Plugins

When the actual app switches between plugins (via navigation):

1. **Defocus Previous Plugin**
   ```python
   # Called by plugin host when workspace loses focus
   plugin.on_defocus(ctx)
   ```

2. **Focus New Plugin**
   ```python
   # Called by plugin host when workspace gains focus
   plugin.on_focus(ctx)
   ```

3. **Workspace Lifecycle**
   - Workspaces are typically created lazily (first time selected)
   - Once created, they're reused when navigating back
   - Plugins manage their own state during focus/defocus

⚠️ **Testing vs Production**: In tests, we create workspaces directly without going through the navigation system, so we don't get the full focus/defocus cycle.

## Common Issues and Solutions

### Issue: Plugin Not Fully Initialized

**Symptoms:**
- Widget discovery finds 0 groups
- Plugin service is None
- UI elements missing

**Solution:**
Ensure `ensure_plugins_enabled()` is called before creating workspace:
```python
original_enabled, _ = ensure_plugins_enabled(datalens_app, ["capture"])
# Now safe to create workspace
workspace = create_plugin_workspace("capture", datalens_app)
```

### Issue: Race Conditions

**Symptoms:**
- Intermittent test failures
- Different behavior on different runs
- Timing-dependent issues

**Solution:**
Add proper waits after critical operations:
```python
plugin_host.set_enabled(...)
QApplication.processEvents()  # Let events propagate
QTest.qWait(200)  # Wait for async operations
```

### Issue: State Pollution Between Tests

**Symptoms:**
- Tests pass individually but fail when run together
- First test passes, second fails
- Plugin already enabled errors

**Solution:**
Always restore state in finally block:
```python
try:
    ensure_plugins_enabled(datalens_app, ["capture"])
    # Run tests...
finally:
    restore_plugin_state(datalens_app, original_enabled)
```

## Best Practices

### 1. Always Wait After Plugin Operations

```python
# ✅ Good
plugin_host.set_enabled(...)
QApplication.processEvents()
QTest.qWait(200)

# ❌ Bad
plugin_host.set_enabled(...)
# Immediately test - may fail!
```

### 2. Test One Plugin at a Time

```python
# ✅ Good - Test plugins in isolation
for plugin_id in ["widget_test", "capture"]:
    ensure_plugins_enabled(app, [plugin_id])
    test_plugin(plugin_id)
    restore_plugin_state(app, original)

# ⚠️ Acceptable - Test multiple plugins together
ensure_plugins_enabled(app, ["widget_test", "capture"])
test_all_plugins()
restore_plugin_state(app, original)
```

### 3. Use Proper Cleanup

```python
# ✅ Good
try:
    workspace = create_plugin_workspace(plugin_id, app)
    workspace.show()
    # Test workspace...
finally:
    if workspace:
        workspace.close()
        workspace.deleteLater()
```

### 4. Verify Plugin is Enabled

```python
# ✅ Good
capture_plugin = plugin_host.get_enabled_plugin(PluginId("capture"))
if capture_plugin is None:
    pytest.skip("Capture plugin is not enabled")
```

## Timeline of a Plugin Test

```
Test Start
│
├─ Load app settings
├─ Create plugin host
│  └─ Plugins discovered but NOT loaded
│
├─ ensure_plugins_enabled()
│  ├─ Update settings
│  ├─ Call plugin_host.set_enabled()
│  │  ├─ Import plugin code
│  │  ├─ Create plugin instance
│  │  ├─ Call on_load()
│  │  ├─ Call register_shortcuts()
│  │  └─ Publish PLUGIN_ENABLED event
│  ├─ QApplication.processEvents() ← Process queued events
│  └─ QTest.qWait(200) ← Wait for async operations
│
├─ create_plugin_workspace()
│  ├─ Import workspace class
│  ├─ Get plugin service (from enabled plugin)
│  ├─ Create workspace widget
│  └─ Return workspace instance
│
├─ workspace.show()
│  └─ QTest.qWait(100) ← Wait for UI rendering
│
├─ WidgetDiscovery.find_groups_in_panel()
│  └─ All widgets are now discoverable
│
├─ Test widget interactions
│  └─ Widgets are fully initialized
│
└─ Cleanup
   ├─ workspace.close()
   ├─ workspace.deleteLater()
   └─ restore_plugin_state()
      ├─ Call plugin_host.set_enabled() (restore original)
      │  └─ Calls on_unload() for disabled plugins
      ├─ QApplication.processEvents()
      └─ QTest.qWait(100)
```

## Conclusion

The test framework ensures plugins are fully initialized by:

1. ✅ Calling `plugin_host.set_enabled()` which triggers all load hooks
2. ✅ Processing Qt events after enabling (`QApplication.processEvents()`)
3. ✅ Waiting for async operations (`QTest.qWait(200)`)
4. ✅ Showing workspaces and waiting for UI (`workspace.show()` + `QTest.qWait(100)`)
5. ✅ Properly cleaning up with event processing on teardown

This provides a **deterministic, fully-initialized environment** for testing plugin widgets, equivalent to what would happen if a user enabled the plugin and navigated to its workspace in the real application.
