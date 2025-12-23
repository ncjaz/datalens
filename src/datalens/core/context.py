from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from datalens.services.background_io.writer import IoWriter, default_io_writer
from datalens.services.capabilities import CapabilitiesRegistry, CapabilityProvider
from datalens.services.config_service import settings_store
from datalens.services.commands import CommandBus
from datalens.services.plugin_preferences_service import PluginPreferencesService
from datalens.services.plugin_state_registry import PluginStateRegistry
from datalens.services.shortcuts import ShortcutsService
from datalens.services.workspace_state_service import WorkspaceStateService
from datalens.services.db.project_db import ProjectDb
from datalens.ui.theme.app_theme import AppTheme
from datalens.core.events import EventHub
from PySide6.QtWidgets import QApplication
from datalens.services.system_info_service import collect_system_info_base
from datalens.api.sharing import (
    CAP_MEDIA_INDEX,
    CAP_PLUGIN_PREFERENCES_SNAPSHOT,
    CAP_PROJECT_STATUS,
    CAP_WORKSPACE_STATE_SNAPSHOT,
    CMD_MEDIA_REGISTER,
)

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
PreProjectOpenHook = Callable[[Path], None]
PostProjectOpenHook = Callable[[ProjectContext], None]


@dataclass
class AppContext:
    """
    Runtime context shared across the app.

    `active_project` is None when no project is open (gating).
    """

    theme: AppTheme
    io: IoWriter
    events: EventHub
    capabilities: CapabilitiesRegistry
    commands: CommandBus
    workspace_state: WorkspaceStateService
    plugin_state: PluginStateRegistry
    preferences: PluginPreferencesService
    shortcuts: ShortcutsService
    # Developer mode enables advanced UI controls (e.g. consume-event toggles in
    # the shortcuts editor). It is not persisted; it is set at startup via CLI.
    dev_mode: bool = False
    active_project: ProjectContext | None = None
    project_flush_hooks: list[ProjectFlushHook] = field(default_factory=list)
    pre_project_open_hooks: list[PreProjectOpenHook] = field(default_factory=list)
    post_project_open_hooks: list[PostProjectOpenHook] = field(default_factory=list)
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

    def register_pre_project_open_hook(self, hook: PreProjectOpenHook) -> None:
        """
        Register an app-level hook invoked immediately before a project open/switch begins.

        Intended for core/app developers. Hooks run on the project-open worker
        thread (never the UI thread). Keep them fast and non-blocking.
        """
        self.pre_project_open_hooks.append(hook)

    def register_post_project_open_hook(self, hook: PostProjectOpenHook) -> None:
        """
        Register an app-level hook invoked after a project has been attached and is "ready".

        Intended for core/app developers. Hooks run on the project-open worker
        thread (never the UI thread). Keep them fast and non-blocking.
        """
        self.post_project_open_hooks.append(hook)


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
    system_info = collect_system_info_base()
    workspace_state.set_system_info(system_info)
    events = EventHub()
    preferences = PluginPreferencesService(events=events)
    app_ctx = AppContext(
        theme=theme,
        io=default_io_writer(),
        events=events,
        capabilities=CapabilitiesRegistry(),
        commands=CommandBus(),
        workspace_state=workspace_state,
        plugin_state=PluginStateRegistry(),
        preferences=preferences,
        shortcuts=ShortcutsService(workspace_state=workspace_state),
    )

    # Schema resolver needs access to the plugin registry, which is only
    # available after startup (when PluginHost is set). Keep this best-effort.
    def _resolve_schema(plugin_id: PluginId):
        host = getattr(app_ctx, "plugin_host", None)
        registry = getattr(host, "registry", None) if host is not None else None
        if registry is None:
            return None
        try:
            record = registry.get(PluginId(str(plugin_id)))
            if record is None:
                return None
            return getattr(record.definition, "preferences", None)
        except Exception:
            return None

    app_ctx.preferences.set_schema_resolver(_resolve_schema)

    # Core-owned capabilities (stable ids): allow plugins to query core state
    # without importing core UI/services directly.
    app_ctx.capabilities.register(
        CapabilityProvider(
            capability_id=CAP_WORKSPACE_STATE_SNAPSHOT,
            provider=app_ctx.workspace_state.snapshot,
            owner_plugin_id=None,
            description="Core workspace state snapshot provider (query current project/workspace/item).",
        ),
        replace_owner=True,
    )
    app_ctx.capabilities.register(
        CapabilityProvider(
            capability_id=CAP_PROJECT_STATUS,
            provider=lambda: {
                "has_project": bool(app_ctx.has_project),
                "project_root": str(app_ctx.project_root) if app_ctx.project_root is not None else None,
            },
            owner_plugin_id=None,
            description="Core project status provider (has_project + project_root).",
        ),
        replace_owner=True,
    )
    app_ctx.capabilities.register(
        CapabilityProvider(
            capability_id=CAP_PLUGIN_PREFERENCES_SNAPSHOT,
            provider=app_ctx.preferences.snapshot,
            owner_plugin_id=None,
            description="Plugin preferences snapshot provider (effective values + schema metadata).",
        ),
        replace_owner=True,
    )

    # ------------------------------------------------------------------
    # Core media index v0: core-owned `media_files` table + plugin-safe APIs.
    # ------------------------------------------------------------------
    #
    # Keep imports local to avoid bootstrap circular imports and to keep
    # module import side-effects minimal (important for docs builds).
    from datalens.services.commands import RegisteredHandler
    from datalens.services.media_index_service import MediaIndexClient, handle_cmd_media_register

    app_ctx.capabilities.register(
        CapabilityProvider(
            capability_id=CAP_MEDIA_INDEX,
            provider=MediaIndexClient(app_ctx),
            owner_plugin_id=None,
            description="Core media index client (query `media_files` via ProjectDb executor).",
        ),
        replace_owner=True,
    )
    app_ctx.commands.register(
        RegisteredHandler(
            command_id=CMD_MEDIA_REGISTER,
            handler=lambda ctx: handle_cmd_media_register(app_ctx, ctx),
            owner_plugin_id=None,
            description="Register a project-relative file path into the core media index (`media_files`).",
        ),
        replace=True,
    )

    return app_ctx


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
