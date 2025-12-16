from __future__ import annotations

from typing import Any

from PySide6.QtCore import QByteArray
from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QWidget

from datalens.domain.plugin import PluginId
from datalens.infra.persistence_queue import PersistenceQueue
from datalens.ui.menus.menubar import DatalensMenuBar


class MainWindow(QMainWindow):
    """Minimal main application window placeholder."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DataLens")
        self.resize(1200, 800)
        self._close_in_progress = False

        menubar = DatalensMenuBar(self)
        menubar.newProjectRequested.connect(self._on_new_project_requested)
        self.setMenuBar(menubar)

        label = QLabel("Main Window (placeholder)")
        label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(label)

        self._ui_state_plugin_id = PluginId("core.ui")
        self._ui_state_key = "main_window_state"
        self._ui_state_last_snapshot: dict[str, object] | None = None
        self._ui_state_queue = PersistenceQueue(
            parent=self,
            name="MainWindowUiState",
            debounce_ms=250,
            max_pending_jobs=1,
            use_worker=False,  # save stage enqueues onto ProjectDb (already background)
            merge_func=self._merge_ui_state_changes,
            snapshot_func=self._snapshot_ui_state,
            save_func=self._save_ui_state,
        )
        self._restore_ui_state_from_project_db()

    def _on_new_project_requested(self) -> None:
        QMessageBox.information(self, "New Project", "New Project is not implemented yet.")

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._ui_state_queue.enqueue(keys={"move"})

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._ui_state_queue.enqueue(keys={"resize"})

    def _merge_ui_state_changes(self, keys: set[object], full_refresh: bool, payloads: list[Any]) -> bool:
        # TODO(v2): This merge callback is intentionally minimal for window UI-state persistence.
        # Current behavior: treat any UI event as "changed" and let `_snapshot_ui_state` dedupe.
        # Future: if we persist additional per-project UI state (tabs, panes, etc.), implement
        # a real in-memory merge/cache update here to avoid unnecessary snapshots.
        return bool(keys) or full_refresh or bool(payloads)

    def _snapshot_ui_state(self) -> dict[str, object] | None:
        app_ctx = self._get_app_context()
        if app_ctx is None or getattr(app_ctx, "active_project", None) is None:
            return None

        snapshot = {
            "geometry_b64": bytes(self.saveGeometry().toBase64()).decode("ascii"),
            "state_b64": bytes(self.saveState().toBase64()).decode("ascii"),
        }
        if snapshot == self._ui_state_last_snapshot:
            return None
        self._ui_state_last_snapshot = snapshot
        return snapshot

    def _save_ui_state(self, payload: dict[str, object]) -> bool:
        app_ctx = self._get_app_context()
        project = getattr(app_ctx, "active_project", None) if app_ctx is not None else None
        if project is None:
            return False
        project.project_db.kv_set(self._ui_state_plugin_id, self._ui_state_key, payload)
        return True

    def _restore_ui_state_from_project_db(self) -> None:
        app_ctx = self._get_app_context()
        project = getattr(app_ctx, "active_project", None) if app_ctx is not None else None
        if project is None:
            return

        future = project.project_db.kv_get(self._ui_state_plugin_id, self._ui_state_key)

        def apply(value: object | None) -> None:
            if not isinstance(value, dict):
                return
            geometry_b64 = value.get("geometry_b64")
            if isinstance(geometry_b64, str) and geometry_b64:
                try:
                    self.restoreGeometry(QByteArray.fromBase64(geometry_b64.encode("ascii")))
                except Exception:
                    pass

            state_b64 = value.get("state_b64")
            if isinstance(state_b64, str) and state_b64:
                try:
                    self.restoreState(QByteArray.fromBase64(state_b64.encode("ascii")))
                except Exception:
                    pass

        def on_done(fut) -> None:
            try:
                value = fut.result()
            except Exception:
                return
            QTimer.singleShot(0, lambda: apply(value))

        future.add_done_callback(on_done)

    def _get_app_context(self) -> object | None:
        try:
            app = QApplication.instance()
            return getattr(app, "app_context", None) if app is not None else None
        except Exception:
            return None

    def closeEvent(self, event) -> None:
        """
        Ensure project persistence flushes run off the UI thread on app close.

        This uses the shared loader infrastructure so the UI remains responsive
        while background flush/close work runs.
        """
        if self._close_in_progress:
            super().closeEvent(event)
            return

        # Ensure the last UI-state snapshot is submitted before the DB flush.
        try:
            self._ui_state_queue.flush()
        except Exception:
            pass

        try:
            app = QApplication.instance()
            app_ctx = getattr(app, "app_context", None) if app is not None else None
        except Exception:
            app_ctx = None

        # No active project: nothing to flush.
        if app_ctx is None or getattr(app_ctx, "active_project", None) is None:
            super().closeEvent(event)
            return

        event.ignore()
        self._close_in_progress = True

        from datalens.infra.background.loader_context import LoaderContext
        from datalens.infra.background.loader_runner import run_with_loader
        from datalens.services.project_service import close_project, close_project_blocking

        def run_close(*, force: bool) -> None:
            def task(ctx: LoaderContext) -> object:
                if force:
                    ctx.log("Force closing project (best-effort)...")
                    close_project(app_ctx)
                else:
                    ctx.log("Flushing project...")
                    close_project_blocking(app_ctx, timeout_seconds=30.0)

                ctx.log("Stopping background IO...")
                try:
                    app_ctx.io.close(flush=False, timeout_seconds=5.0)
                except Exception:
                    pass
                ctx.log("Done.")
                return object()

            def on_done(_: object) -> None:
                self._close_in_progress = False
                QTimer.singleShot(0, self.close)

            def on_error(exc: Exception) -> None:
                self._close_in_progress = False

                dialog = QMessageBox(self)
                dialog.setIcon(QMessageBox.Critical)
                dialog.setWindowTitle("Failed to Close Project")
                dialog.setText(str(exc))
                dialog.setInformativeText(
                    "Retry to attempt a safe close again, cancel to keep the project open, "
                    "or force close (may lose unsaved work)."
                )
                retry = dialog.addButton("Retry", QMessageBox.AcceptRole)
                cancel = dialog.addButton("Cancel", QMessageBox.RejectRole)
                force_btn = dialog.addButton("Force Close", QMessageBox.DestructiveRole)
                dialog.setDefaultButton(retry)
                dialog.exec()

                clicked = dialog.clickedButton()
                if clicked is retry:
                    self._close_in_progress = True
                    run_close(force=False)
                    return
                if clicked is force_btn:
                    self._close_in_progress = True
                    run_close(force=True)
                    return
                # Cancel: keep the window open.

            run_with_loader(
                parent=self,
                title="Closing Project...",
                task=task,
                on_result=on_done,
                on_error=on_error,
                dialog_options={"spinner_size": 80, "title_point_size": 18, "subtitle_point_size": 12},
            )

        run_close(force=False)
