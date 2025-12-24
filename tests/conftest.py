"""
pytest configuration for DataLens full-application testing.

This module provides fixtures that initialize the complete DataLens application
for testing. All tests in this suite run against the fully loaded application.

IMPORTANT: All tests require the full DataLens application to be loaded.
Individual widget testing is NOT supported - tests must interact with the
complete application through UI actions (clicks, keyboard, etc.).

TESTING MODE: Tests run in an isolated environment with:
- Separate settings.json (copy of user settings or fresh defaults)
- Test projects created in temporary directory
- Automatic cleanup on completion (unless keep_test_data flag is set)
- User's actual data is never modified
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Generator

import pytest
from PySide6.QtWidgets import QApplication

# Ensure datalens package is importable
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Import testing mode utilities
from fixtures.testing_mode import (
    TestingEnvironment,
    TestingEnvironmentConfig,
    isolated_test_environment,
)


@pytest.fixture(scope="session")
def test_environment() -> Generator[TestingEnvironment, None, None]:
    """
    Session-scoped testing environment with isolated settings and projects.

    This fixture creates an isolated testing environment that:
    - Uses a temporary directory for all test data
    - Provides isolated settings.json (fresh defaults, not user settings)
    - Creates test projects in a temporary location
    - Automatically cleans up after tests complete

    To preserve test data for debugging, set DATALENS_KEEP_TEST_DATA=1.

    Usage:
        def test_something(test_environment):
            # test_environment.settings_path -> isolated settings
            # test_environment.test_project_root -> test project location
    """
    # Check environment variable for keeping test data
    keep_test_data = os.environ.get("DATALENS_KEEP_TEST_DATA", "0") == "1"

    config = TestingEnvironmentConfig(
        copy_user_settings=False,  # Start with fresh settings for tests
        keep_test_data=keep_test_data,
        test_project_name="datalens_test_project",
    )

    with isolated_test_environment(config) as env:
        # Set environment variables so DataLens uses isolated paths
        original_env = {}
        for key, value in env.get_settings_override_env().items():
            original_env[key] = os.environ.get(key)
            os.environ[key] = value

        yield env

        # Restore original environment variables
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="session")
def qapp(test_environment: TestingEnvironment) -> Generator[QApplication, None, None]:
    """
    Session-scoped QApplication instance (actually DatalensApplication).

    This creates the DatalensApplication which initializes the AppContext.
    Required for all Qt-based tests.
    """
    from datalens.core.logging import init_logging
    from datalens.ui.application import DatalensApplication
    from datalens.ui.theme import AppTheme
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont
    from PySide6.QtWidgets import QColorDialog, QFileDialog, QFontDialog, QInputDialog, QMessageBox
    import logging
    import traceback

    # Initialize logging for tests
    init_logging(log_to_file=False)  # Don't write log files during tests

    # Fail the test session if the app logs an unhandled Qt event.
    # `DatalensApplication.notify()` catches and logs these via `datalens.crash`
    # so they don't naturally fail pytest unless we explicitly guard.
    crash_records: list[tuple[str, str | None]] = []

    class _CrashCapture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
            try:
                msg = record.getMessage()
            except Exception:
                msg = "<unformattable LogRecord>"
            tb = None
            try:
                if record.exc_info:
                    tb = "".join(traceback.format_exception(*record.exc_info))
            except Exception:
                tb = None
            crash_records.append((msg, tb))

    crash_logger = logging.getLogger("datalens.crash")
    crash_handler = _CrashCapture(level=logging.ERROR)
    crash_logger.addHandler(crash_handler)
    crash_logger.propagate = True

    # Prevent native OS dialogs (e.g., Windows folder picker) from blocking tests.
    # Native dialogs are not Qt widgets and can't be closed by `_close_any_popups()`.
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)

    # Prevent *any* modal file dialogs from blocking automated tests.
    # The static convenience APIs (e.g. `QFileDialog.getExistingDirectory`) are
    # synchronous and will hang the test runner until the user interacts.
    try:
        QFileDialog.getExistingDirectory = staticmethod(lambda *args, **kwargs: "")
        QFileDialog.getOpenFileName = staticmethod(lambda *args, **kwargs: ("", ""))
        QFileDialog.getOpenFileNames = staticmethod(lambda *args, **kwargs: ([], ""))
        QFileDialog.getSaveFileName = staticmethod(lambda *args, **kwargs: ("", ""))
    except Exception:
        pass

    # Prevent other common modal dialogs from blocking automated tests.
    # These static convenience APIs are synchronous (they spin a nested event loop)
    # and will hang until the user interacts.
    try:
        QMessageBox.information = staticmethod(lambda *args, **kwargs: QMessageBox.Ok)
        QMessageBox.warning = staticmethod(lambda *args, **kwargs: QMessageBox.Ok)
        QMessageBox.critical = staticmethod(lambda *args, **kwargs: QMessageBox.Ok)
        # Default to "No" for confirmation prompts unless a default button is provided.
        def _question(*args, **kwargs):
            default_button = kwargs.get("defaultButton")
            if default_button is not None:
                return default_button
            return QMessageBox.No

        QMessageBox.question = staticmethod(_question)
    except Exception:
        pass

    try:
        QInputDialog.getText = staticmethod(lambda *args, **kwargs: ("", False))
        QInputDialog.getInt = staticmethod(lambda *args, **kwargs: (0, False))
        QInputDialog.getDouble = staticmethod(lambda *args, **kwargs: (0.0, False))
        QInputDialog.getItem = staticmethod(lambda *args, **kwargs: ("", False))
    except Exception:
        pass

    try:
        QColorDialog.getColor = staticmethod(lambda *args, **kwargs: QColor())
        QFontDialog.getFont = staticmethod(lambda *args, **kwargs: (QFont(), False))
    except Exception:
        pass

    # Create theme and DatalensApplication
    # This will create the AppContext automatically
    theme = AppTheme()
    app = DatalensApplication(sys.argv, theme=theme, slow_event_threshold_ms=0)  # Disable slow event logging in tests

    yield app

    # Cleanup
    try:
        crash_logger.removeHandler(crash_handler)
    except Exception:
        pass

    # Ensure UI windows are closed cleanly to avoid PySide/Qt teardown crashes.
    try:
        from PySide6.QtTest import QTest

        app.closeAllWindows()
        app.processEvents()
        QTest.qWait(100)
        app.processEvents()
    except Exception:
        pass

    # Stop the shared settings writer thread (started by many UI flows).
    try:
        from datalens.services.settings_store import default_debounced_settings_writer

        default_debounced_settings_writer().close()
    except Exception:
        pass

    # Ensure Qt threadpool work is drained before interpreter teardown.
    try:
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().waitForDone(2000)
    except Exception:
        pass

    # Ensure crash handler file handles are released so test temp dirs can be removed.
    try:
        from datalens.ui.diagnostics.crash_handlers import shutdown_crash_handlers

        shutdown_crash_handlers()
    except Exception:
        pass

    if crash_records:
        lines: list[str] = ["Unhandled Qt event(s) were logged during the test run:"]
        for i, (msg, tb) in enumerate(crash_records[:3], start=1):
            lines.append(f"- {i}. {msg}")
            if tb:
                lines.append(tb)
        if len(crash_records) > 3:
            lines.append(f"(and {len(crash_records) - 3} more)")
        raise AssertionError("\n".join(lines))

    try:
        if hasattr(app, "app_context"):
            # Close IO writer
            try:
                app.app_context.io.close(flush=True, timeout_seconds=2.0)
            except Exception:
                pass
    except Exception:
        pass


@pytest.fixture(scope="session")
def datalens_app(qapp: QApplication, test_environment: TestingEnvironment) -> Generator[object, None, None]:
    """
    Session-scoped DataLens application instance.

    This fixture initializes the complete DataLens application once for the
    entire test session in an isolated testing environment. All tests share
    this application instance.

    The application is fully initialized with:
    - Plugin system
    - Preferences/settings (isolated from user's actual settings)
    - Keyboard shortcuts
    - Theme system
    - Event bus
    - All enabled plugins loaded

    IMPORTANT: The app runs in testing mode with isolated settings and projects.
    User's actual data is never modified.

    Usage:
        def test_something(datalens_app):
            # datalens_app is the fully loaded application
            # You can access app_context through get_app_context()
            from datalens.core.context import get_app_context
            ctx = get_app_context()
            # Now interact with the app through UI actions
    """
    from pathlib import Path
    from datalens.services.config_service import load_settings
    from datalens.services.plugins import discover_plugins
    from datalens.services.plugins.runtime.host import PluginHost
    from datalens.infra.paths import datalens_user_data_dir

    # qapp is already a DatalensApplication with AppContext initialized
    app = qapp

    # Load settings from isolated environment
    settings = load_settings()

    # Discover plugins
    try:
        user_data_root = getattr(settings, "user_data_dir", None) or datalens_user_data_dir()
        plugin_discovery = discover_plugins(user_plugins_root_dir=Path(user_data_root) / "plugins")
    except Exception:
        plugin_discovery = discover_plugins()

    # Apply plugin metadata overrides
    try:
        plugin_discovery.registry.apply_definition_overrides(getattr(settings, "plugin_overrides", {}) or {})
    except Exception:
        pass

    # Create plugin host and attach to app context
    plugin_host = PluginHost(plugin_discovery.registry)
    app.app_context.plugin_host = plugin_host

    # Apply settings to shortcuts and preferences
    try:
        app.app_context.shortcuts.apply_settings(settings)
    except Exception:
        pass

    try:
        app.app_context.preferences.apply_settings(settings)
    except Exception:
        pass

    # Apply theme settings
    try:
        from datalens.domain.system.settings import AppSettings
        if isinstance(settings, AppSettings):
            app.app_theme.set_opacity(settings.theme_opacity)
            app.app_theme.set_settings(getattr(settings, "theme_settings", app.app_theme.settings))
    except Exception:
        pass

    # Store settings and plugin info for tests to access
    app._test_settings = settings
    app._test_plugin_discovery = plugin_discovery
    app._test_plugin_host = plugin_host

    yield app

    # Check if we should keep the app open for manual inspection
    keep_open = os.environ.get("DATALENS_TEST_KEEP_APP_OPEN", "0") == "1"
    if keep_open:
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtCore import QTimer

        def show_completion_dialog():
            msg = QMessageBox()
            msg.setWindowTitle("DataLens Tests Complete")
            msg.setText("All tests have finished running.\n\n"
                       "The DataLens application is still loaded.\n"
                       "You can inspect the application state, open dialogs, etc.\n\n"
                       "Click OK to close the application.")
            msg.setIcon(QMessageBox.Information)
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
            app.quit()

        # Show dialog after a short delay to let pytest finish printing
        QTimer.singleShot(500, show_completion_dialog)
        app.exec()  # Run the event loop

    # Cleanup: shutdown plugins
    try:
        if hasattr(app, "_test_plugin_host") and app._test_plugin_host is not None:
            app._test_plugin_host.shutdown(app_ctx=app.app_context)
    except Exception:
        pass


@pytest.fixture(scope="function")
def app_context(datalens_app: object) -> object:
    """
    Function-scoped fixture providing access to the app context.

    This is a convenience fixture that gives tests direct access to the
    application context without needing to import get_app_context.

    Usage:
        def test_preferences(app_context):
            prefs = app_context.preferences
            assert prefs is not None
    """
    from datalens.core.context import get_app_context
    return get_app_context()


@pytest.fixture(scope="function")
def main_window(datalens_app: object):
    """
    Function-scoped fixture providing access to the main window.

    This fixture provides the application's main window for UI testing.
    Tests can use this to find widgets, trigger actions, etc.

    Note: The main window is only created when explicitly shown (e.g., in datalens.app.main()).
    For most tests, you should create dialogs/widgets directly instead of relying on
    the main window. This fixture may return None if the main window hasn't been created.

    Usage:
        def test_menu_action(main_window):
            if main_window is None:
                pytest.skip("Main window not available in test mode")
            # Find a menu action
            edit_menu = main_window.findChild(QMenu, "EditMenu")
            assert edit_menu is not None
    """
    if hasattr(datalens_app, "_main_window"):
        return datalens_app._main_window
    return None


@pytest.fixture(scope="function")
def test_project_root(test_environment: TestingEnvironment) -> Path:
    """
    Function-scoped fixture providing the test project root path.

    This is where tests should create projects through the UI.
    The directory is cleaned up automatically after tests complete
    (unless DATALENS_KEEP_TEST_DATA=1).

    Usage:
        def test_create_project(test_project_root):
            # Use UI to create project at test_project_root
            # Example: File -> New Project -> test_project_root
            assert test_project_root.exists()
    """
    return test_environment.test_project_root


@pytest.fixture(scope="function")
def project_lifecycle(app_context, test_project_root: Path):
    """
    Fixture for testing project load/unload workflows.

    This fixture provides a controlled environment for testing:
    1. No project loaded initially
    2. Load a project
    3. Unload the project
    4. Verify clean state after unload

    Usage:
        def test_project_workflow(project_lifecycle):
            # Phase 1: No project loaded
            assert project_lifecycle.current_project is None

            # Phase 2: Load project through UI
            project_lifecycle.load_project(test_project_root)
            assert project_lifecycle.current_project is not None

            # Phase 3: Unload project
            project_lifecycle.unload_project()
            assert project_lifecycle.current_project is None
            # Verify everything cleaned up correctly
    """
    class ProjectLifecycleHelper:
        def __init__(self, app_ctx, project_root: Path):
            self.app_context = app_ctx
            self.project_root = project_root
            self._current_project = None

        @property
        def current_project(self):
            """Get the currently loaded project (if any)."""
            # Check workspace state for loaded project
            if hasattr(self.app_context, "workspace_state"):
                snap = self.app_context.workspace_state.snapshot()
                project_root = getattr(snap, "project_root", None)
                if project_root is not None:
                    return project_root
            # Fall back to tracked project
            return self._current_project

        def load_project(self, project_path: Path) -> None:
            """
            Load a project through the UI.

            This should trigger all project loading logic:
            - Plugin initialization for project
            - UI updates
            - State changes

            NOTE: This is a simplified implementation for testing.
            Real tests should trigger actual UI flows (File -> Open Project, etc.)
            """
            # Track the loaded project
            self._current_project = project_path

            # TODO: In real implementation, this would:
            # 1. Trigger the actual project loading UI flow
            # 2. Update workspace state
            # 3. Initialize plugins for the project
            # 4. Update UI to show project

        def unload_project(self) -> None:
            """
            Unload the current project through the UI.

            This should trigger all cleanup logic:
            - Plugin deinitialization
            - UI resets
            - State cleanup
            """
            # In a real implementation, this would trigger the actual UI flow
            # For now, this is a placeholder that tests can override
            self._current_project = None

        def verify_no_project_loaded(self) -> None:
            """Verify that no project is currently loaded."""
            assert self.current_project is None, "Expected no project to be loaded"

        def verify_project_loaded(self, expected_path: Path) -> None:
            """Verify that the expected project is loaded."""
            assert self.current_project is not None, "Expected a project to be loaded"
            if expected_path:
                assert self.current_project == expected_path, \
                    f"Expected project {expected_path}, got {self.current_project}"

    helper = ProjectLifecycleHelper(app_context, test_project_root)

    # Phase 1: Ensure no project is loaded at start
    helper.verify_no_project_loaded()

    yield helper

    # Cleanup: Unload any project that might still be loaded
    try:
        if helper.current_project is not None:
            helper.unload_project()
    except Exception:
        pass


# Configure pytest-qt
@pytest.fixture(scope="session")
def qapp_args():
    """
    Arguments to pass to QApplication.

    This can be used to configure the application for testing
    (e.g., disable animations, set specific styles, etc.).
    """
    return []


@pytest.fixture(autouse=True)
def _auto_close_stray_popups(qapp: QApplication) -> Generator[None, None, None]:
    """
    Close any stray popups that might have been opened during a test.

    This keeps the suite robust when a control triggers a toast, dialog, or other
    top-level popup that could steal focus or block subsequent interactions.
    """
    yield

    import time
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QAbstractButton, QDialog, QFileDialog, QMainWindow, QMessageBox

    app = QApplication.instance()
    if not app:
        return

    try:
        from datalens.ui.widgets.dialogs.loader_dialog import LoaderDialog
    except Exception:
        LoaderDialog = None  # type: ignore[assignment]

    for widget in list(app.topLevelWidgets()):
        try:
            if not widget.isVisible():
                continue
            if isinstance(widget, QMainWindow):
                continue

            if LoaderDialog is not None and isinstance(widget, LoaderDialog):
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
                    try:
                        for btn in widget.findChildren(QAbstractButton):
                            if (btn.text() or "").strip().lower() == "cancel" and btn.isVisible() and btn.isEnabled():
                                QTest.mouseClick(btn, Qt.LeftButton)
                                break
                    except Exception:
                        pass
                continue

            if isinstance(widget, (QFileDialog, QMessageBox, QDialog)):
                try:
                    widget.reject()
                except Exception:
                    widget.close()
        except Exception:
            continue


# Marker for tests that require the full app
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "requires_app: mark test as requiring the full DataLens application (all tests should have this)",
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow running",
    )
    config.addinivalue_line(
        "markers",
        "ui: mark test as a UI interaction test (clicks, keyboard, etc.)",
    )


# Auto-use the datalens_app fixture for all tests
@pytest.fixture(autouse=True, scope="session")
def _auto_load_app(datalens_app):
    """
    Automatically load the DataLens application for all tests.

    This ensures every test runs with the full application loaded,
    even if they don't explicitly request the fixture.
    """
    pass
