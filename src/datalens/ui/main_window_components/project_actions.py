from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox, QMainWindow

from datalens.domain.system.settings import AppSettings
from datalens.services.settings_store import SettingsStore

from .app_context import try_get_app_context


class ProjectActionsController:
    """
    Project open/close UX flows for MainWindow.

    This intentionally lives in UI (not services) because it orchestrates:
    - loader dialogs
    - message boxes / retry UI
    - menu/MRU updates
    """

    def __init__(
        self,
        window: QMainWindow,
        *,
        get_recent_projects,
        set_recent_projects,
        on_project_changed,
        flush_ui_state,
        set_close_in_progress,
        is_close_in_progress,
    ) -> None:
        self._window = window
        self._get_recent_projects = get_recent_projects
        self._set_recent_projects = set_recent_projects
        self._on_project_changed = on_project_changed
        self._flush_ui_state = flush_ui_state
        self._set_close_in_progress = set_close_in_progress
        self._is_close_in_progress = is_close_in_progress

    def open_project(self, project_root: Path) -> None:
        from datalens.infra.background.loader_context import LoaderContext
        from datalens.infra.background.loader_runner import run_with_loader
        from datalens.services.project_service import ProjectCloseError, close_project, open_project_with_plugins

        app_ctx = try_get_app_context()
        if app_ctx is None:
            QMessageBox.critical(self._window, "Open Project", "Application context is not available.")
            return

        def update_recents(settings: AppSettings) -> AppSettings:
            recents: list[Path] = [project_root]
            for p in settings.recent_projects:
                if p == project_root:
                    continue
                recents.append(p)
                if len(recents) >= 12:
                    break
            return replace(settings, last_project_root=project_root, recent_projects=tuple(recents))

        def task(ctx: LoaderContext) -> object:
            ctx.log("Opening project...")
            open_project_with_plugins(
                app_ctx=app_ctx,
                project_root=project_root,
                plugin_host=getattr(app_ctx, "plugin_host", None),
                plugin_migrate_timeout_seconds=60.0,
                await_plugin_opened=False,
                progress=ctx.log,
            )
            try:
                store = SettingsStore()
                updated = store.update(update_recents)
                return tuple(updated.recent_projects)
            except Exception:
                return None

        def on_done(result: object) -> None:
            if isinstance(result, tuple) and all(isinstance(p, Path) for p in result):
                self._set_recent_projects(list(result))
            self._on_project_changed()

        def on_error(exc: Exception) -> None:
            if isinstance(exc, ProjectCloseError):
                dialog = QMessageBox(self._window)
                dialog.setIcon(QMessageBox.Critical)
                dialog.setWindowTitle("Failed to Close Project")
                dialog.setText(str(exc))
                dialog.setInformativeText(
                    "Retry to attempt a safe close again, cancel to keep the current project open, "
                    "or force close and open the new project (may lose unsaved work)."
                )
                retry = dialog.addButton("Retry", QMessageBox.AcceptRole)
                dialog.addButton("Cancel", QMessageBox.RejectRole)
                force_btn = dialog.addButton("Force Close + Open", QMessageBox.DestructiveRole)
                dialog.setDefaultButton(retry)
                dialog.exec()

                clicked = dialog.clickedButton()
                if clicked is retry:
                    self.open_project(project_root)
                    return
                if clicked is force_btn:
                    def force_task(ctx: LoaderContext) -> object:
                        ctx.log("Force closing current project (best-effort)...")
                        close_project(app_ctx, reason="force")
                        ctx.log("Opening project...")
                        open_project_with_plugins(
                            app_ctx=app_ctx,
                            project_root=project_root,
                            plugin_host=getattr(app_ctx, "plugin_host", None),
                            plugin_migrate_timeout_seconds=60.0,
                            await_plugin_opened=False,
                            progress=ctx.log,
                        )
                        try:
                            store = SettingsStore()
                            updated = store.update(update_recents)
                            return tuple(updated.recent_projects)
                        except Exception:
                            return None

                    run_with_loader(
                        parent=self._window,
                        title="Opening Project...",
                        task=force_task,
                        on_result=on_done,
                        on_error=lambda e: QMessageBox.critical(self._window, "Open Project", str(e)),
                        dialog_options={"spinner_size": 80, "title_point_size": 18, "subtitle_point_size": 12},
                    )
                    return
                return

            QMessageBox.critical(self._window, "Open Project", str(exc))
            self._on_project_changed()

        run_with_loader(
            parent=self._window,
            title="Opening Project...",
            task=task,
            on_result=on_done,
            on_error=on_error,
            dialog_options={"spinner_size": 80, "title_point_size": 18, "subtitle_point_size": 12},
        )

    def close_project_interactive(self) -> None:
        from datalens.services.project_service import close_project, close_project_blocking

        app_ctx = try_get_app_context()
        if app_ctx is None or getattr(app_ctx, "active_project", None) is None:
            return

        self._run_project_close_loader(
            app_ctx=app_ctx,
            close_project=close_project,
            close_project_blocking=close_project_blocking,
            force_close_label="Force Close",
            on_closed=lambda: self._on_project_changed(),
            on_cancel=lambda: None,
            close_window_after=False,
            reason="user",
        )

    def handle_close_event(self, event) -> bool:
        """
        Return True if the close event was handled (ignored) for async flush.
        """
        if self._is_close_in_progress():
            event.ignore()
            return True

        app_ctx = try_get_app_context()
        if app_ctx is None or getattr(app_ctx, "active_project", None) is None:
            return False

        event.ignore()
        self._set_close_in_progress(True)

        from datalens.services.project_service import close_project, close_project_blocking

        self._run_project_close_loader(
            app_ctx=app_ctx,
            close_project=close_project,
            close_project_blocking=close_project_blocking,
            force_close_label="Force Close",
            on_closed=lambda: (self._set_close_in_progress(False), QTimer.singleShot(0, self._window.close)),
            on_cancel=lambda: self._set_close_in_progress(False),
            close_window_after=True,
            reason="shutdown",
        )
        return True

    def _run_project_close_loader(
        self,
        *,
        app_ctx: object,
        close_project,
        close_project_blocking,
        force_close_label: str,
        on_closed,
        on_cancel,
        close_window_after: bool,
        reason: str,
    ) -> None:
        from datalens.infra.background.loader_context import LoaderContext
        from datalens.infra.background.loader_runner import run_with_loader

        try:
            self._flush_ui_state()
        except Exception:
            pass

        def run_close(*, force: bool) -> None:
            def task(ctx: LoaderContext) -> object:
                if force:
                    ctx.log("Force closing project (best-effort)...")
                    close_project(app_ctx, reason="force")
                else:
                    ctx.log("Flushing project...")
                    close_project_blocking(app_ctx, timeout_seconds=30.0, reason=reason)

                if close_window_after:
                    ctx.log("Stopping background IO...")
                    try:
                        app_ctx.io.close(flush=False, timeout_seconds=5.0)
                    except Exception:
                        pass

                ctx.log("Done.")
                return object()

            def on_done(_: object) -> None:
                try:
                    on_closed()
                except Exception:
                    pass

            def on_error(exc: Exception) -> None:
                dialog = QMessageBox(self._window)
                dialog.setIcon(QMessageBox.Critical)
                dialog.setWindowTitle("Failed to Close Project")
                dialog.setText(str(exc))
                dialog.setInformativeText(
                    "Retry to attempt a safe close again, cancel to keep the project open, "
                    "or force close (may lose unsaved work)."
                )
                retry = dialog.addButton("Retry", QMessageBox.AcceptRole)
                dialog.addButton("Cancel", QMessageBox.RejectRole)
                force_btn = dialog.addButton(force_close_label, QMessageBox.DestructiveRole)
                dialog.setDefaultButton(retry)
                dialog.exec()

                clicked = dialog.clickedButton()
                if clicked is retry:
                    run_close(force=False)
                    return
                if clicked is force_btn:
                    run_close(force=True)
                    return
                try:
                    on_cancel()
                except Exception:
                    pass

            run_with_loader(
                parent=self._window,
                title="Closing Project...",
                task=task,
                on_result=on_done,
                on_error=on_error,
                dialog_options={"spinner_size": 80, "title_point_size": 18, "subtitle_point_size": 12},
            )

        run_close(force=False)


__all__ = ["ProjectActionsController"]
