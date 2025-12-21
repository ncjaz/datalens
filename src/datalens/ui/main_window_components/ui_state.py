from __future__ import annotations

from typing import Any

from PySide6.QtCore import QByteArray, QTimer
from PySide6.QtWidgets import QMainWindow

from datalens.domain.plugin import PluginId
from datalens.infra.persistence_queue import PersistenceQueue

from .app_context import try_get_app_context


class MainWindowUiStateController:
    """
    Persist/restore per-project MainWindow UI state (geometry + state).

    This uses `ProjectDb.kv_*` via a debounce queue so window move/resize doesn't
    block the UI thread and doesn't spam the DB.
    """

    def __init__(
        self,
        window: QMainWindow,
        *,
        plugin_id: PluginId = PluginId("core.ui"),
        key: str = "main_window_state",
    ) -> None:
        self._window = window
        self._plugin_id = plugin_id
        self._key = key
        self._last_snapshot: dict[str, object] | None = None

        self._queue = PersistenceQueue(
            parent=window,
            name="MainWindowUiState",
            debounce_ms=250,
            max_pending_jobs=1,
            use_worker=False,  # save stage enqueues onto ProjectDb (already background)
            merge_func=self._merge_ui_state_changes,
            snapshot_func=self._snapshot_ui_state,
            save_func=self._save_ui_state,
        )

        self.restore_from_project_db()

    def enqueue_move(self) -> None:
        self._queue.enqueue(keys={"move"})

    def enqueue_resize(self) -> None:
        self._queue.enqueue(keys={"resize"})

    def flush(self) -> None:
        self._queue.flush()

    def on_project_changed(self) -> None:
        self._last_snapshot = None
        self.restore_from_project_db()

    def restore_from_project_db(self) -> None:
        app_ctx = try_get_app_context()
        project = getattr(app_ctx, "active_project", None) if app_ctx is not None else None
        if project is None:
            return

        future = project.project_db.kv_get(self._plugin_id, self._key)

        def apply(value: object | None) -> None:
            if not isinstance(value, dict):
                return
            geometry_b64 = value.get("geometry_b64")
            if isinstance(geometry_b64, str) and geometry_b64:
                try:
                    self._window.restoreGeometry(QByteArray.fromBase64(geometry_b64.encode("ascii")))
                except Exception:
                    pass

            state_b64 = value.get("state_b64")
            if isinstance(state_b64, str) and state_b64:
                try:
                    self._window.restoreState(QByteArray.fromBase64(state_b64.encode("ascii")))
                except Exception:
                    pass

        def on_done(fut) -> None:
            try:
                value = fut.result()
            except Exception:
                return
            QTimer.singleShot(0, lambda: apply(value))

        future.add_done_callback(on_done)

    def _merge_ui_state_changes(self, keys: set[object], full_refresh: bool, payloads: list[Any]) -> bool:
        # TODO(v2): This merge callback is intentionally minimal for window UI-state persistence.
        # Current behavior: treat any UI event as "changed" and let `_snapshot_ui_state` dedupe.
        # Future: if we persist additional per-project UI state (tabs, panes, etc.), implement
        # a real in-memory merge/cache update here to avoid unnecessary snapshots.
        return bool(keys) or full_refresh or bool(payloads)

    def _snapshot_ui_state(self) -> dict[str, object] | None:
        app_ctx = try_get_app_context()
        if app_ctx is None or getattr(app_ctx, "active_project", None) is None:
            return None

        snapshot = {
            "geometry_b64": bytes(self._window.saveGeometry().toBase64()).decode("ascii"),
            "state_b64": bytes(self._window.saveState().toBase64()).decode("ascii"),
        }
        if snapshot == self._last_snapshot:
            return None
        self._last_snapshot = snapshot
        return snapshot

    def _save_ui_state(self, payload: dict[str, object]) -> bool:
        app_ctx = try_get_app_context()
        project = getattr(app_ctx, "active_project", None) if app_ctx is not None else None
        if project is None:
            return False
        project.project_db.kv_set(self._plugin_id, self._key, payload)
        return True


__all__ = ["MainWindowUiStateController"]

