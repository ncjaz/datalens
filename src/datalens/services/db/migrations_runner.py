from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from datalens.infra.project_paths import project_meta_path


@dataclass(frozen=True)
class AppMeta:
    """
    Database metadata stored inside the project SQLite DB.

    `app_version` and `db_version` are human-readable strings (start at "1.0").
    `schema_version` is the integer migration version (mirrors PRAGMA user_version).
    """

    app_version: str
    db_version: str
    schema_version: int


DEFAULT_APP_VERSION = "1.0"
DEFAULT_DB_VERSION = "1.0"
DEFAULT_SCHEMA_VERSION = 3


class CoreSchemaError(RuntimeError):
    """Raised when the core project database schema is invalid or incompatible."""


class ForeignDatabaseError(CoreSchemaError):
    """
    Raised when a SQLite DB exists but does not appear to be a DataLens project DB.

    We fail fast instead of creating core tables because that could corrupt a DB
    owned by another system or a plugin that (incorrectly) uses SQLite metadata
    reserved for the core app.
    """


class IncompatibleCoreSchemaError(CoreSchemaError):
    """Raised when the DB core schema version is newer than this app supports."""


def ensure_core_schema(
    conn: sqlite3.Connection,
    *,
    app_version: str = DEFAULT_APP_VERSION,
    db_version: str = DEFAULT_DB_VERSION,
    schema_version: int = DEFAULT_SCHEMA_VERSION,
) -> AppMeta:
    """
    Ensure the core project database schema exists.

    Keep core table creation in one place so project DB initialization does not
    scatter schema creation across modules.
    """
    # Core meta table (single row).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            id           INTEGER PRIMARY KEY CHECK (id = 1),
            app_version  TEXT NOT NULL,
            db_version   TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        )
        """
    )

    # Plugin KV store.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plugin_kv (
            plugin_id   TEXT NOT NULL,
            key         TEXT NOT NULL,
            value_json  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (plugin_id, key)
        )
        """
    )

    if int(schema_version) >= 2:
        # Plugin metadata (core-owned table; plugins own their rows).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plugin_meta (
                plugin_id       TEXT PRIMARY KEY,
                plugin_version  TEXT NOT NULL,
                schema_version  INTEGER NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """
        )

    if int(schema_version) >= 3:
        # Project media index (core-owned): canonical table for files created/discovered in a project.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS media_files (
                media_id         TEXT PRIMARY KEY,
                relative_path    TEXT NOT NULL UNIQUE,
                dir_rel          TEXT NOT NULL,
                filename         TEXT NOT NULL,
                ext              TEXT NOT NULL,
                size_bytes       INTEGER NOT NULL DEFAULT 0,
                sha256           TEXT NULL,
                created_at_s     REAL NULL,
                discovered_at_s  REAL NOT NULL,
                source_plugin_id TEXT NULL,
                source_kind      TEXT NOT NULL,
                mime             TEXT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS media_files_dir_rel ON media_files(dir_rel)")
        conn.execute("CREATE INDEX IF NOT EXISTS media_files_sha256 ON media_files(sha256)")
        conn.execute("CREATE INDEX IF NOT EXISTS media_files_discovered_at ON media_files(discovered_at_s)")

    # Initialize or update the app_meta row.
    conn.execute(
        """
        INSERT INTO app_meta(id, app_version, db_version, created_at, updated_at)
        VALUES (1, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        ON CONFLICT(id) DO UPDATE SET
            app_version=excluded.app_version,
            db_version=excluded.db_version,
            updated_at=excluded.updated_at
        """,
        (str(app_version), str(db_version)),
    )

    # Maintain an integer migration version using PRAGMA user_version.
    current_user_version = _pragma_int(conn, "user_version")
    if current_user_version == 0:
        conn.execute(f"PRAGMA user_version = {int(schema_version)};")
        current_user_version = int(schema_version)

    return AppMeta(
        app_version=str(app_version),
        db_version=str(db_version),
        schema_version=int(current_user_version),
    )


def read_app_meta(conn: sqlite3.Connection) -> AppMeta:
    try:
        row = conn.execute("SELECT app_version, db_version FROM app_meta WHERE id = 1").fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        return AppMeta(
            app_version=DEFAULT_APP_VERSION,
            db_version=DEFAULT_DB_VERSION,
            schema_version=_pragma_int(conn, "user_version"),
        )
    return AppMeta(
        app_version=str(row[0]),
        db_version=str(row[1]),
        schema_version=_pragma_int(conn, "user_version"),
    )


def list_user_tables(conn: sqlite3.Connection) -> list[str]:
    """
    Return non-system table names for metadata/debugging.
    """
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [str(r[0]) for r in rows]


def has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (str(table_name),),
    ).fetchone()
    return row is not None


@dataclass(frozen=True)
class CoreDbInspection:
    """
    Read-only snapshot of core DB metadata used for compatibility checks.
    """

    user_version: int
    user_tables: tuple[str, ...]
    has_app_meta: bool
    has_plugin_kv: bool
    has_plugin_meta: bool
    has_media_files: bool


def inspect_core_db(conn: sqlite3.Connection) -> CoreDbInspection:
    """
    Inspect a DB read-only and return the information needed to decide if we can open it.

    This must never write to the DB.
    """
    tables = tuple(list_user_tables(conn))
    return CoreDbInspection(
        user_version=_pragma_int(conn, "user_version"),
        user_tables=tables,
        has_app_meta=has_table(conn, "app_meta"),
        has_plugin_kv=has_table(conn, "plugin_kv"),
        has_plugin_meta=has_table(conn, "plugin_meta"),
        has_media_files=has_table(conn, "media_files"),
    )


@dataclass(frozen=True)
class CoreOpenDecision:
    """
    Decision for what core action to perform during project DB open.

    `migrate` is used when the DB is a DataLens DB but has an older schema
    version. Migrations must be core-only and additive where possible.
    """

    kind: Literal["ensure", "ok", "migrate"]
    from_schema_version: int | None = None
    to_schema_version: int = DEFAULT_SCHEMA_VERSION


def decide_core_open_action(
    inspection: CoreDbInspection,
    *,
    supported_schema_version: int = DEFAULT_SCHEMA_VERSION,
) -> CoreOpenDecision:
    """
    Decide what core action is safe to take for a project DB.

    Returns:
        CoreOpenDecision:
            kind="ensure": Core schema should be created/ensured (additive writes only).
            kind="ok": DB is compatible; no core writes required during open.
            kind="migrate": DB is compatible but older; run core migrations.

    Raises:
        ForeignDatabaseError: the DB looks non-DataLens or ambiguous.
        IncompatibleCoreSchemaError: the DB core schema is newer than this app supports.
        CoreSchemaError: other unsupported/unknown states.
    """
    v = int(inspection.user_version)

    # New/empty DB: safe to initialize core schema.
    if v == 0 and len(inspection.user_tables) == 0:
        return CoreOpenDecision(kind="ensure")

    # DataLens DB should have core meta. If it doesn't, be conservative and refuse.
    if not inspection.has_app_meta:
        raise ForeignDatabaseError(
            "SQLite DB has user tables but no DataLens core metadata (app_meta); refusing to modify it."
        )

    if v > supported_schema_version:
        raise IncompatibleCoreSchemaError(
            f"Project DB schema version {v} is newer than supported {supported_schema_version}."
        )

    if v == supported_schema_version:
        # If core meta exists but other core tables are missing, we can apply a safe,
        # additive "repair" by ensuring core schema exists.
        if inspection.has_plugin_kv and (v < 2 or inspection.has_plugin_meta) and (v < 3 or inspection.has_media_files):
            return CoreOpenDecision(kind="ok")
        return CoreOpenDecision(kind="ensure")

    # Older schema: migrate core-only tables.
    return CoreOpenDecision(
        kind="migrate",
        from_schema_version=v,
        to_schema_version=int(supported_schema_version),
    )


def migrate_core_schema(
    conn: sqlite3.Connection,
    *,
    from_schema_version: int,
    to_schema_version: int = DEFAULT_SCHEMA_VERSION,
    app_version: str = DEFAULT_APP_VERSION,
    db_version: str = DEFAULT_DB_VERSION,
) -> AppMeta:
    """
    Apply core-only migrations for a project DB.

    Migrations must be additive where possible and must never touch plugin-owned
    tables beyond core-owned metadata.
    """
    from_v = int(from_schema_version)
    to_v = int(to_schema_version)
    if from_v < 0 or to_v < 0:
        raise CoreSchemaError(f"Invalid schema versions: {from_v} -> {to_v}")
    if from_v > to_v:
        raise CoreSchemaError(f"Refusing to downgrade schema: {from_v} -> {to_v}")

    current = _pragma_int(conn, "user_version")
    if current != from_v:
        raise CoreSchemaError(
            f"Migration version mismatch: expected user_version {from_v}, found {current}"
        )

    # v0 -> v1: bring the DB up to the initial V2 core schema and set user_version.
    v = from_v
    if v == 0 and to_v >= 1:
        ensure_core_schema(
            conn,
            app_version=app_version,
            db_version=db_version,
            schema_version=1,
        )
        v = 1

    # v1 -> v2: add plugin_meta table (core-owned) and bump user_version.
    if v == 1 and to_v >= 2:
        ensure_core_schema(
            conn,
            app_version=app_version,
            db_version=db_version,
            schema_version=2,
        )
        conn.execute("PRAGMA user_version = 2;")
        v = 2

    # v2 -> v3: add core media index table and bump user_version.
    if v == 2 and to_v >= 3:
        ensure_core_schema(
            conn,
            app_version=app_version,
            db_version=db_version,
            schema_version=3,
        )
        conn.execute("PRAGMA user_version = 3;")
        v = 3

    if v != to_v:
        raise CoreSchemaError(f"No migration path implemented for schema {v} -> {to_v}")

    return read_app_meta(conn)


def build_project_meta(conn: sqlite3.Connection) -> dict[str, object]:
    """
    Return a JSON-serializable snapshot describing the project DB.

    This is derived from SQLite and can be regenerated at any time.
    """
    meta = read_app_meta(conn)
    return {
        "app_version": meta.app_version,
        "db_version": meta.db_version,
        "schema_version": meta.schema_version,
        "tables": list_user_tables(conn),
    }


def write_project_meta_json(project_root: Path, *, meta: dict[str, object]) -> None:
    """
    Write `<project_root>/.datalens/project_meta.json` atomically.

    Intended for use by higher-level async IO helpers; kept sync and small.
    """
    path = project_meta_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _pragma_int(conn: sqlite3.Connection, pragma_name: str) -> int:
    row: Any = conn.execute(f"PRAGMA {pragma_name};").fetchone()
    try:
        return int(row[0]) if row else 0
    except Exception:
        return 0
