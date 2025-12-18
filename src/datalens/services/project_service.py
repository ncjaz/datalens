"""Project service (application layer).

This module hosts project lifecycle use-cases (open/close for now) and owns
runtime resources like the project database executor.
"""

from __future__ import annotations

import contextvars
import sqlite3
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from datalens.core.context import AppContext, ProjectContext, get_app_context
from datalens.core.events import (
    ActiveProjectChanged,
    EventHub,
    ProjectClosed,
    ProjectClosing,
    ProjectOpenFailed,
    ProjectOpened,
)
from datalens.core.logging import get_logger
from datalens.infra.project_paths import project_db_path, project_meta_path
from datalens.services.background_io.writer import IoWriter
from datalens.services.db.gateway import open_connection
from datalens.services.db.migrations_runner import (
    build_project_meta,
    decide_core_open_action,
    ensure_core_schema,
    inspect_core_db,
    migrate_core_schema,
)
from datalens.services.db.project_db import SqliteProjectDb


log = get_logger(__name__)

if TYPE_CHECKING:
    from datalens.services.plugins.runtime.host import PluginHost


class ProjectCloseError(RuntimeError):
    def __init__(self, *, phase: str, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.phase = phase
        self.__cause__ = cause


class ProjectOpenError(RuntimeError):
    def __init__(self, *, phase: str, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.phase = phase
        self.__cause__ = cause


def _require_not_ui_thread(operation: str) -> None:
    if threading.current_thread() is threading.main_thread():
        raise RuntimeError(
            f"{operation} must not be called on the UI thread; use the loader/background pipeline"
        )


def load_project(project_root: Path, *, io: IoWriter) -> ProjectContext:
    """
    Load project resources and return a ProjectContext.

    This function may block while the project DB initializes. Do not call it on
    the UI thread.

    It does not mutate global/app state; callers attach it to an AppContext.
    """
    _require_not_ui_thread("load_project")
    root = Path(project_root)
    root.mkdir(parents=True, exist_ok=True)

    db_path = project_db_path(root)
    action = "ensure"
    from_schema_version = 0
    if db_path.exists():
        # Inspect first using a read-only connection. This must never write.
        conn: sqlite3.Connection | None = None
        try:
            conn = open_connection(db_path, read_only=True)
            inspection = inspect_core_db(conn)
            decision = decide_core_open_action(inspection)
            action = decision.kind
            from_schema_version = int(decision.from_schema_version or 0)
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

    project_db = SqliteProjectDb.for_project_root(root)
    project_db.ready().result(timeout=10.0)

    # Apply core schema creation/repairs only if needed. This must never touch
    # plugin-owned tables.
    if action == "ensure":
        project_db.execute_core_write(lambda conn: ensure_core_schema(conn)).result(timeout=15.0)
    elif action == "migrate":
        project_db.execute_core_write(
            lambda conn: migrate_core_schema(conn, from_schema_version=from_schema_version)
        ).result(timeout=30.0)

    return ProjectContext(project_root=root, project_db=project_db)


def load_project_async(project_root: Path, *, io: IoWriter) -> Future[ProjectContext]:
    """
    Start loading a project on a background thread and return a Future.

    Callers must not block the UI thread on the returned Future. Use callbacks
    or the loader/background pipeline to await completion.
    """
    future: Future[ProjectContext] = Future()
    ctx = contextvars.copy_context()

    def run() -> None:
        try:
            project = ctx.run(load_project, project_root, io=io)
        except Exception as exc:
            future.set_exception(exc)
            return
        future.set_result(project)

    threading.Thread(target=run, name="ProjectService(load_project)", daemon=True).start()
    return future


def attach_project(app_ctx: AppContext | None, project: ProjectContext, *, schedule_meta: bool = True) -> None:
    """Attach a loaded project context to the app context (gating)."""
    if app_ctx is None:
        app_ctx = get_app_context()
    previous = app_ctx.project_root
    app_ctx.active_project = project
    if schedule_meta:
        schedule_project_meta_write(app_ctx, project)
    try:
        now = time.time()
        app_ctx.events.publish(EventHub.PROJECT_OPENED, ProjectOpened(project_root=project.project_root, timestamp_s=now))
        app_ctx.events.publish(
            EventHub.ACTIVE_PROJECT_CHANGED,
            ActiveProjectChanged(previous_root=previous, current_root=project.project_root, timestamp_s=now),
        )
    except Exception:
        log.debug("Failed to publish project attach events (best-effort)", exc_info=True)


def schedule_project_meta_write(app_ctx: AppContext, project: ProjectContext) -> None:
    """
    Best-effort derived metadata write after a project becomes "ready".

    This must never block the project open critical path.
    """

    def on_meta_done(fut: Future[dict[str, object]]) -> None:
        try:
            meta = fut.result()
        except Exception:
            log.debug(
                "Failed to build derived project metadata (best-effort)",
                extra={"operation": "project_meta", "phase": "warning"},
                exc_info=True,
            )
            return

        try:
            app_ctx.io.write_json_atomic(project_meta_path(project.project_root), meta)
        except Exception:
            log.debug(
                "Failed to enqueue derived project metadata write (best-effort)",
                extra={"operation": "project_meta", "phase": "warning"},
                exc_info=True,
            )

    try:
        future = project.project_db.execute_core_read(build_project_meta)
        future.add_done_callback(on_meta_done)
    except Exception:
        log.debug(
            "Failed to schedule derived project metadata write (best-effort)",
            extra={"operation": "project_meta", "phase": "warning"},
            exc_info=True,
        )


def open_project_with_plugins(
    app_ctx: AppContext | None,
    project_root: Path,
    *,
    plugin_host: "PluginHost | None" = None,
    close_timeout_seconds: float = 30.0,
    plugin_migrate_timeout_seconds: float = 60.0,
    await_plugin_opened: bool = False,
    plugin_opened_timeout_seconds: float = 30.0,
    progress: Callable[[str], None] | None = None,
) -> ProjectContext:
    """
    Open/switch a project and run plugin project lifecycle hooks.

    This is the canonical project-open pipeline for UI entrypoints:
    welcome, MRU, menu "Open...", CLI `--load-last-project`.

    Important:
        This may block. Do not call it on the UI thread. Run it in a loader
        stage or background pipeline.

    Notes:
    - Project meta generation is scheduled only after plugin hooks succeed.
    - If plugin migrations fail, the project is closed and `active_project` is
      cleared before raising.
    """
    if app_ctx is None:
        app_ctx = get_app_context()
    _require_not_ui_thread("open_project_with_plugins")

    def emit(text: str) -> None:
        if progress is None:
            return
        try:
            progress(text)
        except Exception:
            return

    try:
        if app_ctx.active_project is not None:
            emit("Closing previous project...")
            close_project_blocking(app_ctx, timeout_seconds=close_timeout_seconds, reason="switch")

        project = load_project(Path(project_root), io=app_ctx.io)

        # Set active_project early so downstream code can rely on gating, but do
        # not schedule derived metadata until the project is fully "ready".
        attach_project(app_ctx, project, schedule_meta=False)

        if plugin_host is not None:
            emit("Running plugin migrations...")
            migrate_futures = plugin_host.on_project_migrate(app_ctx=app_ctx, project=project)
            for fut in migrate_futures:
                fut.result(timeout=plugin_migrate_timeout_seconds)

            emit("Initializing plugins...")
            opened_futures = plugin_host.on_project_opened(app_ctx=app_ctx, project=project)
            if await_plugin_opened:
                for fut in opened_futures:
                    fut.result(timeout=plugin_opened_timeout_seconds)

        schedule_project_meta_write(app_ctx, project)
        return project
    except ProjectCloseError:
        # Preserve close error shape for callers that want to special-case it.
        raise
    except Exception as exc:
        log.exception(
            "Project open failed; cleaning up",
            extra={"operation": "project_open", "phase": "error"},
        )
        try:
            app_ctx.events.publish(
                EventHub.PROJECT_OPEN_FAILED,
                ProjectOpenFailed(project_root=Path(project_root), error=str(exc), timestamp_s=time.time()),
            )
        except Exception:
            log.debug("Failed to publish project open failed event (best-effort)", exc_info=True)
        try:
            close_project(app_ctx, reason="open_failed")
        except Exception:
            log.warning(
                "Failed to clean up after project open failure (best-effort)",
                extra={"operation": "project_open", "phase": "warning"},
                exc_info=True,
            )
        raise ProjectOpenError(
            phase="open_project_with_plugins",
            message=f"Failed to open project: {project_root}",
            cause=exc,
        ) from exc


def close_project(app_ctx: AppContext, *, reason: str = "close") -> None:
    """Close the currently active project (if any)."""
    if app_ctx is None:
        app_ctx = get_app_context()
    current = app_ctx.active_project
    if current is None:
        return
    _require_not_ui_thread("close_project")
    try:
        try:
            app_ctx.events.publish(
                EventHub.PROJECT_CLOSING,
                ProjectClosing(project_root=current.project_root, reason=str(reason), timestamp_s=time.time()),
            )
        except Exception:
            log.debug("Failed to publish project closing event (best-effort)", exc_info=True)

        # Best-effort flush to reduce risk of dropping queued work. Do not call
        # this function on the UI thread; use a background/loader stage.
        try:
            current.project_db.flush().result(timeout=10.0)
        except Exception:
            log.warning(
                "Best-effort project DB flush failed during close_project",
                extra={"operation": "project_close", "phase": "warning"},
                exc_info=True,
            )

        current.project_db.close()
    finally:
        app_ctx.active_project = None
        try:
            now = time.time()
            app_ctx.events.publish(EventHub.PROJECT_CLOSED, ProjectClosed(project_root=current.project_root, timestamp_s=now))
            app_ctx.events.publish(
                EventHub.ACTIVE_PROJECT_CHANGED,
                ActiveProjectChanged(previous_root=current.project_root, current_root=None, timestamp_s=now),
            )
        except Exception:
            log.debug("Failed to publish project close events (best-effort)", exc_info=True)


def close_project_blocking(
    app_ctx: AppContext | None,
    *,
    timeout_seconds: float = 30.0,
    reason: str = "close",
) -> None:
    """
    Close the active project with flush guarantees.

    This function is plugin-aware:
    - invokes registered project flush hooks
    - flushes the project DB executor (ensuring queued transactions commit)
    - flushes the shared IO writer (ensuring queued file writes commit)

    This may block. Do not call it on the UI thread.
    """
    if app_ctx is None:
        app_ctx = get_app_context()
    _require_not_ui_thread("close_project_blocking")
    current = app_ctx.active_project
    if current is None:
        return

    timeout = max(0.0, float(timeout_seconds))
    deadline = time.monotonic() + timeout if timeout > 0 else None

    def remaining() -> float | None:
        if deadline is None:
            return None
        return max(0.0, deadline - time.monotonic())

    try:
        app_ctx.events.publish(
            EventHub.PROJECT_CLOSING,
            ProjectClosing(project_root=current.project_root, reason=str(reason), timestamp_s=time.time()),
        )
    except Exception:
        log.debug("Failed to publish project closing event (best-effort)", exc_info=True)

    # 1) Plugin flush hooks (plugins own their pipelines).
    hook_futures: list[Future[object]] = []
    for hook in list(app_ctx.project_flush_hooks):
        result = hook(current)
        if result is None:
            continue
        if isinstance(result, (list, tuple)):
            hook_futures.extend([f for f in result if isinstance(f, Future)])
        elif isinstance(result, Future):
            hook_futures.append(result)

    hook_errors: list[Exception] = []
    for fut in hook_futures:
        try:
            fut.result(timeout=remaining())
        except Exception as exc:
            hook_errors.append(exc)

    if hook_errors:
        for exc in hook_errors:
            log.error(
                "Project flush hook failed: %s",
                exc,
                extra={"operation": "project_close", "phase": "error"},
            )
        raise ProjectCloseError(
            phase="plugin_flush_hooks",
            message=f"{len(hook_errors)} plugin flush hook(s) failed; project remains open",
            cause=hook_errors[0],
        )

    # 2) DB flush (authoritative project state).
    try:
        current.project_db.flush().result(timeout=remaining())
    except Exception as exc:
        raise ProjectCloseError(
            phase="db_flush",
            message="Project DB flush failed; project remains open",
            cause=exc,
        )

    # 3) IO flush (derived artifacts / exports / caches).
    try:
        app_ctx.io.flush().result(timeout=remaining())
    except Exception as exc:
        raise ProjectCloseError(
            phase="io_flush",
            message="Background IO flush failed; project remains open",
            cause=exc,
        )

    # 4) Close resources.
    try:
        current.project_db.close()
    finally:
        app_ctx.active_project = None
        try:
            now = time.time()
            app_ctx.events.publish(EventHub.PROJECT_CLOSED, ProjectClosed(project_root=current.project_root, timestamp_s=now))
            app_ctx.events.publish(
                EventHub.ACTIVE_PROJECT_CHANGED,
                ActiveProjectChanged(previous_root=current.project_root, current_root=None, timestamp_s=now),
            )
        except Exception:
            log.debug("Failed to publish project close events (best-effort)", exc_info=True)
