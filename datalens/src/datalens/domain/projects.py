from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NewType, Optional

ProjectId = NewType("ProjectId", int)


@dataclass(frozen=True)
class ProjectSummary:
    """
    Lightweight view of a project used across the UI and plugins.

    - Does NOT include media or annotations; those are fetched on demand.
    - Intended to come straight from SQL via a repository/service.
    """

    id: ProjectId
    name: str
    root_path: Path
    created_at: datetime
    updated_at: datetime
    media_count: int
    annotation_count: int
    active_datasource_id: Optional[int] = None
    active_model_variant_id: Optional[int] = None

    def display_name(self) -> str:
        return self.name or self.root_path.name
