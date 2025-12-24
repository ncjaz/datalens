from __future__ import annotations

"""
Core media index service (V2).

Owns the core ``media_files`` table and provides a plugin-safe registration API
via the CommandBus.
"""

import time
import uuid
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any

from datalens.core.context import AppContext
from datalens.core.events import EventHub
from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.domain.system.media_index import MediaFileRecord, MediaRegisterRequest
from datalens.services.commands.bus import CommandContext

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datalens.core.context import AppContext

log = get_logger(__name__)


def _to_posix_rel_path(relative_path: str) -> str:
    rel = str(relative_path or "").strip().replace("\\", "/")
    rel = str(PurePosixPath(rel))
    rel = rel.lstrip("/")
    if rel in {"", "."}:
        raise ValueError("relative_path must be a non-empty project-relative path")
    if rel.startswith("../") or "/../" in rel or rel == "..":
        raise ValueError("relative_path must not escape the project root")
    return rel


def _split_dir_and_name(rel_posix: str) -> tuple[str, str, str]:
    p = PurePosixPath(rel_posix)
    filename = p.name
    ext = p.suffix.lstrip(".").lower()
    parent = str(p.parent)
    dir_rel = "" if parent in {"", "."} else parent
    return dir_rel, filename, ext


class MediaIndexClient:
    """
    Non-UI-blocking query facade over the core media index.

    All methods return Futures from the project DB executor.
    """

    def __init__(self, app_ctx: "AppContext") -> None:
        self._app_ctx = app_ctx

    def list_latest(self, *, limit: int = 50) -> Any:
        project = self._app_ctx.require_project()
        lim = max(1, int(limit))

        def run(conn):
            rows = conn.execute(
                """
                SELECT media_id, relative_path, dir_rel, filename, ext, size_bytes, sha256,
                       created_at_s, discovered_at_s, source_plugin_id, source_kind, mime
                FROM media_files
                ORDER BY discovered_at_s DESC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()
            return [
                MediaFileRecord(
                    media_id=str(r[0]),
                    relative_path=str(r[1]),
                    dir_rel=str(r[2]),
                    filename=str(r[3]),
                    ext=str(r[4]),
                    size_bytes=int(r[5] or 0),
                    sha256=str(r[6]) if r[6] is not None else None,
                    created_at_s=float(r[7]) if r[7] is not None else None,
                    discovered_at_s=float(r[8]),
                    source_plugin_id=PluginId(str(r[9])) if r[9] is not None else None,
                    source_kind=str(r[10]),
                    mime=str(r[11]) if r[11] is not None else None,
                )
                for r in rows
            ]

        return project.project_db.execute_read(run)

    def list_by_dir(self, dir_rel: str, *, limit: int = 200) -> Any:
        project = self._app_ctx.require_project()
        lim = max(1, int(limit))
        d = str(dir_rel or "").strip().replace("\\", "/")
        d = "" if d in {"", "."} else str(PurePosixPath(d))

        def run(conn):
            rows = conn.execute(
                """
                SELECT media_id, relative_path, dir_rel, filename, ext, size_bytes, sha256,
                       created_at_s, discovered_at_s, source_plugin_id, source_kind, mime
                FROM media_files
                WHERE dir_rel = ?
                ORDER BY discovered_at_s DESC
                LIMIT ?
                """,
                (d, lim),
            ).fetchall()
            return [
                MediaFileRecord(
                    media_id=str(r[0]),
                    relative_path=str(r[1]),
                    dir_rel=str(r[2]),
                    filename=str(r[3]),
                    ext=str(r[4]),
                    size_bytes=int(r[5] or 0),
                    sha256=str(r[6]) if r[6] is not None else None,
                    created_at_s=float(r[7]) if r[7] is not None else None,
                    discovered_at_s=float(r[8]),
                    source_plugin_id=PluginId(str(r[9])) if r[9] is not None else None,
                    source_kind=str(r[10]),
                    mime=str(r[11]) if r[11] is not None else None,
                )
                for r in rows
            ]

        return project.project_db.execute_read(run)


def register_media_file(app_ctx: "AppContext", req: MediaRegisterRequest) -> MediaFileRecord:
    """
    Register a file in the active project into `media_files`.

    This is synchronous and intended to be run off the UI thread (e.g. CommandBus handler).
    """
    project = app_ctx.require_project()
    rel_posix = _to_posix_rel_path(req.relative_path)
    dir_rel, filename, ext = _split_dir_and_name(rel_posix)

    abs_path = (project.project_root / Path(rel_posix)).resolve()
    size_bytes = 0
    created_at_s = req.created_at_s
    try:
        st = abs_path.stat()
        size_bytes = int(getattr(st, "st_size", 0) or 0)
        if created_at_s is None:
            created_at_s = float(getattr(st, "st_mtime", 0.0) or 0.0)
    except Exception:
        pass

    discovered_at_s = time.time()
    source_plugin_id = req.source_plugin_id
    source_kind = str(req.source_kind or "other")

    def db_upsert(conn) -> tuple[str, str | None]:
        row = conn.execute(
            "SELECT media_id, sha256 FROM media_files WHERE relative_path = ?",
            (rel_posix,),
        ).fetchone()
        if row is not None:
            media_id = str(row[0])
            sha256 = str(row[1]) if row[1] is not None else None
            conn.execute(
                """
                UPDATE media_files
                SET dir_rel=?,
                    filename=?,
                    ext=?,
                    size_bytes=?,
                    created_at_s=?,
                    discovered_at_s=?,
                    source_plugin_id=?,
                    source_kind=?,
                    mime=?
                WHERE relative_path=?
                """,
                (
                    dir_rel,
                    filename,
                    ext,
                    int(size_bytes),
                    created_at_s,
                    float(discovered_at_s),
                    str(source_plugin_id) if source_plugin_id is not None else None,
                    source_kind,
                    req.mime,
                    rel_posix,
                ),
            )
            return media_id, sha256

        media_id = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO media_files(
                media_id, relative_path, dir_rel, filename, ext,
                size_bytes, sha256, created_at_s, discovered_at_s,
                source_plugin_id, source_kind, mime
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
            """,
            (
                media_id,
                rel_posix,
                dir_rel,
                filename,
                ext,
                int(size_bytes),
                created_at_s,
                float(discovered_at_s),
                str(source_plugin_id) if source_plugin_id is not None else None,
                source_kind,
                req.mime,
            ),
        )
        return media_id, None

    media_id, sha256 = project.project_db.execute_core_write(db_upsert).result(timeout=15.0)

    record = MediaFileRecord(
        media_id=str(media_id),
        relative_path=rel_posix,
        dir_rel=dir_rel,
        filename=filename,
        ext=ext,
        size_bytes=int(size_bytes),
        sha256=sha256,
        created_at_s=created_at_s,
        discovered_at_s=float(discovered_at_s),
        source_plugin_id=source_plugin_id,
        source_kind=source_kind,
        mime=req.mime,
    )

    try:
        app_ctx.events.publish(EventHub.MEDIA_DISCOVERED, {"media": asdict(record)})
        app_ctx.events.publish(EventHub.MEDIA_LIST_UPDATED, {"timestamp_s": time.time()})
    except Exception:
        log.debug("Failed to publish media index events (best-effort)", exc_info=True)

    log.info(
        "Media registered",
        extra={
            "operation": "media_index",
            "phase": "register",
            "media_id": record.media_id,
            "relative_path": record.relative_path,
            "source_kind": record.source_kind,
            "source_plugin_id": str(record.source_plugin_id) if record.source_plugin_id else None,
        },
    )

    return record


def handle_cmd_media_register(app_ctx: "AppContext", ctx: CommandContext) -> object:
    payload = ctx.payload

    if isinstance(payload, MediaRegisterRequest):
        req = payload
    elif isinstance(payload, dict):
        rel = payload.get("relative_path")
        if not isinstance(rel, str):
            raise TypeError("CMD_MEDIA_REGISTER payload.relative_path must be a string")
        source_kind = payload.get("source_kind", "other")
        if not isinstance(source_kind, str):
            source_kind = str(source_kind)
        created_at_s = payload.get("created_at_s")
        if created_at_s is not None:
            created_at_s = float(created_at_s)
        mime = payload.get("mime")
        if mime is not None and not isinstance(mime, str):
            mime = str(mime)
        source_plugin_id = payload.get("source_plugin_id")
        pid = PluginId(str(source_plugin_id)) if source_plugin_id is not None else None
        req = MediaRegisterRequest(
            relative_path=rel,
            source_kind=source_kind,  # type: ignore[arg-type]
            source_plugin_id=pid,
            created_at_s=created_at_s,
            mime=mime,
        )
    else:
        raise TypeError("CMD_MEDIA_REGISTER payload must be MediaRegisterRequest or dict")

    # If caller plugin id exists, prefer it as the source plugin id unless explicitly set.
    if req.source_plugin_id is None and ctx.caller_plugin_id is not None:
        req = MediaRegisterRequest(
            relative_path=req.relative_path,
            source_kind=req.source_kind,
            source_plugin_id=ctx.caller_plugin_id,
            created_at_s=req.created_at_s,
            mime=req.mime,
        )

    record = register_media_file(app_ctx, req)
    return asdict(record)


__all__ = ["MediaIndexClient", "handle_cmd_media_register", "register_media_file"]
