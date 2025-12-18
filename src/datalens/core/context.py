from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from datalens.services.background_io.writer import IoWriter, default_io_writer
from datalens.services.config_service import settings_store
from datalens.services.plugin_state_registry import PluginStateRegistry
from datalens.services.shortcuts import ShortcutsService
from datalens.services.workspace_state_service import WorkspaceStateService
from datalens.services.db.project_db import ProjectDb
from datalens.ui.theme.app_theme import AppTheme
from datalens.core.events import EventHub
from PySide6.QtWidgets import QApplication

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datalens.services.plugins.runtime.host import PluginHost


class NoActiveProjectError(RuntimeError):
    pass


@dataclass
class ProjectContext:
    """
    Runtime context for an open project.

    This is not a domain object: it owns process resources (DB executors, I/O).
    """

    project_root: Path
    project_db: ProjectDb


ProjectFlushHook = Callable[[ProjectContext], Future[Any] | list[Future[Any]] | None]


@dataclass
class AppContext:
    """
    Runtime context shared across the app.

    `active_project` is None when no project is open (gating).
    """

    theme: AppTheme
    io: IoWriter
    events: EventHub
    workspace_state: WorkspaceStateService
    plugin_state: PluginStateRegistry
    shortcuts: ShortcutsService
    active_project: ProjectContext | None = None
    project_flush_hooks: list[ProjectFlushHook] = field(default_factory=list)
    plugin_host: "PluginHost | None" = None

    @property
    def has_project(self) -> bool:
        """True when a project is currently open."""
        return self.active_project is not None

    @property
    def project(self) -> ProjectContext | None:
        """
        Convenience alias for `active_project`.

        Prefer using this (or `has_project`) for feature gating instead of
        calling `require_project()` and catching exceptions.
        """
        return self.active_project

    @property
    def project_root(self) -> Path | None:
        """Project root for the active project, or None if no project is open."""
        project = self.active_project
        return project.project_root if project is not None else None

    def require_project(self) -> ProjectContext:
        if self.active_project is None:
            raise NoActiveProjectError("No project is currently open")
        return self.active_project

    def with_project(self, fn: Callable[[ProjectContext], Any]) -> Any | None:
        """
        Call `fn(project)` if a project is open, otherwise return None.

        This is a small convenience for gating logic. Keep `fn` lightweight;
        do not block the UI thread within `fn`.
        """
        project = self.active_project
        if project is None:
            return None
        return fn(project)

    def register_project_flush_hook(self, hook: ProjectFlushHook) -> None:
        """
        Register a hook that will be invoked when a project is closing.

        Plugins and services that manage their own background pipelines should
        use this to flush pending work before the core persistence resources
        are torn down.
        """
        self.project_flush_hooks.append(hook)


def create_app_context(theme: AppTheme) -> AppContext:
    """
    Construct the default AppContext.

    This is intentionally lightweight for now; additional shared services will
    be added as the plugin runtime lands.

    This is a bootstrap-only factory. In a running Qt app, there should be
    exactly one global AppContext stored on the QApplication instance
    (``DatalensApplication.app_context``). If you need access to that singleton,
    use :func:`get_app_context`.
    """
    app = QApplication.instance()
    if app is not None and hasattr(app, "app_context"):
        raise RuntimeError("AppContext already exists; use get_app_context()")
    _ = settings_store()  # ensure settings store is initialised/cached
    workspace_state = WorkspaceStateService()
    return AppContext(
        theme=theme,
        io=default_io_writer(),
        events=EventHub(),
        workspace_state=workspace_state,
        plugin_state=PluginStateRegistry(),
        shortcuts=ShortcutsService(workspace_state=workspace_state),
    )


def get_app_context() -> AppContext:
    """
    Return the global AppContext for the running Qt application.

    Use this for UI-layer convenience only. Service-layer code should prefer
    explicit dependency injection by passing ``app_ctx``.
    """
    app = QApplication.instance()
    if app is None or not hasattr(app, "app_context"):
        raise RuntimeError("No running DatalensApplication; AppContext is not available")
    return getattr(app, "app_context")
