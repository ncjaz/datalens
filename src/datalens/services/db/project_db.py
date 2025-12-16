from __future__ import annotations

import json
import queue
import re
import sqlite3
import threading
import contextvars
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.domain.plugin_meta import PluginMeta
from datalens.infra.project_paths import project_db_path
from datalens.services.db.gateway import open_connection


T = TypeVar("T")


class ProjectDb(Protocol):
    """
    Plugin-facing project database interface.

    This API is intentionally small so it remains stable while the internal
    implementation evolves (single DB thread now -> read pooling later).
    """

    def execute_write(self, fn: Callable[[sqlite3.Connection], T]) -> Future[T]:
        """Run `fn(conn)` on the DB executor and return a Future for its result."""

    def execute_read(self, fn: Callable[[sqlite3.Connection], T]) -> Future[T]:
        """Run `fn(conn)` on the DB executor and return a Future for its result."""

    def execute_core_write(self, fn: Callable[[sqlite3.Connection], T]) -> Future[T]:
        """
        Run a core-only write callable.

        Core-only writes must not touch plugin-owned tables (beyond core-owned metadata).
        """

    def execute_core_read(self, fn: Callable[[sqlite3.Connection], T]) -> Future[T]:
        """Run a core-only read callable (symmetry helper)."""

    def kv_get(self, plugin_id: PluginId, key: str) -> Future[object | None]:
        """Return the JSON value for (plugin_id, key) or None if missing."""

    def kv_set(self, plugin_id: PluginId, key: str, value: object) -> Future[None]:
        """Upsert the JSON value for (plugin_id, key)."""

    def plugin_meta_get(self, plugin_id: PluginId) -> Future[PluginMeta | None]:
        """Return plugin-owned metadata for `plugin_id` or None if missing."""

    def plugin_meta_set(
        self,
        plugin_id: PluginId,
        *,
        plugin_version: str,
        schema_version: int,
    ) -> Future[None]:
        """Upsert plugin-owned metadata for `plugin_id`."""

    def flush(self) -> Future[None]:
        """
        Return a Future that completes once all previously submitted tasks have finished.

        This does not close the DB; it is used to guarantee all queued work has
        been committed before project close.
        """

    def close(self, *, flush: bool = False, timeout_seconds: float = 2.0) -> None:
        """Stop the executor and close the underlying connection(s)."""


@dataclass(frozen=True)
class _DbTask:
    fn: Callable[[sqlite3.Connection], Any]
    future: Future[Any]
    context: contextvars.Context
    core_only: bool = False


class CoreDbOwnershipError(RuntimeError):
    pass


_CORE_TABLES: set[str] = {"app_meta", "plugin_kv", "plugin_meta"}
_SQL_WS = re.compile(r"\s+")
_SQL_QUOTED = re.compile(r'^[`"\[]?(.*?)[`"\]]?$')


def _normalize_ident(ident: str) -> str:
    ident = _SQL_WS.sub(" ", ident.strip())
    m = _SQL_QUOTED.match(ident)
    if m:
        ident = m.group(1)
    if "." in ident:
        ident = ident.split(".")[-1]
    return ident.strip().strip('"').strip("`").strip("[").strip("]").lower()


def _extract_table_after(prefix_pattern: str, sql_upper: str) -> str | None:
    m = re.search(prefix_pattern, sql_upper)
    if not m:
        return None
    return m.group(1)


def _assert_core_only_sql(statement: str) -> None:
    """
    Best-effort guard: refuse statements that would mutate non-core tables.

    This is not a SQL parser. It is intentionally conservative and designed to
    catch accidental core mutations of plugin-owned tables during migrations and
    other core-managed phases.
    """
    s = statement.strip()
    if not s:
        return

    s_upper = s.upper()
    if s_upper.startswith(("PRAGMA ", "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE")):
        return

    # Disallow destructive operations in core-only mode (core migrations should be additive).
    if s_upper.startswith("DROP "):
        raise CoreDbOwnershipError(f"Core-only DB operation attempted: {s.strip()}")

    candidates: list[str] = []

    table = _extract_table_after(r"\bINSERT\s+INTO\s+([^\s(]+)", s_upper)
    if table:
        candidates.append(table)

    table = _extract_table_after(r"\bUPDATE\s+([^\s]+)", s_upper)
    if table:
        candidates.append(table)

    table = _extract_table_after(r"\bDELETE\s+FROM\s+([^\s]+)", s_upper)
    if table:
        candidates.append(table)

    table = _extract_table_after(r"\bALTER\s+TABLE\s+([^\s]+)", s_upper)
    if table:
        candidates.append(table)

    table = _extract_table_after(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)", s_upper)
    if table:
        candidates.append(table)

    if "CREATE INDEX" in s_upper or "CREATE UNIQUE INDEX" in s_upper:
        table = _extract_table_after(r"\bON\s+([^\s(]+)", s_upper)
        if table:
            candidates.append(table)

    for raw in candidates:
        ident = _normalize_ident(raw)
        if ident.startswith("sqlite_"):
            continue
        if ident not in _CORE_TABLES:
            raise CoreDbOwnershipError(
                f"Core-only DB operation attempted to modify non-core table {ident!r}: {s.strip()}"
            )


class SqliteProjectDb(ProjectDb):
    """
    Minimal per-project SQLite executor.

    Implementation notes:

    - Uses a single background thread.
    - Both reads and writes run on the same thread/connection for now.
    - The interface is designed so reads can be upgraded to a pool later without
      changing plugin code.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._tasks: queue.Queue[_DbTask | None] = queue.Queue()
        self._closed = False
        self._lock = threading.Lock()
        self._ready: Future[None] = Future()

        self._thread = threading.Thread(
            target=self._run,
            name=f"ProjectDb({self._db_path.name})",
            daemon=True,
        )
        self._thread.start()

    @classmethod
    def for_project_root(cls, project_root: Path) -> "SqliteProjectDb":
        """
        Convenience constructor that uses the standard V2 project DB layout:
        `<project_root>/.datalens/project.sqlite`.
        """
        return cls(project_db_path(project_root))

    @property
    def db_path(self) -> Path:
        return self._db_path

    def ready(self) -> Future[None]:
        """
        Return a Future that completes when the DB is ready for use.

        Callers must not block the UI thread waiting for this future. Use the
        loader/background pipeline to await readiness.
        """
        return self._ready

    def execute_write(self, fn: Callable[[sqlite3.Connection], T]) -> Future[T]:
        return self._submit(fn, core_only=False)

    def execute_read(self, fn: Callable[[sqlite3.Connection], T]) -> Future[T]:
        return self._submit(fn, core_only=False)

    def execute_core_write(self, fn: Callable[[sqlite3.Connection], T]) -> Future[T]:
        return self._submit(fn, core_only=True)

    def execute_core_read(self, fn: Callable[[sqlite3.Connection], T]) -> Future[T]:
        return self._submit(fn, core_only=True)

    def kv_get(self, plugin_id: PluginId, key: str) -> Future[object | None]:
        plugin = str(plugin_id)
        k = str(key)

        def read(conn: sqlite3.Connection) -> object | None:
            cur = conn.execute(
                "SELECT value_json FROM plugin_kv WHERE plugin_id = ? AND key = ?",
                (plugin, k),
            )
            row = cur.fetchone()
            if row is None:
                return None
            try:
                return json.loads(row[0])
            except Exception:
                return None

        return self.execute_read(read)

    def kv_set(self, plugin_id: PluginId, key: str, value: object) -> Future[None]:
        plugin = str(plugin_id)
        k = str(key)
        payload = json.dumps(value)

        def write(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO plugin_kv(plugin_id, key, value_json, updated_at)
                VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                ON CONFLICT(plugin_id, key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=excluded.updated_at
                """,
                (plugin, k, payload),
            )

        return self.execute_write(write)

    def plugin_meta_get(self, plugin_id: PluginId) -> Future[PluginMeta | None]:
        plugin = str(plugin_id)

        def read(conn: sqlite3.Connection) -> PluginMeta | None:
            row = conn.execute(
                "SELECT plugin_version, schema_version, updated_at FROM plugin_meta WHERE plugin_id = ?",
                (plugin,),
            ).fetchone()
            if row is None:
                return None
            try:
                schema_version = int(row[1])
            except Exception:
                schema_version = 0
            return PluginMeta(
                plugin_id=plugin_id,
                plugin_version=str(row[0]),
                schema_version=schema_version,
                updated_at=str(row[2]),
            )

        return self.execute_read(read)

    def plugin_meta_set(
        self,
        plugin_id: PluginId,
        *,
        plugin_version: str,
        schema_version: int,
    ) -> Future[None]:
        plugin = str(plugin_id)
        version = str(plugin_version)
        schema = int(schema_version)

        def write(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO plugin_meta(plugin_id, plugin_version, schema_version, updated_at)
                VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                ON CONFLICT(plugin_id) DO UPDATE SET
                    plugin_version=excluded.plugin_version,
                    schema_version=excluded.schema_version,
                    updated_at=excluded.updated_at
                """,
                (plugin, version, schema),
            )

        return self.execute_write(write)

    def close(self, *, flush: bool = False, timeout_seconds: float = 2.0) -> None:
        """
        Stop the executor thread.

        If `flush=True`, waits (up to `timeout_seconds`) for all queued tasks to
        complete before stopping.
        """
        barrier_future: Future[None] | None = None
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if not self._ready.done():
                try:
                    self._ready.set_exception(RuntimeError("ProjectDb closed before connection opened"))
                except Exception:
                    pass
            if flush:
                barrier_future = Future()
                self._tasks.put(
                    _DbTask(
                        fn=lambda _: None,
                        future=barrier_future,
                        context=contextvars.copy_context(),
                    )
                )
            self._tasks.put(None)

        timeout = max(0.0, float(timeout_seconds))

        flush_error: Exception | None = None
        if barrier_future is not None:
            try:
                barrier_future.result(timeout=timeout)
            except Exception as exc:
                flush_error = exc

        self._thread.join(timeout=timeout)
        if flush_error is not None:
            raise flush_error

    def flush(self) -> Future[None]:
        """
        Barrier operation: completes after all previously queued tasks complete.

        Note: do not call `future.result()` for the returned future on the UI
        thread. Use the loader/background pipeline.
        """

        def barrier(_: sqlite3.Connection) -> None:
            return None

        future: Future[None] = self.execute_write(barrier)
        return future

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _submit(self, fn: Callable[[sqlite3.Connection], T], *, core_only: bool) -> Future[T]:
        with self._lock:
            if self._closed:
                future: Future[T] = Future()
                future.set_exception(RuntimeError("ProjectDb is closed"))
                return future
            future = Future()
            self._tasks.put(
                _DbTask(
                    fn=fn,
                    future=future,
                    context=contextvars.copy_context(),
                    core_only=bool(core_only),
                )
            )
            return future  # type: ignore[return-value]

    def _run(self) -> None:
        log = get_logger(__name__)
        try:
            conn = open_connection(self._db_path)
        except Exception as exc:
            log.exception(
                "Failed to open project DB connection",
                extra={"operation": "db_open", "phase": "error"},
            )
            if not self._ready.done():
                try:
                    self._ready.set_exception(exc)
                except Exception:
                    pass
            return

        if not self._ready.done():
            try:
                self._ready.set_result(None)
            except Exception:
                pass
        try:
            while True:
                task = self._tasks.get()
                if task is None:
                    return
                if task.future.cancelled():
                    continue
                try:
                    if task.core_only:
                        conn.set_trace_callback(_assert_core_only_sql)
                    result = task.context.run(task.fn, conn)
                    conn.commit()
                    task.future.set_result(result)
                except Exception as exc:
                    conn.rollback()
                    log.exception(
                        "ProjectDb task failed",
                        extra={"operation": "db_task", "phase": "error"},
                    )
                    task.future.set_exception(exc)
                finally:
                    if task.core_only:
                        try:
                            conn.set_trace_callback(None)
                        except Exception:
                            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
