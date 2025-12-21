from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QMessageBox, QMainWindow

from datalens.domain.system.settings import AppSettings
from datalens.core.logging import get_logger
from datalens.services.project_close_policy import default_project_close_policy
from datalens.services.settings_store import SettingsStore

from .app_context import try_get_app_context


log = get_logger(__name__)


def _prompt_project_close_failure(
    parent: QMainWindow,
    *,
    exc: Exception,
    force_label: str,
    switching_projects: bool,
) -> str:
    """
    Prompt the user when a safe project close fails.

    Returns:
        `"retry" | "cancel" | "force"`
    """
    from datalens.services.project_service import ProjectCloseError

    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Critical)
    dialog.setWindowTitle("Failed to Close Project")

    phase = getattr(exc, "phase", None) if isinstance(exc, ProjectCloseError) else None
    if phase:
        dialog.setText(f"{exc}\n\nPhase: {phase}")
    else:
        dialog.setText(str(exc))

    phase_msg = ""
    if phase == "plugin_flush_hooks":
        phase_msg = "A plugin reported a flush/shutdown error during close."
    elif phase == "db_flush":
        phase_msg = "The project database did not flush successfully."
    elif phase == "io_flush":
        phase_msg = "Background file I/O did not flush successfully."

    if switching_projects:
        base = (
            "Retry to attempt a safe close again, cancel to keep the current project open, "
            "or force close and open the new project (may lose unsaved work)."
        )
    else:
        base = (
            "Retry to attempt a safe close again, cancel to keep the project open, "
            "or force close (may lose unsaved work)."
        )
    dialog.setInformativeText(f"{phase_msg}\n\n{base}".strip())

    retry = dialog.addButton("Retry", QMessageBox.AcceptRole)
    dialog.addButton("Cancel", QMessageBox.RejectRole)
    force_btn = dialog.addButton(force_label, QMessageBox.DestructiveRole)
    dialog.setDefaultButton(retry)
    dialog.exec()

    clicked = dialog.clickedButton()
    if clicked is retry:
        return "retry"
    if clicked is force_btn:
        return "force"
    return "cancel"


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
        self._close_policy = default_project_close_policy()

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
                close_timeout_seconds=float(self._close_policy.safe_close_timeout_seconds),
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
                action = _prompt_project_close_failure(
                    self._window,
                    exc=exc,
                    force_label="Force Close + Open",
                    switching_projects=True,
                )
                if action == "retry":
                    self.open_project(project_root)
                    return
                if action == "force":
                    def force_task(ctx: LoaderContext) -> object:
                        ctx.log("Force closing current project (best-effort)...")
                        close_project(app_ctx, reason="force")
                        ctx.log("Opening project...")
                        open_project_with_plugins(
                            app_ctx=app_ctx,
                            project_root=project_root,
                            plugin_host=getattr(app_ctx, "plugin_host", None),
                            close_timeout_seconds=float(self._close_policy.safe_close_timeout_seconds),
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

    def startup_load(
        self,
        *,
        enabled_plugin_ids: set[str] | None,
        load_last_project: bool,
        last_project_root: object | None,
    ) -> None:
        """
        Apply the initial startup selection in a single, consistent loader flow.

        This is used by `datalens.app` after showing the main window.
        It consolidates the "enable selected plugins" + "open last project"
        behavior so it matches the same UX/policy used by File->Open/Switch.
        """
        from datalens.infra.background.loader_context import LoaderContext
        from datalens.infra.background.loader_runner import LoaderStage, run_with_loader_sequence
        from datalens.services.project_service import open_project_with_plugins

        app_ctx = try_get_app_context()
        if app_ctx is None:
            return

        plugin_ids = set(enabled_plugin_ids or set())
        should_open_project = bool(load_last_project and last_project_root)
        if not plugin_ids and not should_open_project:
            return

        stages: list[LoaderStage] = []

        if plugin_ids:
            def enable_plugins_task(ctx: LoaderContext) -> object:
                host = getattr(app_ctx, "plugin_host", None)
                if host is None:
                    return None
                try:
                    preview = ", ".join(sorted(str(pid) for pid in plugin_ids))
                    ctx.log(f"Enabling {len(plugin_ids)} plugin(s): {preview}")
                except Exception:
                    ctx.log("Enabling selected plugins...")
                host.set_enabled(app_ctx=app_ctx, plugin_ids=plugin_ids)
                ctx.set_progress(1.0)
                return None

            stages.append(LoaderStage(name="Enabling selected plugins...", task=enable_plugins_task, weight=1.0))

        if should_open_project:
            def open_project_task(ctx: LoaderContext) -> object:
                ctx.log("Opening project...")
                project = open_project_with_plugins(
                    app_ctx=app_ctx,
                    project_root=last_project_root,
                    plugin_host=getattr(app_ctx, "plugin_host", None),
                    close_timeout_seconds=float(self._close_policy.safe_close_timeout_seconds),
                    plugin_migrate_timeout_seconds=60.0,
                    await_plugin_opened=False,
                    progress=ctx.log,
                )
                try:
                    project_root = getattr(project, "project_root", None)
                    if project_root is not None:
                        root = Path(project_root)

                        def update_recents(settings: AppSettings) -> AppSettings:
                            recents: list[Path] = [root]
                            for p in settings.recent_projects:
                                if p == root:
                                    continue
                                recents.append(p)
                                if len(recents) >= 12:
                                    break
                            return replace(settings, last_project_root=root, recent_projects=tuple(recents))

                        SettingsStore().update(update_recents)
                except Exception:
                    log.debug("Failed to update recent projects after open (best-effort)", exc_info=True)
                ctx.set_progress(1.0)
                return project

            stages.append(LoaderStage(name="Opening project...", task=open_project_task, weight=3.0))

        def on_sequence_done(results: list[object]) -> None:
            # Once enable stage completes, re-dispatch focus so the visible
            # workspace receives `on_focus`.
            try:
                on_plugins_enabled = getattr(self._window, "on_plugins_enabled", None)
                if callable(on_plugins_enabled):
                    on_plugins_enabled()
            except Exception:
                log.debug("Failed to dispatch plugin focus after enabling (best-effort)", exc_info=True)

            # If a project was opened, it will be the last non-None stage result.
            project: object | None = None
            for item in reversed(results):
                if item is not None:
                    project = item
                    break
            if project is None:
                try:
                    self._on_project_changed()
                except Exception:
                    log.warning("Failed to update main window after loader sequence (best-effort)", exc_info=True)
                return

            try:
                self._on_project_changed()
            except Exception:
                log.warning("Failed to update main window on project open (best-effort)", exc_info=True)
            try:
                reload_recents = getattr(self._window, "reload_recent_projects_from_settings", None)
                if callable(reload_recents):
                    reload_recents()
            except Exception:
                log.debug("Failed to reload recent projects after open (best-effort)", exc_info=True)

        def on_sequence_error(exc: Exception) -> None:
            log.error("Startup load failed: %s", exc, extra={"operation": "startup_load", "phase": "error"})
            try:
                QMessageBox.critical(self._window, "Startup", str(exc))
            except Exception:
                log.debug("Failed to show startup error dialog (best-effort)", exc_info=True)
            try:
                self._on_project_changed()
            except Exception:
                log.warning("Failed to update main window after startup error (best-effort)", exc_info=True)

        run_with_loader_sequence(
            parent=self._window,
            title="Loading...",
            stages=stages,
            on_result=on_sequence_done,
            on_error=on_sequence_error,
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

    def restart_app_interactive(self) -> None:
        """
        Restart DataLens in a fresh process (File -> Restart).

        This tries to behave like "closing the app and running it again from the terminal":
        - if a project is open, run the same safe close/flush UX (retry/cancel/force)
        - if close succeeds, spawn a new `python -m datalens.app` process
        - quit the current app instance
        """
        if self._is_close_in_progress():
            return

        app_ctx = try_get_app_context()
        if app_ctx is None:
            QMessageBox.critical(self._window, "Restart", "Application context is not available.")
            return

        program = sys.executable
        args: list[str] = ["-m", "datalens.app", *list(sys.argv[1:])]

        # If a project is open, ensure we can reload it after restart.
        has_project = bool(getattr(app_ctx, "active_project", None) is not None)
        if has_project:
            try:
                project_root = getattr(app_ctx, "project_root", None)
                if project_root is not None:
                    store = SettingsStore()
                    store.update(lambda s: replace(s, last_project_root=Path(project_root)))
            except Exception:
                log.debug("Failed to persist last project root before restart (best-effort)", exc_info=True)
            # Force a "terminal-like" restart that returns the user to the same project
            # without needing to click through the welcome flow.
            if "--skip-welcome" not in args:
                args.append("--skip-welcome")
            if "--load-last-project" not in args:
                args.append("--load-last-project")

        spawned = {"done": False}

        def spawn_new_process() -> None:
            if spawned["done"]:
                return
            spawned["done"] = True
            try:
                ok, _pid = QProcess.startDetached(program, args, os.getcwd())
            except Exception:
                ok = False
            if not ok:
                QMessageBox.critical(
                    self._window,
                    "Restart Failed",
                    f"Failed to start a new DataLens process.\n\nCommand:\n{program} {' '.join(args)}",
                )
                return
            app = QApplication.instance()
            if app is not None:
                app.quit()

        if not has_project:
            spawn_new_process()
            return

        self._set_close_in_progress(True)
        from datalens.services.project_service import close_project, close_project_blocking

        self._run_project_close_loader(
            app_ctx=app_ctx,
            close_project=close_project,
            close_project_blocking=close_project_blocking,
            force_close_label="Force Close + Restart",
            on_closed=lambda: (self._set_close_in_progress(False), spawn_new_process(), QTimer.singleShot(0, self._window.close)),
            on_cancel=lambda: self._set_close_in_progress(False),
            close_window_after=True,
            reason="restart",
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
            log.debug("Failed to flush UI state before project close (best-effort)", exc_info=True)

        def run_close(*, force: bool) -> None:
            def task(ctx: LoaderContext) -> object:
                if force:
                    ctx.log("Force closing project (best-effort)...")
                    close_project(app_ctx, reason="force")
                else:
                    ctx.log("Flushing project...")
                    close_project_blocking(
                        app_ctx,
                        timeout_seconds=float(self._close_policy.safe_close_timeout_seconds),
                        reason=reason,
                    )

                if close_window_after:
                    ctx.log("Stopping background IO...")
                    try:
                        app_ctx.io.close(
                            flush=False,
                            timeout_seconds=float(self._close_policy.io_shutdown_timeout_seconds),
                        )
                    except Exception:
                        log.warning("Failed to close IoWriter during project close (best-effort)", exc_info=True)

                ctx.log("Done.")
                return object()

            def on_done(_: object) -> None:
                try:
                    on_closed()
                except Exception:
                    log.debug("Project close 'on_closed' callback failed (best-effort)", exc_info=True)

            def on_error(exc: Exception) -> None:
                action = _prompt_project_close_failure(
                    self._window,
                    exc=exc,
                    force_label=force_close_label,
                    switching_projects=False,
                )
                if action == "retry":
                    run_close(force=False)
                    return
                if action == "force":
                    run_close(force=True)
                    return
                try:
                    on_cancel()
                except Exception:
                    log.debug("Project close 'on_cancel' callback failed (best-effort)", exc_info=True)

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
