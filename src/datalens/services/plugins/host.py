"""
Plugin host/runtime loader.

This module owns:
- loading enabled plugin runtimes (from `plugin.py`)
- invoking lifecycle hooks (app + project)
- registering a project flush hook with `AppContext`

Pairing:
- UI selection: `datalens/ui/welcome_window.py`
- Loader UX for long work: `datalens/infra/background/loader_runner.py`
"""

from __future__ import annotations

import importlib
import sys
import types
from concurrent.futures import Future
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any

from datalens.core.context import AppContext, ProjectContext, ProjectFlushHook
from datalens.core.logging import bind_log_context, get_logger
from datalens.domain.plugin import PluginId
from datalens.services.db.plugin_db import PluginDb
from datalens.services.plugins.registry import PluginOrigin, PluginRecord, PluginRegistry
from datalens.services.plugins.runtime import BasePlugin, NoopPlugin, PluginAppContext, PluginProjectContext, PluginFutureResult


class PluginLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class PluginRuntime:
    record: PluginRecord
    instance: BasePlugin


def _safe_identifier(text: str) -> str:
    return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in text)


def _module_name_for_plugin(*, origin: PluginOrigin, plugin_id: PluginId, plugin_root: Path) -> str:
    digest = sha1(str(plugin_root).encode("utf-8")).hexdigest()[:10]
    return f"datalens._plugins.{origin.value}.{_safe_identifier(str(plugin_id))}_{digest}"


def _load_user_plugin_module(*, module_base: str, plugin_root: Path) -> types.ModuleType:
    """
    Load `plugin.py` from an arbitrary directory as a package-backed module.

    This enables relative imports within the plugin directory:
      from .ui.panel import ...
    """
    plugin_py = plugin_root / "plugin.py"
    if not plugin_py.exists():
        raise FileNotFoundError(f"Missing {plugin_py.name}")

    pkg_name = module_base
    mod_name = f"{pkg_name}.plugin"

    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(plugin_root)]  # type: ignore[attr-defined]
    sys.modules[pkg_name] = pkg

    spec = importlib.util.spec_from_file_location(mod_name, plugin_py)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to import module from {plugin_py}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    return module


def _load_shipped_plugin_module(plugin_root: Path) -> types.ModuleType:
    """
    Import shipped plugin runtime using its in-package module name.

    Shipped plugins live under `datalens/plugins/` and should be importable as
    `datalens.plugins.<...>.plugin`.
    """
    plugins_root = Path(__file__).resolve().parents[2] / "plugins"
    try:
        rel = plugin_root.resolve().relative_to(plugins_root.resolve())
    except Exception as exc:
        raise PluginLoadError(f"Plugin root {plugin_root} is not under {plugins_root}") from exc

    parts = ["datalens", "plugins", *[p for p in rel.parts if p]]
    module_path = ".".join(parts + ["plugin"])
    return importlib.import_module(module_path)


def _plugin_from_module(module: types.ModuleType) -> BasePlugin:
    candidate = getattr(module, "PLUGIN", None)
    if candidate is not None:
        return candidate  # type: ignore[return-value]

    factory = getattr(module, "get_plugin", None)
    if callable(factory):
        plugin = factory()
        return plugin

    raise PluginLoadError("plugin.py must export PLUGIN or get_plugin()")


def _normalize_futures(result: PluginFutureResult) -> list[Future[Any]]:
    if result is None:
        return []
    if isinstance(result, Future):
        return [result]
    if isinstance(result, list):
        return [f for f in result if isinstance(f, Future)]
    if isinstance(result, tuple):
        return [f for f in result if isinstance(f, Future)]
    return []


class PluginHost:
    """Loads enabled plugin runtimes and coordinates lifecycle hooks."""

    def __init__(self, registry: PluginRegistry) -> None:
        self._log = get_logger(__name__)
        self._registry = registry
        self._records: dict[PluginId, PluginRecord] = {r.definition.id: r for r in registry.all()}
        self._enabled: dict[PluginId, PluginRuntime] = {}
        self._flush_hook_registered = False

    def enabled_plugins(self) -> tuple[PluginId, ...]:
        return tuple(self._enabled.keys())

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
            runtime = self._load_runtime(record)
            with bind_log_context(
                plugin_id=str(plugin_id),
                plugin_phase="enable",
                hook="on_load",
            ):
                self._log.info(
                    "Enabling plugin",
                    extra={"operation": "plugin_enable", "phase": "start"},
                )
                runtime.instance.on_load(PluginAppContext(app=app_ctx, plugin=record.definition))
                self._log.info(
                    "Plugin enabled",
                    extra={"operation": "plugin_enable", "phase": "end"},
                )
            self._enabled[plugin_id] = runtime

        if not self._flush_hook_registered:
            app_ctx.register_project_flush_hook(self._project_flush_hook(app_ctx))
            self._flush_hook_registered = True

    def on_project_opened(self, *, app_ctx: AppContext, project: ProjectContext) -> list[Future[Any]]:
        """Invoke `on_project_opened` for enabled plugins."""
        futures: list[Future[Any]] = []
        for plugin_id, runtime in list(self._enabled.items()):
            with bind_log_context(
                plugin_id=str(plugin_id),
                plugin_phase="project_open",
                hook="on_project_opened",
            ):
                ctx = PluginProjectContext(
                    app=app_ctx,
                    project=project,
                    plugin=runtime.record.definition,
                    db=PluginDb(project_db=project.project_db, plugin_id=plugin_id),
                )
                futures.extend(_normalize_futures(runtime.instance.on_project_opened(ctx)))
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
            with bind_log_context(
                plugin_id=str(plugin_id),
                plugin_phase="project_migrate",
                hook="on_project_migrate",
            ):
                ctx = PluginProjectContext(
                    app=app_ctx,
                    project=project,
                    plugin=runtime.record.definition,
                    db=PluginDb(project_db=project.project_db, plugin_id=plugin_id),
                )
                futures.extend(_normalize_futures(runtime.instance.on_project_migrate(ctx)))
        return futures

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_runtime(self, record: PluginRecord) -> PluginRuntime:
        plugin_root = record.location.root_dir
        plugin_id = record.definition.id

        plugin_py = plugin_root / "plugin.py"
        if not plugin_py.exists():
            return PluginRuntime(record=record, instance=NoopPlugin(plugin_id))

        with bind_log_context(plugin_id=str(plugin_id), plugin_phase="load"):
            self._log.debug(
                "Loading plugin runtime",
                extra={"operation": "plugin_load", "phase": "start"},
            )
            if record.location.origin == PluginOrigin.SHIPPED:
                module = _load_shipped_plugin_module(plugin_root)
            else:
                module_base = _module_name_for_plugin(
                    origin=record.location.origin,
                    plugin_id=plugin_id,
                    plugin_root=plugin_root,
                )
                module = _load_user_plugin_module(module_base=module_base, plugin_root=plugin_root)

        plugin = _plugin_from_module(module)
        if getattr(plugin, "plugin_id", None) != plugin_id:
            raise PluginLoadError(f"plugin_id mismatch for {plugin_id}: runtime returned {getattr(plugin,'plugin_id',None)!r}")

        self._log.debug(
            "Plugin runtime loaded",
            extra={"operation": "plugin_load", "phase": "end", "plugin_id": str(plugin_id)},
        )
        return PluginRuntime(record=record, instance=plugin)

    def _project_flush_hook(self, app_ctx: AppContext) -> ProjectFlushHook:
        def hook(project: ProjectContext) -> Future[Any] | list[Future[Any]] | None:
            futures: list[Future[Any]] = []
            for _, runtime in list(self._enabled.items()):
                plugin_id = runtime.record.definition.id
                with bind_log_context(
                    plugin_id=str(plugin_id),
                    plugin_phase="project_close",
                    hook="on_project_closing",
                ):
                    ctx = PluginProjectContext(
                        app=app_ctx,
                        project=project,
                        plugin=runtime.record.definition,
                        db=PluginDb(project_db=project.project_db, plugin_id=plugin_id),
                    )
                    futures.extend(_normalize_futures(runtime.instance.on_project_closing(ctx)))
            return futures

        return hook
