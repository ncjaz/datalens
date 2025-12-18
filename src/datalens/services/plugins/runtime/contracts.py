"""
Plugin runtime contracts (application layer).

This module defines the minimal runtime interface for enabled plugins.

Pairing:
- Runtime coordinator: `datalens/services/plugins/runtime/host.py`
- UI selection: `datalens/ui/welcome_window.py`
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Protocol

from datalens.core.context import AppContext, ProjectContext
from datalens.domain.plugin import PluginDefinition, PluginId
from datalens.services.db.plugin_db import PluginDb


@dataclass(frozen=True)
class PluginAppContext:
    """Runtime context passed to plugin lifecycle hooks (app scope)."""

    app: AppContext
    plugin: PluginDefinition

    @property
    def has_project(self) -> bool:
        """True if a project is currently open."""
        return self.app.has_project

    @property
    def project_or_none(self) -> ProjectContext | None:
        """Active project, or None if no project is open."""
        return self.app.project

    def require_project(self) -> ProjectContext:
        """Return the active project or raise `NoActiveProjectError`."""
        return self.app.require_project()

    @property
    def is_focused(self) -> bool:
        """
        True if this plugin is currently the active workspace in the UI.

        Plugins must treat this as best-effort: the active workspace can change
        at any time, and focus hooks are not a security boundary.
        """
        try:
            snap = self.app.workspace_state.snapshot()
            return str(snap.active_workspace_id or "") == str(self.plugin.id)
        except Exception:
            return False


@dataclass(frozen=True)
class PluginProjectContext:
    """Runtime context passed to plugin lifecycle hooks (project scope)."""

    app: AppContext
    project: ProjectContext
    plugin: PluginDefinition
    db: PluginDb

    @property
    def project_root(self):
        return self.project.project_root


PluginFutureResult = Future[Any] | list[Future[Any]] | None


class BasePlugin(Protocol):
    """
    Minimal plugin runtime interface.

    Plugins should keep these hooks fast and non-blocking. Any heavy work should
    be scheduled onto background systems (ProjectDb/IoWriter/loader stages).
    """

    @property
    def plugin_id(self) -> PluginId: ...

    def on_load(self, ctx: PluginAppContext) -> None:
        """Called when the plugin is enabled/loaded for the current app run."""

    def on_unload(self, ctx: PluginAppContext) -> None:
        """Called when the plugin is disabled/unloaded for the current app run."""

    def on_focus(self, ctx: PluginAppContext) -> None:
        """
        Called when this plugin's workspace becomes active in the UI.

        This must be fast and non-blocking. Use it for lightweight UI refresh,
        starting view-scoped timers, or requesting background work.
        """

    def on_defocus(self, ctx: PluginAppContext) -> None:
        """
        Called when this plugin's workspace is no longer active in the UI.

        This must be fast and non-blocking. Use it to stop view-scoped timers
        or detach temporary listeners.
        """

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        """Called after a project is attached to the AppContext."""

    def on_project_migrate(self, ctx: PluginProjectContext) -> PluginFutureResult:
        """
        Called after core DB migrations complete, before `on_project_opened`.

        Plugins should use this hook to create/migrate their own tables and to
        update their `plugin_meta` row.
        """

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        """Called during project close before core persistence resources close."""


class SupportsShortcuts(Protocol):
    """
    Optional plugin capability: declare shortcut pages/commands at enable time.

    Implement `register_shortcuts` if your plugin wants to expose commands in
    the Preferences -> Keyboard Shortcuts page.

    Registration should be lightweight and must not block.
    """

    def register_shortcuts(self, ctx: PluginAppContext) -> None:
        """
        Called after `on_load` while enabling the plugin.

        Plugins should register commands via `ctx.app.shortcuts.register_page(...)`.
        """


class NoopPlugin:
    """Fallback plugin runtime used when a plugin has no `plugin.py` entrypoint."""

    def __init__(self, plugin_id: PluginId) -> None:
        self._plugin_id = plugin_id

    @property
    def plugin_id(self) -> PluginId:
        return self._plugin_id

    def on_load(self, ctx: PluginAppContext) -> None:
        return None

    def on_unload(self, ctx: PluginAppContext) -> None:
        return None

    def on_focus(self, ctx: PluginAppContext) -> None:
        return None

    def on_defocus(self, ctx: PluginAppContext) -> None:
        return None

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        return None

    def on_project_migrate(self, ctx: PluginProjectContext) -> PluginFutureResult:
        return None

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        return None


GetPluginFn = Callable[[], BasePlugin]


class ProjectAwarePlugin:
    """
    Optional convenience base class for plugin authors.

    This is not required, but it makes "no project open" gating easier when
    plugins register UI actions in `on_load` and then need to access project
    resources later.

    Contract:
    - `on_load` may run with no project open.
    - Project-scoped work must be started in `on_project_opened` and stopped/
      flushed in `on_project_closing`.
    """

    def __init__(self) -> None:
        self._app_ctx: AppContext | None = None
        self._project_ctx: ProjectContext | None = None
        self._plugin_def: PluginDefinition | None = None
        self._plugin_db: PluginDb | None = None

    @property
    def plugin_id(self) -> PluginId:  # pragma: no cover - overridden by plugins
        raise NotImplementedError

    @property
    def app(self) -> AppContext:
        if self._app_ctx is None:
            raise RuntimeError("Plugin has not been loaded yet (on_load not called).")
        return self._app_ctx

    @property
    def plugin(self) -> PluginDefinition:
        if self._plugin_def is None:
            raise RuntimeError("Plugin has not been loaded yet (on_load not called).")
        return self._plugin_def

    @property
    def has_project(self) -> bool:
        return self._project_ctx is not None

    @property
    def project(self) -> ProjectContext | None:
        return self._project_ctx

    @property
    def db(self) -> PluginDb | None:
        return self._plugin_db

    def require_project(self) -> ProjectContext:
        return self.app.require_project()

    def on_load(self, ctx: PluginAppContext) -> None:
        self._app_ctx = ctx.app
        self._plugin_def = ctx.plugin
        self.on_app_loaded(ctx)

    def on_unload(self, ctx: PluginAppContext) -> None:
        try:
            self.on_app_unloaded(ctx)
        finally:
            self._app_ctx = None
            self._plugin_def = None
            self._project_ctx = None
            self._plugin_db = None

    def on_app_loaded(self, ctx: PluginAppContext) -> None:
        """Override for app-scope setup (UI registration, service init)."""
        return None

    def on_app_unloaded(self, ctx: PluginAppContext) -> None:
        """Override for app-scope teardown (disconnect signals, stop services)."""
        return None

    def on_focus(self, ctx: PluginAppContext) -> None:
        """Override for "this workspace became active" behavior."""
        return None

    def on_defocus(self, ctx: PluginAppContext) -> None:
        """Override for "this workspace is no longer active" behavior."""
        return None

    def on_project_migrate(self, ctx: PluginProjectContext) -> PluginFutureResult:
        return None

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        self._project_ctx = ctx.project
        self._plugin_db = ctx.db
        return self.on_project_ready(ctx)

    def on_project_ready(self, ctx: PluginProjectContext) -> PluginFutureResult:
        """Override for project-scope setup (DB tables, caches, watchers)."""
        return None

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        try:
            return self.on_project_teardown(ctx)
        finally:
            self._project_ctx = None
            self._plugin_db = None

    def on_project_teardown(self, ctx: PluginProjectContext) -> PluginFutureResult:
        """Override for project-scope flush/teardown."""
        return None


__all__ = [
    "BasePlugin",
    "GetPluginFn",
    "NoopPlugin",
    "PluginAppContext",
    "PluginFutureResult",
    "PluginProjectContext",
    "ProjectAwarePlugin",
    "SupportsShortcuts",
]
