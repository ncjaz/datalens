from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceStateSnapshot:
    """
    Snapshot of a small set of core-owned "current state" values.

    This is intentionally narrow. High-rate payloads and large objects do not
    belong here.
    """

    project_root: Path | None = None
    active_workspace_id: str | None = None
    active_item_id: str | None = None


__all__ = ["WorkspaceStateSnapshot"]
