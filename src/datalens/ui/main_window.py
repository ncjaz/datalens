from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QWidget

from datalens.domain.plugin import PluginId
from datalens.services.plugins.registry import PluginRecord
from datalens.services.settings_store import default_settings_store
from datalens.ui.main_window_components import (
    MainWindowUiStateController,
    ProjectActionsController,
    WorkspacesController,
    try_get_app_context,
)
from datalens.ui.menus.factory import create_menubar


class MainWindow(QMainWindow):
    """
    Main application window.

    Keep this class focused on top-level composition/wiring; detailed UI logic is
    implemented in `datalens.ui.main_window_components.*` to avoid monolithic growth.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        recent_projects: list[Path] | None = None,
        plugins: list[PluginRecord] | None = None,
        enabled_plugin_ids: set[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("DataLens")
        self.resize(1200, 800)

        self._close_in_progress = False
        self._recent_projects: list[Path] = list(recent_projects or [])
        self._plugins: list[PluginRecord] = list(plugins or [])
        self._enabled_plugin_ids: set[PluginId] | None = (
            {PluginId(pid) for pid in enabled_plugin_ids} if enabled_plugin_ids is not None else None
        )

        menubar = create_menubar(self)
        self.setMenuBar(menubar)
        self._menubar = menubar
        self._menubar.set_recent_projects(self._recent_projects)

        self._workspaces = WorkspacesController(self, plugins=self._plugins, enabled_plugin_ids=self._enabled_plugin_ids)
        self.setCentralWidget(self._workspaces.central_widget)

        self._ui_state = MainWindowUiStateController(self)

        def set_recent_projects(new: list[Path]) -> None:
            self._recent_projects = list(new)
            self._menubar.set_recent_projects(self._recent_projects)

        self._projects = ProjectActionsController(
            self,
            get_recent_projects=lambda: list(self._recent_projects),
            set_recent_projects=set_recent_projects,
            on_project_changed=self.on_project_changed,
            flush_ui_state=self._ui_state.flush,
            set_close_in_progress=lambda v: setattr(self, "_close_in_progress", bool(v)),
            is_close_in_progress=lambda: bool(self._close_in_progress),
        )

        self._refresh_project_state()

    def on_plugins_enabled(self) -> None:
        """
        Notify the UI that plugin enable/disable has completed.

        The main window is shown before plugins are enabled (loader stages run
        after `show()`), so the initial workspace selection may have been
        published before the runtime existed. Re-dispatch focus so the visible
        workspace receives `on_focus`.
        """
        self._workspaces.on_plugins_enabled()

    def plugin_records(self) -> list[PluginRecord]:
        """Return the currently known discovered plugin records (UI metadata)."""
        return list(self._plugins)

    def refresh_plugin_records_from_app_context(self) -> None:
        """
        Best-effort: refresh discovered plugin metadata from the runtime plugin registry.

        This is used after editing plugin metadata overrides (group/name/nav label)
        so the workspace nav and menus can reflect changes immediately without a restart.
        """
        app_ctx = try_get_app_context()
        if app_ctx is None:
            return
        host = getattr(app_ctx, "plugin_host", None)
        registry = getattr(host, "registry", None) if host is not None else None
        if registry is None:
            return
        try:
            records = list(registry.all())
        except Exception:
            return
        try:
            settings = default_settings_store().load()
            enabled = set(getattr(settings, "enabled_plugins", ()) or ())
        except Exception:
            enabled = None
        self._plugins = records
        self._enabled_plugin_ids = enabled
        self._workspaces.set_plugins(self._plugins, self._enabled_plugin_ids)

    def reload_recent_projects_from_settings(self) -> None:
        """
        Reload recent projects from `settings.json` and update menu/MRU surfaces.

        Used by startup flows that open projects outside the File menu controller.
        """
        try:
            settings = default_settings_store().load()
            self._recent_projects = list(getattr(settings, "recent_projects", ()) or ())
            self._menubar.set_recent_projects(self._recent_projects)
        except Exception:
            return

    def active_workspace_id(self) -> PluginId | None:
        return self._workspaces.active_workspace_id

    def moveEvent(self, event) -> None:  # type: ignore[override]
        super().moveEvent(event)
        self._ui_state.enqueue_move()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._ui_state.enqueue_resize()

    def best_open_start_dir(self) -> str:
        app_ctx = try_get_app_context()
        project_root = getattr(app_ctx, "project_root", None) if app_ctx is not None else None
        if project_root is not None:
            return str(project_root)
        if self._recent_projects:
            return str(self._recent_projects[0])
        return ""

    def _refresh_project_state(self) -> None:
        app_ctx = try_get_app_context()
        has_project = bool(app_ctx is not None and getattr(app_ctx, "active_project", None) is not None)
        self._menubar.set_has_project(has_project)
        try:
            project_root = getattr(app_ctx, "project_root", None) if app_ctx is not None else None
            if project_root is None:
                self.setWindowTitle("DataLens")
            else:
                name = Path(project_root).name
                self.setWindowTitle(f"DataLens: {name}")
        except Exception:
            self.setWindowTitle("DataLens")

    def on_project_changed(self) -> None:
        """
        Refresh UI state after a project open/close/switch.

        This is intentionally lightweight: it updates menu gating and restores any
        persisted per-project main window UI state.
        """
        self._ui_state.on_project_changed()
        self._refresh_project_state()
        self._workspaces.on_project_changed()

    def open_project(self, project_root: Path) -> None:
        self._projects.open_project(project_root)

    def close_project(self) -> None:
        self._projects.close_project_interactive()

    def restart_app(self) -> None:
        """
        Restart DataLens in a new process.

        If a project is currently open, the restart will re-open the last project
        (same as starting from terminal) using `--skip-welcome --load-last-project`.
        """
        self._projects.restart_app_interactive()

    def startup_load(
        self,
        *,
        enabled_plugin_ids: set[str] | None,
        load_last_project: bool,
        last_project_root: object | None,
    ) -> None:
        """
        Apply the initial startup selection using the same UX as File->Open.

        This keeps startup behavior consistent and reduces duplicated logic in
        `datalens.app`.
        """
        self._projects.startup_load(
            enabled_plugin_ids=enabled_plugin_ids,
            load_last_project=load_last_project,
            last_project_root=last_project_root,
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """
        Ensure project persistence flushes run off the UI thread on app close.

        The close event is intercepted and handled asynchronously when a project
        is open; the window closes once the loader completes.
        """
        if self._projects.handle_close_event(event):
            return
        super().closeEvent(event)


__all__ = ["MainWindow"]
