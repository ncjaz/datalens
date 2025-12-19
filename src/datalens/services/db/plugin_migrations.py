from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import Future
from dataclasses import dataclass
import sqlite3

from datalens.domain.plugin import PluginId
from datalens.services.db.project_db import ProjectDb


@dataclass(frozen=True)
class PluginMigration:
    """
    A single plugin-owned schema migration.

    This is intentionally lightweight: plugins own their tables and can create as
    many as they want. Migrations are executed on the ProjectDb executor thread
    (never the UI thread).
    """

    schema_version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


class PluginMigrationError(RuntimeError):
    pass


def run_plugin_migrations(
    *,
    project_db: ProjectDb,
    plugin_id: PluginId,
    plugin_version: str,
    migrations: Sequence[PluginMigration],
) -> Future[int]:
    """
    Apply plugin-owned schema migrations and update the plugin's `plugin_meta` row.

    Intended usage: call from `on_project_migrate` and return the returned Future
    so the project-open pipeline can await it (non-blocking UI).

    Notes:

    - This is not a security boundary: plugin code runs in-process.
    - Use stable schemas where possible; version *data* via columns/ids rather
      than creating a new table per data version.
    """

    ordered = sorted(migrations, key=lambda m: int(m.schema_version))
    if ordered and int(ordered[0].schema_version) < 1:
        raise PluginMigrationError("Plugin schema versions must start at 1.")
    for prev, cur in zip(ordered, ordered[1:], strict=False):
        if int(cur.schema_version) <= int(prev.schema_version):
            raise PluginMigrationError("Plugin migrations must be unique and strictly increasing.")

    plugin_id_str = str(plugin_id)
    plugin_version_str = str(plugin_version).strip()
    if not plugin_version_str:
        raise PluginMigrationError("plugin_version is required to update plugin_meta.")

    def task(conn) -> int:
        row = conn.execute(
            "SELECT schema_version FROM plugin_meta WHERE plugin_id = ?",
            (plugin_id_str,),
        ).fetchone()
        current_version = int(row[0]) if row else 0

        for migration in ordered:
            target = int(migration.schema_version)
            if target <= current_version:
                continue
            migration.apply(conn)
            current_version = target

        # Record the final schema version, even if no migrations ran. This keeps
        # plugin_meta consistent and ensures `plugin_version` is updated.
        conn.execute(
            """
            INSERT INTO plugin_meta(plugin_id, plugin_version, schema_version, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(plugin_id) DO UPDATE SET
                plugin_version = excluded.plugin_version,
                schema_version = excluded.schema_version,
                updated_at = CURRENT_TIMESTAMP
            """,
            (plugin_id_str, plugin_version_str, int(current_version)),
        )
        return int(current_version)

    return project_db.execute_write(task)


__all__ = ["PluginMigration", "PluginMigrationError", "run_plugin_migrations"]
