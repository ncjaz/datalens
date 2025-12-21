"""
Helper utilities for comprehensive workflow testing.

These helpers enable complex workflows like:
- App restarts with different plugin configurations
- File menu interactions (Quit, Restart, Open Recent)
- Main window navigation between plugins
- Project creation and loading workflows
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget, QPushButton, QMenu

if TYPE_CHECKING:
    from datalens.ui.welcome_window import WelcomeWindow
    from datalens.ui.main_window import MainWindow


class WelcomeScreenHelper:
    """Helper for interacting with the welcome screen."""

    def __init__(self, welcome: WelcomeWindow):
        self.welcome = welcome

    def find_quit_button(self) -> QPushButton | None:
        """Find the Quit button."""
        for btn in self.welcome.findChildren(QPushButton):
            if btn.text() == "Quit":
                return btn
        return None

    def find_continue_button(self) -> QPushButton | None:
        """Find the Continue button."""
        for btn in self.welcome.findChildren(QPushButton):
            if btn.text() == "Continue":
                return btn
        return None

    def click_quit(self) -> None:
        """Click the Quit button."""
        btn = self.find_quit_button()
        assert btn is not None, "Could not find Quit button"
        QTest.mouseClick(btn, Qt.LeftButton)
        QTest.qWait(50)

    def click_continue(self) -> None:
        """Click the Continue button to proceed with app launch."""
        btn = self.find_continue_button()
        assert btn is not None, "Could not find Continue button"
        assert btn.isEnabled(), "Continue button is not enabled"
        QTest.mouseClick(btn, Qt.LeftButton)
        QTest.qWait(100)

    def get_workspaces_panel(self) -> QWidget:
        """Get the workspaces panel widget."""
        panel = self.welcome.findChild(QWidget, "WelcomeWorkspacesPanel")
        assert panel is not None, "Could not find WelcomeWorkspacesPanel"
        return panel

    def get_plugin_checkboxes(self):
        """Get all plugin checkbox widgets."""
        from datalens.ui.widgets.core.checkboxes import DatalensCheckBox
        panel = self.get_workspaces_panel()
        return panel.findChildren(DatalensCheckBox)

    def enable_plugins(self, plugin_indices: list[int]) -> None:
        """
        Enable only the specified plugins by index.

        Args:
            plugin_indices: List of indices of plugins to enable (0-based)
        """
        checkboxes = self.get_plugin_checkboxes()
        for i, cb in enumerate(checkboxes):
            cb.setChecked(i in plugin_indices)
            QTest.qWait(10)

    def enable_all_plugins(self) -> None:
        """Enable all plugins."""
        checkboxes = self.get_plugin_checkboxes()
        for cb in checkboxes:
            cb.setChecked(True)
            QTest.qWait(10)

    def disable_all_plugins(self) -> None:
        """Disable all plugins."""
        checkboxes = self.get_plugin_checkboxes()
        for cb in checkboxes:
            cb.setChecked(False)
            QTest.qWait(10)

    def get_enabled_plugins(self) -> frozenset[str]:
        """Get the set of currently enabled plugin IDs."""
        return self.welcome._workspaces_panel.enabled_workspaces()

    def verify_plugin_count(self, expected_count: int) -> None:
        """Verify the number of enabled plugins."""
        enabled = self.get_enabled_plugins()
        actual_count = len(enabled)
        assert actual_count == expected_count, \
            f"Expected {expected_count} plugins enabled, got {actual_count}"


class MainWindowHelper:
    """Helper for interacting with the main window."""

    def __init__(self, main_window: MainWindow):
        self.main_window = main_window

    def get_file_menu(self) -> QMenu | None:
        """Get the File menu."""
        menubar = self.main_window.menuBar()
        if menubar is None:
            return None

        for action in menubar.actions():
            menu = action.menu()
            if menu and menu.title() == "&File":
                return menu
        return None

    def find_menu_action(self, menu: QMenu, action_text: str) -> QAction | None:
        """Find a menu action by text."""
        for action in menu.actions():
            if action.text() == action_text:
                return action
        return None

    def trigger_file_menu_action(self, action_text: str) -> None:
        """
        Trigger a File menu action by text.

        Args:
            action_text: The text of the action (e.g., "Quit", "Restart")
        """
        file_menu = self.get_file_menu()
        assert file_menu is not None, "Could not find File menu"

        action = self.find_menu_action(file_menu, action_text)
        assert action is not None, f"Could not find action '{action_text}' in File menu"

        action.trigger()
        QTest.qWait(50)

    def file_quit(self) -> None:
        """File → Quit"""
        self.trigger_file_menu_action("Quit")

    def file_restart(self) -> None:
        """File → Restart"""
        self.trigger_file_menu_action("Restart")

    def file_new_project(self) -> None:
        """File → New Project"""
        self.trigger_file_menu_action("New Project\u2026")

    def file_open_project(self) -> None:
        """File → Open Project"""
        self.trigger_file_menu_action("Open Project\u2026")

    def file_close_project(self) -> None:
        """File → Close Project"""
        self.trigger_file_menu_action("Close Project")

    def file_open_recent_project(self, project_path: Path) -> None:
        """
        File → Recent Projects → [select project]

        Args:
            project_path: Path to the project to open
        """
        file_menu = self.get_file_menu()
        assert file_menu is not None, "Could not find File menu"

        # Find Recent Projects submenu
        recent_menu = None
        for action in file_menu.actions():
            submenu = action.menu()
            if submenu and submenu.title() == "Recent Projects":
                recent_menu = submenu
                break

        assert recent_menu is not None, "Could not find Recent Projects menu"

        # Trigger the menu to populate it
        recent_menu.aboutToShow.emit()
        QTest.qWait(50)

        # Find the action for this project
        project_str = str(project_path)
        for action in recent_menu.actions():
            if action.text() == project_str:
                action.trigger()
                QTest.qWait(100)
                return

        raise AssertionError(f"Could not find project '{project_str}' in Recent Projects menu")

    def get_workspace_tabs(self) -> list[QWidget]:
        """Get all workspace tab widgets (one per plugin)."""
        # TODO: Implement based on actual main window structure
        # This will need to find the tab widget or workspace switcher
        # and return the list of plugin workspace widgets
        return []

    def switch_to_plugin(self, plugin_index: int) -> None:
        """
        Switch to a plugin's workspace by index.

        Args:
            plugin_index: Index of the plugin to switch to (0-based)
        """
        # TODO: Implement based on actual main window structure
        # This will need to click the tab or use the workspace switcher
        # to navigate to the specified plugin
        pass

    def verify_plugin_accessible(self, plugin_index: int) -> None:
        """
        Verify that a plugin's workspace is accessible without error.

        Args:
            plugin_index: Index of the plugin to verify (0-based)
        """
        # TODO: Implement based on actual main window structure
        # This should switch to the plugin and verify no exceptions
        # and that the workspace widget is visible
        pass


class ProjectHelper:
    """Helper for project creation and management during tests."""

    @staticmethod
    def create_test_project(project_root: Path, name: str = "Test Project") -> None:
        """
        Create a minimal test project.

        Args:
            project_root: Directory where the project should be created
            name: Name of the project
        """
        import json

        project_root.mkdir(parents=True, exist_ok=True)
        project_file = project_root / "project.json"
        project_data = {
            "name": name,
            "version": "1.0",
            "created": "2025-12-20",
        }
        project_file.write_text(json.dumps(project_data, indent=2))

    @staticmethod
    def delete_test_project(project_root: Path) -> None:
        """
        Delete a test project.

        Args:
            project_root: Directory of the project to delete
        """
        import shutil

        if project_root.exists():
            shutil.rmtree(project_root)


def wait_for_condition(condition_func, timeout_ms: int = 5000, check_interval_ms: int = 100) -> bool:
    """
    Wait for a condition to become true.

    Args:
        condition_func: Function that returns True when condition is met
        timeout_ms: Maximum time to wait in milliseconds
        check_interval_ms: How often to check the condition in milliseconds

    Returns:
        True if condition met, False if timeout

    Example:
        >>> success = wait_for_condition(lambda: widget.isVisible(), timeout_ms=2000)
        >>> assert success, "Widget failed to become visible"
    """
    import time

    start = time.time()
    while (time.time() - start) * 1000 < timeout_ms:
        try:
            if condition_func():
                return True
        except Exception:
            # Condition check failed, keep waiting
            pass
        QTest.qWait(check_interval_ms)
    return False


class EventWatcher:
    """
    Helper for waiting on DataLens events during testing.

    This allows tests to verify that events are emitted correctly
    when actions are performed.

    Example:
        >>> from datalens.core.context import get_app_context
        >>> app_ctx = get_app_context()
        >>> watcher = EventWatcher(app_ctx)
        >>> watcher.watch("capture.streaming_started")
        >>> click_start_button()
        >>> watcher.assert_received("capture.streaming_started", timeout_ms=3000)
    """

    def __init__(self, app_context):
        self.app_ctx = app_context
        self.received_events: dict[str, bool] = {}
        self.event_data: dict[str, object] = {}
        self._subscriptions: dict[str, object] = {}  # Store Subscription objects

    def watch(self, event_name: str) -> None:
        """
        Start watching for an event.

        Args:
            event_name: Name of the event to watch (e.g., "capture.streaming_started")
        """

        def handler(event):
            self.received_events[event_name] = True
            self.event_data[event_name] = event

        # subscribe() returns a Subscription object with unsubscribe() method
        subscription = self.app_ctx.events.subscribe(event_name, handler)
        self._subscriptions[event_name] = subscription
        self.received_events[event_name] = False

    def wait_for(self, event_name: str, timeout_ms: int = 5000) -> bool:
        """
        Wait for an event to be received.

        Args:
            event_name: Name of the event to wait for
            timeout_ms: Maximum time to wait in milliseconds

        Returns:
            True if event received, False if timeout
        """
        return wait_for_condition(lambda: self.received_events.get(event_name, False), timeout_ms=timeout_ms)

    def assert_received(self, event_name: str, timeout_ms: int = 5000) -> None:
        """
        Assert that event was received within timeout.

        Args:
            event_name: Name of the event that should have been received
            timeout_ms: Maximum time to wait in milliseconds

        Raises:
            AssertionError: If event not received within timeout
        """
        success = self.wait_for(event_name, timeout_ms)
        assert success, f"Event '{event_name}' not received within {timeout_ms}ms"

    def get_event_data(self, event_name: str) -> object | None:
        """
        Get the data from a received event.

        Args:
            event_name: Name of the event

        Returns:
            Event data if event was received, None otherwise
        """
        return self.event_data.get(event_name)

    def was_received(self, event_name: str) -> bool:
        """
        Check if an event was received (without waiting).

        Args:
            event_name: Name of the event

        Returns:
            True if event was received, False otherwise
        """
        return self.received_events.get(event_name, False)

    def cleanup(self) -> None:
        """Unsubscribe all event handlers. Call this in test cleanup."""
        for event_name, subscription in self._subscriptions.items():
            subscription.unsubscribe()
        self._subscriptions.clear()


class StateWatcher:
    """
    Helper for monitoring DataLens state during testing.

    This allows tests to verify that state changes correctly
    when actions are performed.

    Example:
        >>> from datalens.core.context import get_app_context
        >>> app_ctx = get_app_context()
        >>> watcher = StateWatcher(app_ctx)
        >>> click_start_button()
        >>> watcher.assert_state(lambda s: s.capture.is_streaming, timeout_ms=3000)
    """

    def __init__(self, app_context):
        self.app_ctx = app_context

    def wait_for_state(self, condition_func, timeout_ms: int = 5000) -> bool:
        """
        Wait for a state condition to become true.

        Args:
            condition_func: Function that takes state snapshot and returns bool
            timeout_ms: Maximum time to wait in milliseconds

        Returns:
            True if condition met, False if timeout

        Example:
            >>> watcher.wait_for_state(lambda s: s.capture.is_streaming, timeout_ms=3000)
        """
        return wait_for_condition(
            lambda: condition_func(self.app_ctx.workspace_state.snapshot()), timeout_ms=timeout_ms
        )

    def assert_state(self, condition_func, timeout_ms: int = 5000, message: str = "") -> None:
        """
        Assert that state condition becomes true within timeout.

        Args:
            condition_func: Function that takes state snapshot and returns bool
            timeout_ms: Maximum time to wait in milliseconds
            message: Custom error message if assertion fails

        Raises:
            AssertionError: If condition not met within timeout
        """
        success = self.wait_for_state(condition_func, timeout_ms)
        assert success, message or f"State condition not met within {timeout_ms}ms"

    def get_snapshot(self):
        """
        Get current state snapshot.

        Returns:
            Current workspace state snapshot
        """
        return self.app_ctx.workspace_state.snapshot()


__all__ = [
    "WelcomeScreenHelper",
    "MainWindowHelper",
    "ProjectHelper",
    "EventWatcher",
    "StateWatcher",
    "wait_for_condition",
]
