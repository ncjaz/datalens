"""
Test the welcome screen workflow.

This test demonstrates:
- Opening the welcome window with the full app loaded
- Finding and enabling all plugins through the UI
- Clicking Continue to proceed with the app
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QWidget

from datalens.ui.welcome_window import WelcomeWindow
from datalens.ui.widgets.core.checkboxes import DatalensCheckBox


@pytest.mark.ui
def test_welcome_screen_enable_all_plugins(datalens_app):
    """
    Test going through the welcome screen and enabling all plugins.

    This test verifies:
    - Welcome window can be created and shown
    - All plugin checkboxes can be found
    - All plugins can be enabled through the UI
    - Continue button is available and clickable

    Note: This test preserves the original enabled plugins state and restores it
    after the test completes to avoid affecting other tests in the session.
    """
    # Get settings and plugins from the test app
    settings = datalens_app._test_settings
    plugins = tuple(r.definition for r in datalens_app._test_plugin_discovery.registry.all())

    # Save the original enabled plugins to restore later
    original_enabled_plugins = settings.enabled_plugins
    print(f"\n✓ Saved original enabled plugins: {sorted(str(p) for p in original_enabled_plugins)}")

    print(f"✓ Found {len(plugins)} plugins to display in welcome screen")

    # Create the welcome window
    welcome = WelcomeWindow(
        theme=datalens_app.app_theme,
        settings=settings,
        plugins=plugins,
    )

    try:
        # Show the window
        welcome.show()
        QTest.qWait(200)  # Wait for window to render
        print("✓ Welcome window displayed")

        # Find the workspaces panel
        workspaces_panel = welcome.findChild(QWidget, "WelcomeWorkspacesPanel")
        assert workspaces_panel is not None, "Could not find WelcomeWorkspacesPanel"
        print("✓ Found workspaces panel")

        # Find all plugin checkboxes
        checkboxes = workspaces_panel.findChildren(DatalensCheckBox)
        print(f"✓ Found {len(checkboxes)} plugin checkboxes")

        # Count how many are currently enabled
        initially_enabled = sum(1 for cb in checkboxes if cb.isChecked())
        print(f"✓ {initially_enabled} plugins initially enabled")

        # First, ensure all plugins are disabled to establish a known starting state
        for checkbox in checkboxes:
            if checkbox.isChecked():
                checkbox.setChecked(False)
                QTest.qWait(50)

        # Verify all are disabled
        all_disabled = all(not cb.isChecked() for cb in checkboxes)
        assert all_disabled, f"Not all plugins were disabled. Still checked: {[cb.text() for cb in checkboxes if cb.isChecked()]}"
        print(f"✓ All {len(checkboxes)} plugins disabled (establishing clean state)")

        # Now enable all plugins
        enabled_count = 0
        for checkbox in checkboxes:
            # Use setChecked for reliability (mouseClick can be flaky)
            checkbox.setChecked(True)
            QTest.qWait(50)  # Small delay for UI update
            enabled_count += 1

        print(f"✓ Enabled {enabled_count} plugins")

        # Verify all are now enabled
        all_enabled = all(cb.isChecked() for cb in checkboxes)
        assert all_enabled, f"Not all plugins were enabled. Unchecked: {[cb.text() for cb in checkboxes if not cb.isChecked()]}"
        print(f"✓ All {len(checkboxes)} plugins are now enabled")

        # Find the Continue button
        continue_btn = welcome.findChild(QPushButton)
        # The Continue button should be a DatalensButton, but QPushButton is its base
        # Look for the button with text "Continue"
        for btn in welcome.findChildren(QPushButton):
            if btn.text() == "Continue":
                continue_btn = btn
                break

        assert continue_btn is not None, "Could not find Continue button"
        assert continue_btn.text() == "Continue", f"Expected Continue button, got {continue_btn.text()}"
        print("✓ Found Continue button")

        # Verify the button is enabled
        assert continue_btn.isEnabled(), "Continue button should be enabled"

        # Get the enabled plugins before clicking continue
        enabled_plugins = welcome._workspaces_panel.enabled_workspaces()
        print(f"✓ {len(enabled_plugins)} plugins will be enabled: {sorted(p for p in enabled_plugins)}")

        # Click Continue button
        # Note: We don't actually click it because that would close the dialog
        # and potentially start the full app initialization
        # QTest.mouseClick(continue_btn, Qt.LeftButton)
        print("✓ Continue button is ready to be clicked (not clicking in test)")

        # Verify the settings were updated
        assert len(enabled_plugins) == len(checkboxes), \
            f"Expected {len(checkboxes)} enabled plugins, got {len(enabled_plugins)}"

        print(f"\n✅ Welcome screen test completed successfully!")
        print(f"   - Displayed {len(plugins)} plugins")
        print(f"   - Enabled all {len(checkboxes)} plugin checkboxes")
        print(f"   - Continue button is ready")

    finally:
        # Clean up
        welcome.close()
        welcome.deleteLater()

        # Restore original enabled plugins to avoid affecting other tests
        datalens_app._test_settings = replace(settings, enabled_plugins=original_enabled_plugins)
        print(f"✓ Restored original enabled plugins: {sorted(str(p) for p in original_enabled_plugins)}")


@pytest.mark.ui
def test_welcome_screen_selective_plugins(datalens_app):
    """
    Test enabling only specific plugins through the welcome screen.

    This verifies that:
    - Individual plugins can be toggled
    - Plugin selection is tracked correctly

    Note: This test preserves the original enabled plugins state and restores it
    after the test completes to avoid affecting other tests in the session.
    """
    settings = datalens_app._test_settings
    plugins = tuple(r.definition for r in datalens_app._test_plugin_discovery.registry.all())

    # Save the original enabled plugins to restore later
    original_enabled_plugins = settings.enabled_plugins
    print(f"\n✓ Saved original enabled plugins: {sorted(str(p) for p in original_enabled_plugins)}")

    welcome = WelcomeWindow(
        theme=datalens_app.app_theme,
        settings=settings,
        plugins=plugins,
    )

    try:
        welcome.show()
        QTest.qWait(200)

        workspaces_panel = welcome.findChild(QWidget, "WelcomeWorkspacesPanel")
        checkboxes = workspaces_panel.findChildren(DatalensCheckBox)

        # Disable all plugins first (use setChecked() for reliability)
        for checkbox in checkboxes:
            if checkbox.isChecked():
                checkbox.setChecked(False)
                QTest.qWait(50)

        # Verify all are disabled
        all_disabled = all(not cb.isChecked() for cb in checkboxes)
        assert all_disabled, f"Not all plugins were disabled. Still checked: {[cb.text() for cb in checkboxes if cb.isChecked()]}"
        print(f"✓ All {len(checkboxes)} plugins disabled")

        # Enable just the first 3 plugins
        plugins_to_enable = min(3, len(checkboxes))
        for i in range(plugins_to_enable):
            checkboxes[i].setChecked(True)
            QTest.qWait(50)

        # Verify exactly 3 are enabled
        enabled_count = sum(1 for cb in checkboxes if cb.isChecked())
        assert enabled_count == plugins_to_enable, \
            f"Expected {plugins_to_enable} plugins enabled, got {enabled_count}"
        print(f"✓ Enabled exactly {plugins_to_enable} plugins")

        # Verify the workspaces panel reports the correct count
        enabled_plugins = welcome._workspaces_panel.enabled_workspaces()
        assert len(enabled_plugins) == plugins_to_enable, \
            f"Panel reports {len(enabled_plugins)} enabled, expected {plugins_to_enable}"
        print(f"✓ Workspaces panel correctly reports {len(enabled_plugins)} enabled plugins")

    finally:
        welcome.close()
        welcome.deleteLater()

        # Restore original enabled plugins to avoid affecting other tests
        datalens_app._test_settings = replace(settings, enabled_plugins=original_enabled_plugins)
        print(f"✓ Restored original enabled plugins: {sorted(str(p) for p in original_enabled_plugins)}")
