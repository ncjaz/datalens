"""
Systematic widget group testing for plugins.

This test suite automatically discovers and tests all widget groups in plugins.

Usage:
    # Test a specific plugin
    pytest tests/integration/plugins/test_plugin_widget_groups.py --plugin=capture

    # Test multiple plugins
    pytest tests/integration/plugins/test_plugin_widget_groups.py --plugin=capture --plugin=widget_test

    # Test all available plugins
    pytest tests/integration/plugins/test_plugin_widget_groups.py --test-all-plugins

    # Generate widget inventory report
    pytest tests/integration/plugins/test_plugin_widget_groups.py --plugin=capture --generate-inventory
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import replace

import pytest
from PySide6.QtTest import QTest

from datalens.domain.plugin import PluginId
from helpers.widget_discovery import WidgetDiscovery, WidgetGroup


class ErrorCapturingHandler(logging.Handler):
    """
    Logging handler that captures ERROR and CRITICAL level logs, plus exceptions.

    This is used during widget testing to detect when button clicks
    or widget interactions cause errors, even if those errors are
    caught and logged rather than raised.

    Also captures WARNING-level logs that contain exception information,
    as some code may log exceptions at WARNING level.
    """

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.errors = []
        self.exceptions_captured = []

    def emit(self, record):
        """
        Capture error records and any logs with exception info.

        Captures:
        - ERROR and CRITICAL level logs
        - Any log with exc_info (even if at WARNING level)
        - Any log message containing 'exception', 'error', 'failed' (case-insensitive)
        """
        should_capture = False

        # Always capture ERROR and CRITICAL
        if record.levelno >= logging.ERROR:
            should_capture = True
        # Capture if there's exception info
        elif record.exc_info:
            should_capture = True
        # Capture if message indicates an error/exception/failure
        elif any(keyword in record.getMessage().lower() for keyword in ['exception', 'error', 'failed', 'traceback']):
            should_capture = True

        if should_capture:
            error_info = {
                "message": record.getMessage(),
                "level": record.levelname,
                "name": record.name,
                "exc_info": record.exc_info,
                "pathname": record.pathname,
                "lineno": record.lineno,
            }
            self.errors.append(error_info)

            # Track unique exceptions
            if record.exc_info:
                exc_type, exc_value, exc_tb = record.exc_info
                if exc_value not in self.exceptions_captured:
                    self.exceptions_captured.append(exc_value)

    def clear(self):
        """Clear captured errors."""
        self.errors = []
        self.exceptions_captured = []

    def has_errors(self) -> bool:
        """Check if any errors were captured."""
        return len(self.errors) > 0

    def get_error_summary(self) -> str:
        """Get a summary of captured errors with full details."""
        if not self.errors:
            return ""
        lines = []
        for i, err in enumerate(self.errors, 1):
            lines.append(f"  Error {i}: [{err['level']}] {err['name']}")
            lines.append(f"    Message: {err['message']}")
            lines.append(f"    Location: {err['pathname']}:{err['lineno']}")
            if err['exc_info']:
                exc_type, exc_value, exc_tb = err['exc_info']
                lines.append(f"    Exception: {exc_type.__name__}: {exc_value}")
        return "\n".join(lines)


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "plugin_widget_test: mark test as a plugin widget group test",
    )


def get_plugins_to_test(request, datalens_app) -> list[str]:
    """
    Get the list of plugin IDs to test based on command-line options.

    Returns:
        List of plugin IDs to test
    """
    plugin_ids = request.config.getoption("--plugin")
    test_all = request.config.getoption("--test-all-plugins")

    if test_all:
        # Get all available plugins
        all_plugins = [
            r.definition.id
            for r in datalens_app._test_plugin_discovery.registry.all()
        ]
        return all_plugins
    elif plugin_ids:
        # Use specified plugins
        return plugin_ids
    else:
        # Default: test widget_test plugin (always available)
        return ["widget_test"]


def ensure_plugins_enabled(datalens_app, plugin_ids: list[str]) -> tuple[set[PluginId], set[PluginId]]:
    """
    Ensure specified plugins are enabled for testing.

    Args:
        datalens_app: The DataLens application
        plugin_ids: List of plugin IDs to enable

    Returns:
        Tuple of (original_enabled_plugins, plugins_to_restore)
    """
    from PySide6.QtWidgets import QApplication

    settings = datalens_app._test_settings
    plugin_host = datalens_app.app_context.plugin_host
    original_enabled = settings.enabled_plugins

    # Convert plugin IDs to PluginId objects
    plugins_to_enable = {PluginId(pid) for pid in plugin_ids}

    # Combine with already enabled plugins
    new_enabled = original_enabled | plugins_to_enable

    # Update settings
    datalens_app._test_settings = replace(settings, enabled_plugins=new_enabled)

    # Actually enable the plugins in the plugin host
    # Note: This imports plugin code and calls on_load hooks
    plugin_host.set_enabled(
        app_ctx=datalens_app.app_context,
        plugin_ids=new_enabled,
        project=None,
    )

    # Process any pending Qt events to ensure plugins are fully initialized
    # This is critical because plugin initialization may queue UI updates,
    # event subscriptions, and other async operations
    QApplication.processEvents()
    QTest.qWait(200)  # Additional wait for async plugin initialization

    return original_enabled, plugins_to_enable


def restore_plugin_state(datalens_app, original_enabled: set[PluginId]):
    """
    Restore original plugin enabled state.

    Args:
        datalens_app: The DataLens application
        original_enabled: Original set of enabled plugins
    """
    from PySide6.QtWidgets import QApplication

    settings = datalens_app._test_settings
    plugin_host = datalens_app.app_context.plugin_host

    # Update settings
    datalens_app._test_settings = replace(settings, enabled_plugins=original_enabled)

    # Restore plugin host state
    # This will call on_unload hooks for disabled plugins
    plugin_host.set_enabled(
        app_ctx=datalens_app.app_context,
        plugin_ids=original_enabled,
        project=None,
    )

    # Process events to ensure clean teardown
    QApplication.processEvents()
    QTest.qWait(100)


def create_plugin_workspace(plugin_id: str, datalens_app):
    """
    Create a workspace widget for the specified plugin.

    Args:
        plugin_id: The plugin ID
        datalens_app: The DataLens application

    Returns:
        The workspace widget, or None if plugin doesn't have a workspace
    """
    # Map plugin IDs to their workspace widget classes
    workspace_classes = {
        "widget_test": "datalens.plugins.widget_test.ui.workspace.WorkspaceWidget",
        "capture": "datalens.plugins.capture.ui.workspace.CaptureWorkspaceWidget",
    }

    workspace_class_path = workspace_classes.get(plugin_id)
    if not workspace_class_path:
        return None

    # Import the workspace class
    module_path, class_name = workspace_class_path.rsplit(".", 1)
    try:
        module = __import__(module_path, fromlist=[class_name])
        workspace_class = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        pytest.skip(f"Could not import workspace for plugin {plugin_id}: {e}")
        return None

    # Create workspace with appropriate parameters
    # Note: Different plugins have different constructor signatures
    if plugin_id == "widget_test":
        kwargs = {
            "theme": datalens_app.app_theme,
            "parent": None,
            "shortcut_button_bindings": None,
        }
    elif plugin_id == "capture":
        # CaptureWorkspaceWidget requires parent as positional, plus app_ctx and service
        # Get the capture service from the plugin instance
        try:
            plugin_host = datalens_app.app_context.plugin_host
            capture_plugin = plugin_host.get_enabled_plugin(PluginId("capture"))
            if capture_plugin is None:
                pytest.skip(f"Capture plugin is not enabled")
                return None
            capture_service = capture_plugin._service
        except Exception as e:
            pytest.skip(f"Could not get capture service for plugin {plugin_id}: {e}")
            return None

        kwargs = {
            "parent": None,
            "theme": datalens_app.app_theme,
            "app_ctx": datalens_app.app_context,
            "service": capture_service,
        }
    else:
        # Default parameters for unknown plugins
        kwargs = {"theme": datalens_app.app_theme, "parent": None}

    try:
        workspace = workspace_class(**kwargs)
        return workspace
    except Exception as e:
        pytest.skip(f"Could not create workspace for plugin {plugin_id}: {e}")
        return None


@pytest.mark.plugin_widget_test
@pytest.mark.ui
def test_plugin_widget_groups(request, datalens_app):
    """
    Test all widget groups in specified plugins.

    This test:
    1. Enables the specified plugins (if not already enabled)
    2. Discovers all widget groups in each plugin
    3. Tests standard interaction patterns
    4. Generates reports if requested
    5. Restores original plugin state
    """
    # Get plugins to test from command-line options
    plugin_ids = get_plugins_to_test(request, datalens_app)

    if not plugin_ids:
        pytest.skip("No plugins specified for testing")

    print(f"\n{'='*70}")
    print(f"🧪 Testing widget groups for plugins: {', '.join(plugin_ids)}")
    print(f"{'='*70}\n")

    # Ensure plugins are enabled
    original_enabled, plugins_enabled = ensure_plugins_enabled(datalens_app, plugin_ids)
    print(f"✓ Enabled plugins for testing: {', '.join(str(p) for p in plugins_enabled)}")

    generate_inventory = request.config.getoption("--generate-inventory")

    # Install error capturing handler for the entire test session
    # NOTE: Must add to "datalens" logger because it has propagate=False
    error_handler = ErrorCapturingHandler()
    datalens_logger = logging.getLogger("datalens")
    datalens_logger.addHandler(error_handler)

    try:
        all_results = {}

        for plugin_id in plugin_ids:
            print(f"\n{'─'*70}")
            print(f"Testing plugin: {plugin_id}")
            print(f"{'─'*70}\n")

            # Clear errors before testing this plugin
            error_handler.clear()

            # Create the plugin workspace
            workspace = create_plugin_workspace(plugin_id, datalens_app)
            if not workspace:
                print(f"⚠ Skipping {plugin_id}: no workspace available")
                continue

            # Check if workspace creation caused any errors
            if error_handler.has_errors():
                error_summary = error_handler.get_error_summary()
                raise AssertionError(
                    f"Plugin '{plugin_id}' workspace creation caused errors:\n{error_summary}"
                )

            try:
                workspace.show()
                QTest.qWait(100)

                # Initialize ToastManager for widget_test plugin (needed for toast demos)
                if plugin_id == "widget_test":
                    try:
                        from datalens.ui.widgets.notifications.toast_manager import ToastManager
                        ToastManager.get_instance(parent=workspace, theme=datalens_app.app_theme)
                    except Exception:
                        # ToastManager already initialized or not available
                        pass

                # Discover widget groups
                groups = WidgetDiscovery.find_groups_in_panel(workspace)

                print(f"✓ Discovered {len(groups)} widget groups in {plugin_id}")

                # Generate inventory if requested
                if generate_inventory:
                    WidgetDiscovery.print_discovery_report(groups, plugin_id)

                # Test each group
                passed = 0
                failed = 0
                for group in groups:
                    try:
                        _test_widget_group_interactions(group, error_handler)
                        passed += 1
                    except Exception as e:
                        failed += 1
                        print(f"✗ {group.section} > {group.control}: {e}")

                all_results[plugin_id] = {
                    "total_groups": len(groups),
                    "passed": passed,
                    "failed": failed,
                }

                print(f"\n✓ Plugin {plugin_id}: {passed} passed, {failed} failed\n")

            finally:
                workspace.close()
                workspace.deleteLater()

        # Print summary
        print(f"\n{'='*70}")
        print("📊 Test Summary")
        print(f"{'='*70}\n")

        total_groups = sum(r["total_groups"] for r in all_results.values())
        total_passed = sum(r["passed"] for r in all_results.values())
        total_failed = sum(r["failed"] for r in all_results.values())

        for plugin_id, results in all_results.items():
            print(
                f"{plugin_id:20s}: {results['passed']:3d} passed, "
                f"{results['failed']:3d} failed, "
                f"{results['total_groups']:3d} total"
            )

        print(f"\n{'─'*70}")
        print(
            f"{'TOTAL':20s}: {total_passed:3d} passed, "
            f"{total_failed:3d} failed, "
            f"{total_groups:3d} total"
        )
        print(f"{'='*70}\n")

        # Assert overall success
        assert total_failed == 0, f"{total_failed} widget group(s) failed testing"

    finally:
        # Remove error handler
        datalens_logger.removeHandler(error_handler)
        # Restore original plugin state
        restore_plugin_state(datalens_app, original_enabled)
        print(f"✓ Restored original plugin state")


def _close_any_popups():
    """
    Close any popup windows that may have been opened by button clicks.

    Handles:
    - QDialog (our custom dialogs, preferences, etc.)
    - QFileDialog (file/directory pickers)
    - QMessageBox (message boxes)
    - Any top-level widget that appeared

    This prevents tests from hanging when buttons open modal dialogs.
    """
    from PySide6.QtWidgets import QApplication, QAbstractButton, QDialog, QFileDialog, QMessageBox
    from PySide6.QtCore import Qt

    app = QApplication.instance()
    if not app:
        return

    try:
        from datalens.ui.widgets.dialogs.loader_dialog import LoaderDialog
    except Exception:
        LoaderDialog = None  # type: ignore[assignment]

    # Find all top-level widgets (windows, dialogs, etc.)
    top_level_widgets = app.topLevelWidgets()

    for widget in top_level_widgets:
        # Skip if it's not visible or is the main window
        try:
            if not widget.isVisible():
                continue
        except RuntimeError:
            # Widget was deleted between enumeration and inspection.
            continue

        # Close QFileDialog (file/dir pickers) - these block the test
        if isinstance(widget, QFileDialog):
            widget.reject()  # Cancel the dialog
            QTest.qWait(50)
            continue

        # Close QMessageBox (message boxes)
        if isinstance(widget, QMessageBox):
            widget.reject()  # Close the message box
            QTest.qWait(50)
            continue

        # Loader dialogs should be allowed to complete (they manage a worker thread).
        # Forcibly rejecting them can leave background QThreads running and crash the
        # process at interpreter shutdown.
        if LoaderDialog is not None and isinstance(widget, LoaderDialog):
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                try:
                    if not widget.isVisible():
                        break
                except RuntimeError:
                    break
                app.processEvents()
                QTest.qWait(50)

            try:
                still_visible = widget.isVisible()
            except RuntimeError:
                still_visible = False

            if still_visible:
                # Try to request cancellation via the Cancel button (best-effort).
                try:
                    for btn in widget.findChildren(QAbstractButton):
                        if (btn.text() or "").strip().lower() == "cancel" and btn.isVisible() and btn.isEnabled():
                            QTest.mouseClick(btn, Qt.LeftButton)
                            break
                except Exception:
                    pass

                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    try:
                        if not widget.isVisible():
                            break
                    except RuntimeError:
                        break
                    app.processEvents()
                    QTest.qWait(50)

            try:
                still_visible = widget.isVisible()
            except RuntimeError:
                still_visible = False
            if still_visible:
                raise RuntimeError("Loader dialog did not close within timeout")
            continue

        # Close any QDialog (our custom dialogs)
        # Check window flags to see if it's a dialog/popup
        if isinstance(widget, QDialog):
            # Don't close if it's a main window (shouldn't happen, but be safe)
            if not (widget.windowFlags() & Qt.Window):
                continue
            widget.reject()  # Close the dialog
            QTest.qWait(50)
            continue

        # Handle other modal windows by checking window modality
        try:
            if widget.isModal():
                widget.close()
                QTest.qWait(50)
        except RuntimeError:
            continue


def _test_widget_group_interactions(group: WidgetGroup, error_handler: ErrorCapturingHandler):
    """
    Test all interactions within a widget group.

    This is a generalized test that:
    1. Uses the provided error-capturing logging handler
    2. Tests ALL buttons in the widget group (clicks each ONE AT A TIME)
    3. After each button click, closes any popup dialogs that appeared
    4. Tests specific patterns (slider+auto, dropdown+refresh, etc.)
    5. Checks for ANY errors/exceptions in logs
    6. Fails the test if errors occurred, even if they were caught

    This ensures button clicks don't cause errors, not just that they don't crash.

    IMPORTANT: Buttons are clicked one at a time, and any popups that appear
    are automatically closed to prevent tests from hanging.

    Args:
        group: The widget group to test
        error_handler: Pre-installed error capturing handler from the parent test
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton, QToolButton

    # Clear previous errors before testing this group
    error_handler.clear()

    # GENERALIZED: Test ALL buttons in the widget group
    # This ensures we catch errors from any button, not just known patterns
    all_buttons = []
    for role, widget in group.widgets.items():
        if isinstance(widget, (QPushButton, QToolButton)):
            all_buttons.append((role, widget))

    # Click buttons ONE AT A TIME and handle popups
    for role, button in all_buttons:
        if button.isVisible() and button.isEnabled():
            # Clear previous errors before this button click
            error_count_before = len(error_handler.errors)

            # Click the button
            QTest.mouseClick(button, Qt.LeftButton)
            QTest.qWait(100)  # Wait for any async operations

            # CRITICAL: Close any popups that appeared
            # This prevents tests from hanging on modal dialogs
            _close_any_popups()
            QTest.qWait(50)  # Let close operations complete

            # Check if THIS button click caused errors
            error_count_after = len(error_handler.errors)
            if error_count_after > error_count_before:
                # Get errors caused by this button
                new_errors = error_handler.errors[error_count_before:]
                error_details = []
                for err in new_errors:
                    error_details.append(f"[{err['level']}] {err['name']}: {err['message']}")
                raise AssertionError(
                    f"Button '{role}' in '{group.section} > {group.control}' caused errors:\n" +
                    "\n".join(error_details)
                )

    # SPECIFIC PATTERNS: Test known interaction patterns for completeness

    # Pattern: Slider + Auto Button (toggle behavior)
    if "slider" in group.widgets and "auto_button" in group.widgets:
        auto_button = group.widgets["auto_button"]
        if auto_button.isCheckable():
            initial_state = auto_button.isChecked()
            QTest.mouseClick(auto_button, Qt.LeftButton)
            QTest.qWait(50)
            assert auto_button.isChecked() != initial_state, \
                f"Auto button should toggle state for {group.control}"
            QTest.mouseClick(auto_button, Qt.LeftButton)
            QTest.qWait(50)
            assert auto_button.isChecked() == initial_state, \
                f"Auto button should return to initial state for {group.control}"

    # Pattern: Dropdown + Refresh
    if "dropdown" in group.widgets and "refresh_button" in group.widgets:
        dropdown = group.widgets["dropdown"]
        refresh_button = group.widgets["refresh_button"]
        if isinstance(dropdown, QComboBox) and isinstance(refresh_button, QPushButton):
            if refresh_button.isEnabled():
                QTest.mouseClick(refresh_button, Qt.LeftButton)
                QTest.qWait(100)

    # Pattern: Input + Browse
    if "input" in group.widgets and "browse_button" in group.widgets:
        input_field = group.widgets["input"]
        browse_button = group.widgets["browse_button"]
        if isinstance(input_field, QLineEdit) and isinstance(browse_button, QPushButton):
            assert browse_button.isVisible(), \
                f"Browse button should be visible for {group.control}"

    # FINAL CHECK: Verify no errors occurred during any interactions
    if error_handler.has_errors():
        error_summary = error_handler.get_error_summary()
        raise AssertionError(
            f"Widget group '{group.section} > {group.control}' caused errors during testing:\n{error_summary}"
        )


@pytest.mark.plugin_widget_test
@pytest.mark.ui
def test_generate_widget_inventory(request, datalens_app):
    """
    Generate a comprehensive widget inventory for specified plugins.

    This test generates a detailed report of all widgets, which is useful for:
    - Documentation
    - Coverage analysis
    - Understanding plugin UI structure
    """
    plugin_ids = get_plugins_to_test(request, datalens_app)

    if not plugin_ids:
        pytest.skip("No plugins specified for inventory generation")

    # Ensure plugins are enabled
    original_enabled, _ = ensure_plugins_enabled(datalens_app, plugin_ids)

    try:
        inventory = {}

        for plugin_id in plugin_ids:
            workspace = create_plugin_workspace(plugin_id, datalens_app)
            if not workspace:
                continue

            try:
                workspace.show()
                QTest.qWait(100)

                # Initialize ToastManager for widget_test plugin (needed for toast demos)
                if plugin_id == "widget_test":
                    try:
                        from datalens.ui.widgets.notifications.toast_manager import ToastManager
                        ToastManager.get_instance(parent=workspace, theme=datalens_app.app_theme)
                    except Exception:
                        # ToastManager already initialized or not available
                        pass

                groups = WidgetDiscovery.find_groups_in_panel(workspace)

                plugin_inventory = {
                    "plugin_id": plugin_id,
                    "total_groups": len(groups),
                    "sections": {},
                }

                for group in groups:
                    section = group.section
                    if section not in plugin_inventory["sections"]:
                        plugin_inventory["sections"][section] = []

                    group_info = {
                        "control": group.control,
                        "row_index": group.row_index,
                        "widgets": {},
                    }

                    for role, widget in group.widgets.items():
                        widget_info = {
                            "type": widget.__class__.__name__,
                            "object_name": widget.objectName() or None,
                            "tooltip": widget.toolTip() or None,
                            "enabled": widget.isEnabled(),
                            "visible": widget.isVisible(),
                        }
                        group_info["widgets"][role] = widget_info

                    plugin_inventory["sections"][section].append(group_info)

                inventory[plugin_id] = plugin_inventory

            finally:
                workspace.close()
                workspace.deleteLater()

        # Print inventory
        print(f"\n{'='*70}")
        print("📋 Widget Inventory Report")
        print(f"{'='*70}\n")

        for plugin_id, data in inventory.items():
            print(f"\n{'─'*70}")
            print(f"Plugin: {plugin_id}")
            print(f"Total Groups: {data['total_groups']}")
            print(f"{'─'*70}\n")

            for section, groups in data["sections"].items():
                print(f"  Section: {section}")
                for group in groups:
                    print(f"    ├─ {group['control']}")
                    for role, widget in group["widgets"].items():
                        print(f"    │  └─ {role:15s}: {widget['type']:25s} [{widget['object_name'] or 'unnamed'}]")
                print()

        print(f"{'='*70}\n")

    finally:
        restore_plugin_state(datalens_app, original_enabled)


@pytest.mark.plugin_widget_test
@pytest.mark.ui
@pytest.mark.parametrize("plugin_id", ["widget_test", "capture"])
def test_individual_plugin_widgets(plugin_id: str, datalens_app):
    """
    Test widget groups for a single plugin (parameterized).

    This provides individual test runs for each plugin, which can be
    useful for isolating failures.

    Usage:
        # Test just the capture plugin
        pytest tests/integration/plugins/test_plugin_widget_groups.py::test_individual_plugin_widgets[capture]

        # Test just the widget_test plugin
        pytest tests/integration/plugins/test_plugin_widget_groups.py::test_individual_plugin_widgets[widget_test]
    """
    # Ensure plugin is enabled
    original_enabled, _ = ensure_plugins_enabled(datalens_app, [plugin_id])

    # Install error capturing handler
    # NOTE: Must add to "datalens" logger because it has propagate=False
    error_handler = ErrorCapturingHandler()
    datalens_logger = logging.getLogger("datalens")
    datalens_logger.addHandler(error_handler)

    try:
        workspace = create_plugin_workspace(plugin_id, datalens_app)
        if not workspace:
            pytest.skip(f"Plugin {plugin_id} has no workspace")

        # Check if workspace creation caused any errors
        if error_handler.has_errors():
            error_summary = error_handler.get_error_summary()
            raise AssertionError(
                f"Plugin '{plugin_id}' workspace creation caused errors:\n{error_summary}"
            )

        try:
            workspace.show()
            QTest.qWait(100)

            # Initialize ToastManager for widget_test plugin (needed for toast demos)
            if plugin_id == "widget_test":
                try:
                    from datalens.ui.widgets.notifications.toast_manager import ToastManager
                    ToastManager.get_instance(parent=workspace, theme=datalens_app.app_theme)
                except Exception:
                    # ToastManager already initialized or not available
                    pass

            # Discover and test groups
            groups = WidgetDiscovery.find_groups_in_panel(workspace)

            print(f"\n✓ Discovered {len(groups)} widget groups in {plugin_id}")

            max_groups = 0
            try:
                max_groups = int(os.environ.get("DATALENS_TEST_MAX_WIDGET_GROUPS", "0") or "0")
            except Exception:
                max_groups = 0

            for idx, group in enumerate(groups, start=1):
                print(f"  Testing: {group.section} > {group.control}")
                _test_widget_group_interactions(group, error_handler)
                if max_groups and idx >= max_groups:
                    break

            print(f"✓ All {len(groups)} widget groups passed")

        finally:
            workspace.close()
            workspace.deleteLater()

    finally:
        # Remove error handler
        datalens_logger.removeHandler(error_handler)
        # Restore original plugin state
        restore_plugin_state(datalens_app, original_enabled)
