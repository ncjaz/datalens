from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from datalens.services.background_io.writer import IoWriter, default_io_writer
from datalens.services.config_service import settings_store
from datalens.services.db.project_db import ProjectDb
from datalens.ui.theme.app_theme import AppTheme

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datalens.services.plugins.host import PluginHost


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
    active_project: ProjectContext | None = None
    project_flush_hooks: list[ProjectFlushHook] = field(default_factory=list)
    plugin_host: "PluginHost | None" = None

    def require_project(self) -> ProjectContext:
        if self.active_project is None:
            raise NoActiveProjectError("No project is currently open")
        return self.active_project

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
    """
    _ = settings_store()  # ensure settings store is initialised/cached
    return AppContext(theme=theme, io=default_io_writer())
