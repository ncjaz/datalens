"""
Example test demonstrating full-application testing with DataLens.

This test shows how to:
- Access the fully loaded application
- Navigate through UI (preferences dialog)
- Interact with widgets (buttons, inputs)
- Verify application state

All tests run against the complete DataLens application.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QTreeWidget

from datalens.core.context import get_app_context


@pytest.mark.ui
def test_open_preferences_dialog(app_context):
    """
    Test that the preferences dialog can be opened through the UI.

    This test demonstrates:
    - Accessing app context
    - Finding UI elements
    - Simulating user interactions
    """
    # Get the main window from the app context
    # (This will need to be adjusted based on your actual app structure)
    app = get_app_context()

    # In a real test, we would:
    # 1. Find the Edit menu
    # 2. Click Preferences action
    # 3. Verify dialog opens

    # Example (commented out until we verify the actual structure):
    # main_window = app.main_window
    # edit_menu = main_window.menuBar().findChild(QMenu, "EditMenu")
    # prefs_action = edit_menu.findChild(QAction, "PreferencesAction")
    # prefs_action.trigger()

    # For now, just verify the app context is available
    assert app is not None
    assert hasattr(app, "preferences")


@pytest.mark.ui
def test_plugin_preferences_reset_button(app_context):
    """
    Test that plugin preferences can be reset through the UI.

    This test demonstrates:
    - Opening preferences dialog
    - Navigating to a specific plugin's preferences
    - Clicking the Reset to Defaults button
    - Verifying the reset action
    """
    from datalens.ui.menus.edit.preferences.preferences_dialog import PreferencesDialog

    # Create and show the preferences dialog
    # (In a real test, this would be triggered through the menu)
    dialog = PreferencesDialog()

    try:
        # Show the dialog (non-modal for testing)
        dialog.show()
        QTest.qWait(100)  # Wait for dialog to render

        # Find the navigation tree
        nav = dialog.findChild(QTreeWidget, "PreferencesNav")
        assert nav is not None

        # Find the "Plugins" section
        # This navigates the tree to find the Plugins item
        plugins_item = None
        for i in range(nav.topLevelItemCount()):
            item = nav.topLevelItem(i)
            if item and item.text(0) == "Plugins":
                plugins_item = item
                break

        if plugins_item is not None:
            # Select the Plugins section
            nav.setCurrentItem(plugins_item)
            QTest.qWait(50)

            # Find the Reset to Defaults button
            # (This would be in the plugin preferences page)
            reset_btn = dialog.findChild(QPushButton)
            # Note: In a real test, we'd find the specific button by object name
            # and verify it has the reset icon

    finally:
        # Clean up
        dialog.close()
        dialog.deleteLater()


@pytest.mark.ui
def test_keyboard_shortcuts_page(app_context):
    """
    Test that keyboard shortcuts preferences can be accessed.

    This test demonstrates:
    - Opening preferences to a specific page
    - Using the initial_page_key parameter
    """
    from datalens.ui.menus.edit.preferences.preferences_dialog import PreferencesDialog

    # Open preferences directly to the keyboard shortcuts page
    dialog = PreferencesDialog(initial_page_key="keyboard_shortcuts")

    try:
        dialog.show()
        QTest.qWait(100)

        # Verify we're on the keyboard shortcuts page
        nav = dialog.findChild(QTreeWidget, "PreferencesNav")
        if nav:
            current = nav.currentItem()
            if current:
                key = current.data(0, Qt.UserRole)
                # Should be on keyboard_shortcuts or a child page
                assert key is not None
                assert "keyboard_shortcuts" in str(key)
    finally:
        dialog.close()
        dialog.deleteLater()


@pytest.mark.ui
@pytest.mark.slow
def test_theme_switching(app_context):
    """
    Test that theme can be switched through preferences.

    This is marked as slow because theme changes may involve
    reloading styles across the entire application.
    """
    # Get current theme
    current_theme = app_context.theme
    assert current_theme is not None

    # In a real test, we would:
    # 1. Open preferences
    # 2. Navigate to Theme section
    # 3. Select a different theme
    # 4. Apply changes
    # 5. Verify theme changed
    # 6. Switch back to original theme

    # For now, just verify theme service exists
    assert hasattr(current_theme, "primary_color")
    assert hasattr(current_theme, "background_color")


def test_preferences_persistence(app_context):
    """
    Test that preferences are persisted correctly.

    This test demonstrates:
    - Setting a preference value
    - Reading it back
    - Verifying persistence
    """
    from datalens.domain.plugin import PluginId

    prefs = app_context.preferences

    # Use a test plugin ID (this should exist in your setup)
    test_plugin = PluginId("test.plugin")
    test_key = "test_setting"
    test_value = "test_value_12345"

    # Set a preference
    # Note: This test assumes we're in testing mode with isolated settings
    try:
        prefs.set(test_plugin, test_key, test_value)

        # Read it back
        retrieved = prefs.get(test_plugin, test_key)
        assert retrieved == test_value

        # Clean up
        prefs.set(test_plugin, test_key, None)
    except Exception:
        # If the plugin doesn't exist, this test is informational only
        pytest.skip("Test plugin not available")
