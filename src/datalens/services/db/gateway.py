from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional


def open_connection(db_path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    """
    Open a SQLite connection for a project database.

    Notes:
    - Uses `check_same_thread=False` so the connection can be owned by a
      dedicated worker thread (writer/executor).
    - Applies standard pragmas via `configure_connection`.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if read_only:
        # `mode=ro` requires URI form. Keep a conservative timeout because reads
        # may still contend with a writer in WAL mode.
        uri = db_path.as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(db_path, check_same_thread=False)

    configure_connection(conn, read_only=read_only)
    return conn


def configure_connection(conn: sqlite3.Connection, *, read_only: bool = False) -> None:
    """
    Apply standard project database pragmas.

    Defaults mirror V1 goals: safe, responsive, and WAL-friendly.
    """
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    if not read_only:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """
    Transaction context manager.

    Ensures commit/rollback around a block. Intended for use on a single
    connection (typically owned by the DB executor thread).
    """
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def execute(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[object] | Mapping[str, object] = (),
) -> sqlite3.Cursor:
    return conn.execute(sql, params)


def query_one(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[object] | Mapping[str, object] = (),
) -> tuple[Any, ...] | None:
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return tuple(row) if row is not None else None


def query_all(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[object] | Mapping[str, object] = (),
) -> list[tuple[Any, ...]]:
    cur = conn.execute(sql, params)
    return [tuple(r) for r in cur.fetchall()]


class DbGateway:
    """
    Minimal convenience wrapper around a SQLite connection.

    This keeps calling code terse without hiding SQL. Higher-level repositories
    should be built on top of this, not ad-hoc helper functions.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def execute(
        self,
        sql: str,
        params: Sequence[object] | Mapping[str, object] = (),
    ) -> sqlite3.Cursor:
        return execute(self._conn, sql, params)

    def query_one(
        self,
        sql: str,
        params: Sequence[object] | Mapping[str, object] = (),
    ) -> tuple[Any, ...] | None:
        return query_one(self._conn, sql, params)

    def query_all(
        self,
        sql: str,
        params: Sequence[object] | Mapping[str, object] = (),
    ) -> list[tuple[Any, ...]]:
        return query_all(self._conn, sql, params)

    @contextmanager
    def transaction(self) -> Iterator["DbGateway"]:
        with transaction(self._conn):
            yield self

    def close(self) -> None:
        self._conn.close()
