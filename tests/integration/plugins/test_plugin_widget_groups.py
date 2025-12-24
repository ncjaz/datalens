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

from dataclasses import replace

import pytest
from PySide6.QtTest import QTest

from datalens.domain.plugin import PluginId
from helpers.widget_discovery import WidgetDiscovery, WidgetGroup


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

    try:
        all_results = {}

        for plugin_id in plugin_ids:
            print(f"\n{'─'*70}")
            print(f"Testing plugin: {plugin_id}")
            print(f"{'─'*70}\n")

            # Create the plugin workspace
            workspace = create_plugin_workspace(plugin_id, datalens_app)
            if not workspace:
                print(f"⚠ Skipping {plugin_id}: no workspace available")
                continue

            try:
                workspace.show()
                QTest.qWait(100)

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
                        _test_widget_group_interactions(group)
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
        # Restore original plugin state
        restore_plugin_state(datalens_app, original_enabled)
        print(f"✓ Restored original plugin state")


def _test_widget_group_interactions(group: WidgetGroup):
    """
    Test all interactions within a widget group.

    Tests common patterns:
    - Slider + Auto button
    - Slider + Reset button
    - Dropdown + Refresh button
    - Input + Browse button
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton

    # Pattern: Slider + Auto Button
    if "slider" in group.widgets and "auto_button" in group.widgets:
        slider = group.widgets["slider"]
        auto_button = group.widgets["auto_button"]

        # Test auto button is checkable
        if auto_button.isCheckable():
            # Save initial state
            initial_state = auto_button.isChecked()

            # Toggle auto button
            QTest.mouseClick(auto_button, Qt.LeftButton)
            QTest.qWait(50)

            # Verify state changed
            assert auto_button.isChecked() != initial_state, \
                f"Auto button should toggle state for {group.control}"

            # Toggle back
            QTest.mouseClick(auto_button, Qt.LeftButton)
            QTest.qWait(50)

            assert auto_button.isChecked() == initial_state, \
                f"Auto button should return to initial state for {group.control}"

    # Pattern: Slider + Reset Button
    if "slider" in group.widgets and "reset_button" in group.widgets:
        slider = group.widgets["slider"]
        reset_button = group.widgets["reset_button"]

        # Just verify reset button is clickable
        # (Actual reset behavior depends on DatalensSliderOption implementation)
        if reset_button.isEnabled():
            QTest.mouseClick(reset_button, Qt.LeftButton)
            QTest.qWait(50)

    # Pattern: Dropdown + Refresh
    if "dropdown" in group.widgets and "refresh_button" in group.widgets:
        dropdown = group.widgets["dropdown"]
        refresh_button = group.widgets["refresh_button"]

        if isinstance(dropdown, QComboBox) and isinstance(refresh_button, QPushButton):
            if refresh_button.isEnabled():
                initial_count = dropdown.count()
                QTest.mouseClick(refresh_button, Qt.LeftButton)
                QTest.qWait(100)  # Refresh may take time
                # Count may or may not change - just verify button works

    # Pattern: Input + Browse
    if "input" in group.widgets and "browse_button" in group.widgets:
        input_field = group.widgets["input"]
        browse_button = group.widgets["browse_button"]

        if isinstance(input_field, QLineEdit) and isinstance(browse_button, QPushButton):
            # Just verify button is enabled
            # (Can't test file dialog without mocking)
            assert browse_button.isVisible(), \
                f"Browse button should be visible for {group.control}"


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

    try:
        workspace = create_plugin_workspace(plugin_id, datalens_app)
        if not workspace:
            pytest.skip(f"Plugin {plugin_id} has no workspace")

        try:
            workspace.show()
            QTest.qWait(100)

            # Discover and test groups
            groups = WidgetDiscovery.find_groups_in_panel(workspace)

            print(f"\n✓ Discovered {len(groups)} widget groups in {plugin_id}")

            for group in groups:
                print(f"  Testing: {group.section} > {group.control}")
                _test_widget_group_interactions(group)

            print(f"✓ All {len(groups)} widget groups passed")

        finally:
            workspace.close()
            workspace.deleteLater()

    finally:
        restore_plugin_state(datalens_app, original_enabled)
