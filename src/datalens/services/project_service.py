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

from datalens.core.context import AppContext, ProjectContext
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
        project_db.execute_write(lambda conn: ensure_core_schema(conn)).result(timeout=15.0)
    elif action == "migrate":
        project_db.execute_write(
            lambda conn: migrate_core_schema(conn, from_schema_version=from_schema_version)
        ).result(timeout=30.0)

    # Derived metadata is best effort and should not block project readiness.
    try:
        meta = project_db.execute_read(build_project_meta).result(timeout=5.0)
        io.write_json_atomic(project_meta_path(root), meta)
    except Exception:
        log.debug(
            "Failed to write derived project metadata (best-effort)",
            extra={"operation": "project_meta", "phase": "warning"},
            exc_info=True,
        )

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


def attach_project(app_ctx: AppContext, project: ProjectContext) -> None:
    """Attach a loaded project context to the app context (gating)."""
    app_ctx.active_project = project


def open_project(app_ctx: AppContext, project_root: Path) -> ProjectContext:
    """
    Open a project and attach it to the app context.

    This creates process resources (DB executor) and closes any previous project.

    Important:
        This function may block while the project DB initializes. Do not call it
        on the UI thread. Use the loader/background pipeline (or a dedicated
        async wrapper) in UI code.
    """
    _require_not_ui_thread("open_project")
    close_project(app_ctx)
    project = load_project(project_root, io=app_ctx.io)
    attach_project(app_ctx, project)
    return project


def close_project(app_ctx: AppContext) -> None:
    """Close the currently active project (if any)."""
    current = app_ctx.active_project
    if current is None:
        return
    _require_not_ui_thread("close_project")
    try:
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


def close_project_blocking(app_ctx: AppContext, *, timeout_seconds: float = 30.0) -> None:
    """
    Close the active project with flush guarantees.

    This function is plugin-aware:
    - invokes registered project flush hooks
    - flushes the project DB executor (ensuring queued transactions commit)
    - flushes the shared IO writer (ensuring queued file writes commit)

    This may block. Do not call it on the UI thread.
    """
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
        raise RuntimeError(
            f"{len(hook_errors)} plugin flush hook(s) failed; project remains open"
        ) from hook_errors[0]

    # 2) DB flush (authoritative project state).
    current.project_db.flush().result(timeout=remaining())

    # 3) IO flush (derived artifacts / exports / caches).
    app_ctx.io.flush().result(timeout=remaining())

    # 4) Close resources.
    try:
        current.project_db.close()
    finally:
        app_ctx.active_project = None
