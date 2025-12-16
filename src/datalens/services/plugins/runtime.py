"""
Plugin runtime contracts (application layer).

This module defines the minimal runtime interface for enabled plugins.

Pairing:
- Runtime loader/wiring: `datalens/services/plugins/host.py`
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


@dataclass(frozen=True)
class PluginProjectContext:
    """Runtime context passed to plugin lifecycle hooks (project scope)."""

    app: AppContext
    project: ProjectContext
    plugin: PluginDefinition
    db: PluginDb


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


class NoopPlugin:
    """Fallback plugin runtime used when a plugin has no `plugin.py` entrypoint."""

    def __init__(self, plugin_id: PluginId) -> None:
        self._plugin_id = plugin_id

    @property
    def plugin_id(self) -> PluginId:
        return self._plugin_id

    def on_load(self, ctx: PluginAppContext) -> None:
        return None

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        return None

    def on_project_migrate(self, ctx: PluginProjectContext) -> PluginFutureResult:
        return None

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        return None


GetPluginFn = Callable[[], BasePlugin]
