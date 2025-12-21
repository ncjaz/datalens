from __future__ import annotations

"""
Media index domain contracts (V2).

These dataclasses describe the *shape* of data stored in / referenced from the
core project media index (``media_files``).

They are Qt-free and can be used by plugins and services.
"""

from dataclasses import dataclass
from typing import Literal

from datalens.domain.plugin import PluginId

MediaId = str
MediaSourceKind = Literal["capture", "watcher", "import", "manual", "other"]


@dataclass(frozen=True)
class MediaRegisterRequest:
    """
    Request payload for registering a project file into the core media index.

    All paths are project-relative (portable).
    """

    relative_path: str
    source_kind: MediaSourceKind = "other"
    source_plugin_id: PluginId | None = None
    created_at_s: float | None = None
    mime: str | None = None


@dataclass(frozen=True)
class MediaFileRecord:
    """
    Canonical record for a file in the core media index.
    """

    media_id: MediaId
    relative_path: str
    dir_rel: str
    filename: str
    ext: str
    size_bytes: int
    sha256: str | None
    created_at_s: float | None
    discovered_at_s: float
    source_plugin_id: PluginId | None
    source_kind: str
    mime: str | None


__all__ = ["MediaFileRecord", "MediaId", "MediaRegisterRequest", "MediaSourceKind"]

