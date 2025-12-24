from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import Callable

from datalens.core.logging import get_logger
from datalens.domain.system.workspace_state import WorkspaceStateSnapshot
from datalens.domain.system.system_info import SystemInfoSnapshot

log = get_logger(__name__)


WorkspaceStateListener = Callable[[WorkspaceStateSnapshot], None]


class WorkspaceStateService:
    """
    Core-owned, queryable "current workspace state".

    This is intentionally small and is meant to be queried by late-loaded
    plugins to sync to the current app state.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = WorkspaceStateSnapshot()
        self._version = 0
        self._listeners: list[WorkspaceStateListener] = []

    def version(self) -> int:
        with self._lock:
            return self._version

    def snapshot(self) -> WorkspaceStateSnapshot:
        with self._lock:
            return self._snapshot

    def set_project_root(self, project_root: Path | None) -> None:
        self._update(lambda s: replace(s, project_root=project_root))

    def set_active_workspace_id(self, workspace_id: str | None) -> None:
        self._update(lambda s: replace(s, active_workspace_id=workspace_id))

    def set_active_item_id(self, item_id: str | None) -> None:
        self._update(lambda s: replace(s, active_item_id=item_id))

    def set_system_info(self, system_info: SystemInfoSnapshot | None) -> None:
        self._update(lambda s: replace(s, system_info=system_info))

    def subscribe(self, listener: WorkspaceStateListener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._listeners.remove(listener)
                except ValueError:
                    pass

        return unsubscribe

    def _update(self, mutator: Callable[[WorkspaceStateSnapshot], WorkspaceStateSnapshot]) -> None:
        listeners: list[WorkspaceStateListener] = []
        snapshot: WorkspaceStateSnapshot | None = None
        with self._lock:
            updated = mutator(self._snapshot)
            if updated == self._snapshot:
                return
            self._snapshot = updated
            self._version += 1
            snapshot = updated
            listeners = list(self._listeners)

        # Call listeners outside the lock. Listener execution is synchronous and
        # runs on the caller's thread; listeners must not block.
        for fn in listeners:
            try:
                fn(snapshot)  # type: ignore[arg-type]
            except Exception:
                log.debug("WorkspaceState listener failed (best-effort)", exc_info=True)
