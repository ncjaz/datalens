from __future__ import annotations

from concurrent.futures import Future
from typing import Any

from datalens.core.context import AppContext
from datalens.domain.plugin import PluginId
from datalens.services.plugins.runtime.contracts import PluginAppContext, PluginFutureResult, PluginProjectContext


def normalize_futures(result: PluginFutureResult) -> list[Future[Any]]:
    if result is None:
        return []
    if isinstance(result, Future):
        return [result]
    if isinstance(result, list):
        return [f for f in result if isinstance(f, Future)]
    if isinstance(result, tuple):
        return [f for f in result if isinstance(f, Future)]
    return []


def call_app_hook(
    *,
    log: Any,
    operation: str,
    hook: str,
    plugin_id: PluginId,
    app_ctx: AppContext,
    plugin_def: Any,
    fn: Any,
    best_effort: bool,
) -> None:
    if not callable(fn):
        return None
    log.info("Plugin hook started", extra={"operation": operation, "phase": "start", "hook": hook})
    try:
        fn(PluginAppContext(app=app_ctx, plugin=plugin_def))
    except Exception:
        log.warning(
            "Plugin hook failed",
            extra={"operation": operation, "phase": "error", "hook": hook},
            exc_info=True,
        )
        if not best_effort:
            raise
    else:
        log.info("Plugin hook completed", extra={"operation": operation, "phase": "end", "hook": hook})
    return None


def call_project_hook(
    *,
    log: Any,
    operation: str,
    hook: str,
    plugin_id: PluginId,
    ctx: PluginProjectContext,
    fn: Any,
    best_effort: bool,
) -> list[Future[Any]]:
    if not callable(fn):
        return []
    log.info("Plugin hook started", extra={"operation": operation, "phase": "start", "hook": hook})
    try:
        result = fn(ctx)
    except Exception:
        log.warning(
            "Plugin hook failed",
            extra={"operation": operation, "phase": "error", "hook": hook},
            exc_info=True,
        )
        if not best_effort:
            raise
        return []
    futures = normalize_futures(result)
    log.info(
        "Plugin hook completed",
        extra={"operation": operation, "phase": "end", "hook": hook, "futures": len(futures)},
    )
    return futures

