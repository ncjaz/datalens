"""
Plugin runtime host.

This module owns:
- loading enabled plugin runtimes (from `plugin.py`)
- invoking lifecycle hooks (app + project)
- registering a project flush hook with `AppContext`

Pairing:
- UI selection: `datalens/ui/welcome_window.py`
- Loader UX for long work: `datalens/infra/background/loader_runner.py`
"""

from __future__ import annotations

from concurrent.futures import Future
from typing import Any

from datalens.core.context import AppContext, ProjectContext, ProjectFlushHook
from datalens.core.logging import bind_log_context, get_logger
from datalens.domain.plugin import PluginId
from datalens.services.db.plugin_db import PluginDb
from datalens.services.plugins.registry import PluginRecord, PluginRegistry
from datalens.services.plugins.runtime import dispatcher
from datalens.services.plugins.runtime.contracts import PluginAppContext, PluginProjectContext
from datalens.services.plugins.runtime.loader import load_plugin_instance
from datalens.services.plugins.runtime.types import PluginRuntime


class PluginHost:
    """Loads enabled plugin runtimes and coordinates lifecycle hooks."""

    def __init__(self, registry: PluginRegistry) -> None:
        self._log = get_logger(__name__)
        self._registry = registry
        self._records: dict[PluginId, PluginRecord] = {r.definition.id: r for r in registry.all()}
        self._enabled: dict[PluginId, PluginRuntime] = {}
        self._flush_hook_registered = False
        self._focused_workspace: PluginId | None = None
        self._focused_workspace_hook_delivered = False

    def enabled_plugins(self) -> tuple[PluginId, ...]:
        return tuple(self._enabled.keys())

    def get_enabled_plugin(self, plugin_id: PluginId) -> object | None:
        """Return the enabled plugin runtime instance for `plugin_id`, or None."""
        runtime = self._enabled.get(PluginId(str(plugin_id)))
        return runtime.instance if runtime is not None else None

    def get_enabled_record(self, plugin_id: PluginId) -> PluginRecord | None:
        """Return the enabled plugin record for `plugin_id`, or None."""
        runtime = self._enabled.get(PluginId(str(plugin_id)))
        return runtime.record if runtime is not None else None

    def set_enabled(
        self,
        *,
        app_ctx: AppContext,
        plugin_ids: set[PluginId],
        project: ProjectContext | None = None,
    ) -> list[Future[Any]]:
        """
        Enable/disable plugins to match `plugin_ids`.

        Returns Futures from any `on_project_closing` calls triggered by disabling
        plugins while a project is open. Callers may choose to await them.

        This may import plugin code. Do not call it on the UI thread.
        """
        desired = {PluginId(str(pid)) for pid in plugin_ids}
        active_project = project if project is not None else app_ctx.project

        futures: list[Future[Any]] = []
        to_disable = set(self._enabled.keys()) - desired
        if to_disable:
            futures.extend(self.disable(app_ctx=app_ctx, plugin_ids=to_disable, project=active_project))
        self.enable(app_ctx=app_ctx, plugin_ids=desired)
        return futures

    def enable(self, *, app_ctx: AppContext, plugin_ids: set[PluginId]) -> None:
        """
        Enable the specified plugins for this app run.

        This may import plugin code. Do not call it on the UI thread.
        """
        desired = {PluginId(str(pid)) for pid in plugin_ids}

        for plugin_id in desired:
            if plugin_id in self._enabled:
                continue
            record = self._records.get(plugin_id)
            if record is None:
                continue
            runtime = PluginRuntime(record=record, instance=load_plugin_instance(record))
            with bind_log_context(plugin_id=str(plugin_id), plugin_phase="enable", hook="on_load"):
                dispatcher.call_app_hook(
                    log=self._log,
                    operation="plugin_enable",
                    hook="on_load",
                    plugin_id=plugin_id,
                    app_ctx=app_ctx,
                    plugin_def=record.definition,
                    fn=getattr(runtime.instance, "on_load", None),
                    best_effort=False,
                )
            self._enabled[plugin_id] = runtime

            # If the UI already selected this workspace before the plugin was enabled,
            # dispatch `on_focus` once the runtime becomes available.
            if self._focused_workspace == plugin_id and not self._focused_workspace_hook_delivered:
                with bind_log_context(plugin_id=str(plugin_id), plugin_phase="ui", hook="on_focus"):
                    dispatcher.call_app_hook(
                        log=self._log,
                        operation="plugin_focus",
                        hook="on_focus",
                        plugin_id=plugin_id,
                        app_ctx=app_ctx,
                        plugin_def=record.definition,
                        fn=getattr(runtime.instance, "on_focus", None),
                        best_effort=True,
                    )
                self._focused_workspace_hook_delivered = True
                try:
                    app_ctx.plugin_state.set(plugin_id=plugin_id, key="ui.focused", value=True)
                except Exception:
                    pass

        if not self._flush_hook_registered:
            app_ctx.register_project_flush_hook(self._project_flush_hook(app_ctx))
            self._flush_hook_registered = True

    def disable(
        self,
        *,
        app_ctx: AppContext,
        plugin_ids: set[PluginId],
        project: ProjectContext | None = None,
    ) -> list[Future[Any]]:
        """
        Disable the specified plugins for this app run.

        If `project` is provided (or a project is currently open), this will
        invoke `on_project_closing` for the plugin before unloading it.

        Returns futures from `on_project_closing` so callers may await flushes.
        """
        active_project = project if project is not None else app_ctx.project
        futures: list[Future[Any]] = []

        for plugin_id in {PluginId(str(pid)) for pid in plugin_ids}:
            runtime = self._enabled.pop(plugin_id, None)
            if runtime is None:
                continue

            # Best-effort: defocus before unloading if this plugin is currently active.
            if self._focused_workspace == plugin_id:
                self.set_focused_workspace(app_ctx=app_ctx, plugin_id=None)

            if active_project is not None:
                with bind_log_context(plugin_id=str(plugin_id), plugin_phase="project_close", hook="on_project_closing"):
                    ctx = PluginProjectContext(
                        app=app_ctx,
                        project=active_project,
                        plugin=runtime.record.definition,
                        db=PluginDb(project_db=active_project.project_db, plugin_id=plugin_id),
                    )
                    futures.extend(
                        dispatcher.call_project_hook(
                            log=self._log,
                            operation="plugin_project_close",
                            hook="on_project_closing",
                            plugin_id=plugin_id,
                            ctx=ctx,
                            fn=getattr(runtime.instance, "on_project_closing", None),
                            best_effort=True,
                        )
                    )

            with bind_log_context(plugin_id=str(plugin_id), plugin_phase="disable", hook="on_unload"):
                dispatcher.call_app_hook(
                    log=self._log,
                    operation="plugin_disable",
                    hook="on_unload",
                    plugin_id=plugin_id,
                    app_ctx=app_ctx,
                    plugin_def=runtime.record.definition,
                    fn=getattr(runtime.instance, "on_unload", None),
                    best_effort=True,
                )

        return futures

    def focused_workspace(self) -> PluginId | None:
        """Currently focused workspace plugin id (best-effort), or None."""
        return self._focused_workspace

    def set_focused_workspace(self, *, app_ctx: AppContext, plugin_id: PluginId | None) -> None:
        """
        Notify plugins when workspace focus changes.

        This is a lightweight UI coordination hook; it is not a sandbox.
        """
        new_id = PluginId(str(plugin_id)) if plugin_id is not None else None
        old_id = self._focused_workspace
        if new_id == old_id:
            # Focus is unchanged. If the runtime is now available and we haven't
            # delivered `on_focus` yet, dispatch it once.
            if new_id is not None and not self._focused_workspace_hook_delivered:
                runtime = self._enabled.get(new_id)
                if runtime is not None:
                    with bind_log_context(plugin_id=str(new_id), plugin_phase="ui", hook="on_focus"):
                        dispatcher.call_app_hook(
                            log=self._log,
                            operation="plugin_focus",
                            hook="on_focus",
                            plugin_id=new_id,
                            app_ctx=app_ctx,
                            plugin_def=runtime.record.definition,
                            fn=getattr(runtime.instance, "on_focus", None),
                            best_effort=True,
                        )
                    self._focused_workspace_hook_delivered = True
            return

        # Defocus previous.
        if old_id is not None:
            runtime = self._enabled.get(old_id)
            if runtime is not None:
                with bind_log_context(plugin_id=str(old_id), plugin_phase="ui", hook="on_defocus"):
                    dispatcher.call_app_hook(
                        log=self._log,
                        operation="plugin_defocus",
                        hook="on_defocus",
                        plugin_id=old_id,
                        app_ctx=app_ctx,
                        plugin_def=runtime.record.definition,
                        fn=getattr(runtime.instance, "on_defocus", None),
                        best_effort=True,
                    )
            try:
                app_ctx.plugin_state.set(plugin_id=old_id, key="ui.focused", value=False)
            except Exception:
                pass

        self._focused_workspace = new_id
        self._focused_workspace_hook_delivered = False

        # Focus new.
        if new_id is not None:
            runtime = self._enabled.get(new_id)
            if runtime is not None:
                with bind_log_context(plugin_id=str(new_id), plugin_phase="ui", hook="on_focus"):
                    dispatcher.call_app_hook(
                        log=self._log,
                        operation="plugin_focus",
                        hook="on_focus",
                        plugin_id=new_id,
                        app_ctx=app_ctx,
                        plugin_def=runtime.record.definition,
                        fn=getattr(runtime.instance, "on_focus", None),
                        best_effort=True,
                    )
                self._focused_workspace_hook_delivered = True
            try:
                app_ctx.plugin_state.set(plugin_id=new_id, key="ui.focused", value=True)
            except Exception:
                pass

    def shutdown(self, *, app_ctx: AppContext) -> list[Future[Any]]:
        """
        Best-effort unload of all enabled plugins.

        Returns futures from any `on_project_closing` calls triggered during
        shutdown.
        """
        return self.disable(app_ctx=app_ctx, plugin_ids=set(self._enabled.keys()), project=app_ctx.project)

    def on_project_opened(self, *, app_ctx: AppContext, project: ProjectContext) -> list[Future[Any]]:
        """Invoke `on_project_opened` for enabled plugins."""
        futures: list[Future[Any]] = []
        for plugin_id, runtime in list(self._enabled.items()):
            with bind_log_context(plugin_id=str(plugin_id), plugin_phase="project_open", hook="on_project_opened"):
                ctx = PluginProjectContext(
                    app=app_ctx,
                    project=project,
                    plugin=runtime.record.definition,
                    db=PluginDb(project_db=project.project_db, plugin_id=plugin_id),
                )
                futures.extend(
                    dispatcher.call_project_hook(
                        log=self._log,
                        operation="plugin_project_open",
                        hook="on_project_opened",
                        plugin_id=plugin_id,
                        ctx=ctx,
                        fn=getattr(runtime.instance, "on_project_opened", None),
                        best_effort=True,
                    )
                )
        return futures

    def on_project_migrate(self, *, app_ctx: AppContext, project: ProjectContext) -> list[Future[Any]]:
        """
        Invoke `on_project_migrate` for enabled plugins.

        This runs after core DB migrations (if any) and before `on_project_opened`.
        Callers may choose to await the returned futures to ensure migrations are
        complete before continuing.
        """
        futures: list[Future[Any]] = []
        for plugin_id, runtime in list(self._enabled.items()):
            with bind_log_context(plugin_id=str(plugin_id), plugin_phase="project_migrate", hook="on_project_migrate"):
                ctx = PluginProjectContext(
                    app=app_ctx,
                    project=project,
                    plugin=runtime.record.definition,
                    db=PluginDb(project_db=project.project_db, plugin_id=plugin_id),
                )
                futures.extend(
                    dispatcher.call_project_hook(
                        log=self._log,
                        operation="plugin_project_migrate",
                        hook="on_project_migrate",
                        plugin_id=plugin_id,
                        ctx=ctx,
                        fn=getattr(runtime.instance, "on_project_migrate", None),
                        best_effort=True,
                    )
                )
        return futures

    def _project_flush_hook(self, app_ctx: AppContext) -> ProjectFlushHook:
        def hook(project: ProjectContext) -> Future[Any] | list[Future[Any]] | None:
            futures: list[Future[Any]] = []
            for _, runtime in list(self._enabled.items()):
                plugin_id = runtime.record.definition.id
                with bind_log_context(plugin_id=str(plugin_id), plugin_phase="project_close", hook="on_project_closing"):
                    ctx = PluginProjectContext(
                        app=app_ctx,
                        project=project,
                        plugin=runtime.record.definition,
                        db=PluginDb(project_db=project.project_db, plugin_id=plugin_id),
                    )
                    futures.extend(
                        dispatcher.call_project_hook(
                            log=self._log,
                            operation="plugin_project_close",
                            hook="on_project_closing",
                            plugin_id=plugin_id,
                            ctx=ctx,
                            fn=getattr(runtime.instance, "on_project_closing", None),
                            best_effort=True,
                        )
                    )
            return futures

        return hook
