from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import NewType, Optional

from .projects import ProjectId

MediaId = NewType("MediaId", int)


class MediaType(Enum):
    IMAGE = auto()
    VIDEO = auto()
    OTHER = auto()


@dataclass(frozen=True)
class MediaItemSummary:
    """
    Summary of a media item suitable for lists/grids and quick filters.

    Image pixels are not part of the domain; those are handled by the UI
    and infrastructure. Paths are expected to be project-relative in SQL.
    """

    id: MediaId
    project_id: ProjectId
    relative_path: Path
    media_type: MediaType
    width: Optional[int]
    height: Optional[int]
    has_annotations: bool
    is_flagged: bool
    created_at: datetime
    updated_at: datetime

    @property
    def filename(self) -> str:
        return self.relative_path.name


@dataclass(frozen=True)
class MediaFilter:
    """
    Filter parameters for listing media from a service.

    This stays intentionally simple; services can extend with additional
    filter arguments as needed.
    """

    only_flagged: bool = False
    only_with_annotations: bool = False
    media_type: Optional[MediaType] = None
