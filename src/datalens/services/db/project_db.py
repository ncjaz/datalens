from __future__ import annotations

import json
import queue
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar

from datalens.domain.plugin import PluginId
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

    def kv_get(self, plugin_id: PluginId, key: str) -> Future[object | None]:
        """Return the JSON value for (plugin_id, key) or None if missing."""

    def kv_set(self, plugin_id: PluginId, key: str, value: object) -> Future[None]:
        """Upsert the JSON value for (plugin_id, key)."""

    def flush(self) -> Future[None]:
        """
        Return a Future that completes once all previously submitted tasks have finished.

        This does not close the DB; it is used to guarantee all queued work has
        been committed before project close.
        """

    def close(self) -> None:
        """Stop the executor and close the underlying connection(s)."""


@dataclass(frozen=True)
class _DbTask:
    fn: Callable[[sqlite3.Connection], Any]
    future: Future[Any]


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
        return self._submit(fn)

    def execute_read(self, fn: Callable[[sqlite3.Connection], T]) -> Future[T]:
        return self._submit(fn)

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

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if not self._ready.done():
                try:
                    self._ready.set_exception(RuntimeError("ProjectDb closed before connection opened"))
                except Exception:
                    pass
        self._tasks.put(None)
        self._thread.join(timeout=2.0)

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

    def _submit(self, fn: Callable[[sqlite3.Connection], T]) -> Future[T]:
        with self._lock:
            if self._closed:
                future: Future[T] = Future()
                future.set_exception(RuntimeError("ProjectDb is closed"))
                return future

        future = Future()
        self._tasks.put(_DbTask(fn=fn, future=future))
        return future  # type: ignore[return-value]

    def _run(self) -> None:
        try:
            conn = open_connection(self._db_path)
        except Exception as exc:
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
                    result = task.fn(conn)
                    conn.commit()
                    task.future.set_result(result)
                except Exception as exc:
                    conn.rollback()
                    task.future.set_exception(exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass
