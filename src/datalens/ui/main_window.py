from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray
from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.domain.plugin import PluginKind
from datalens.infra.persistence_queue import PersistenceQueue
from datalens.services.plugins.registry import PluginRecord
from datalens.ui.menus.factory import create_menubar
from datalens.ui.widgets.navigation.plugin_sidebar import PluginNavItem, PluginSidebar, nav_label_for


log = get_logger(__name__)


class MainWindow(QMainWindow):
    """Minimal main application window placeholder."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        recent_projects: list[Path] | None = None,
        plugins: list[PluginRecord] | None = None,
        enabled_plugin_ids: set[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("DataLens")
        self.resize(1200, 800)
        self._close_in_progress = False
        self._recent_projects: list[Path] = list(recent_projects or [])
        self._plugins: list[PluginRecord] = list(plugins or [])
        self._enabled_plugin_ids: set[PluginId] | None = (
            {PluginId(pid) for pid in enabled_plugin_ids} if enabled_plugin_ids is not None else None
        )
        self._active_workspace_id: PluginId | None = None
        self._last_project_root: Path | None = None

        menubar = create_menubar(self)
        self.setMenuBar(menubar)
        self._menubar = menubar
        self._menubar.set_recent_projects(self._recent_projects)

        self._sidebar = PluginSidebar(self)
        self._sidebar.pluginSelected.connect(self._on_workspace_selected)

        self._label = QLabel("", self)
        self._label.setAlignment(Qt.AlignCenter)
        self._workspace_stack = QStackedWidget(self)
        self._workspace_stack.addWidget(self._label)
        self._workspace_widgets: dict[PluginId, QWidget] = {}

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar, 0)

        right = QWidget(central)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._workspace_stack, 1)
        layout.addWidget(right, 1)
        self.setCentralWidget(central)

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
        self._refresh_workspace_nav()
        self._refresh_project_state()

    def on_plugins_enabled(self) -> None:
        """
        Notify the UI that plugin enable/disable has completed.

        The main window is shown before plugins are enabled (loader stages run
        after `show()`), so the initial workspace selection may have been
        published before the runtime existed. Re-dispatch focus so the visible
        workspace receives `on_focus`.
        """
        if self._active_workspace_id is None:
            return
        self._show_workspace_widget(self._active_workspace_id)
        self._publish_active_workspace(self._active_workspace_id)
        self._update_placeholder_text()

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
                    log.debug("Failed to restore main window geometry (best-effort)", exc_info=True)

            state_b64 = value.get("state_b64")
            if isinstance(state_b64, str) and state_b64:
                try:
                    self.restoreState(QByteArray.fromBase64(state_b64.encode("ascii")))
                except Exception:
                    log.debug("Failed to restore main window state (best-effort)", exc_info=True)

        def on_done(fut) -> None:
            try:
                value = fut.result()
            except Exception:
                return
            QTimer.singleShot(0, lambda: apply(value))

        future.add_done_callback(on_done)

    def _best_open_start_dir(self) -> str:
        app_ctx = self._get_app_context()
        project = getattr(app_ctx, "active_project", None) if app_ctx is not None else None
        if project is not None:
            return str(project.project_root)
        if self._recent_projects:
            return str(self._recent_projects[0])
        return ""

    def _refresh_project_state(self) -> None:
        app_ctx = self._get_app_context()
        project = getattr(app_ctx, "active_project", None) if app_ctx is not None else None
        if project is None:
            self._last_project_root = None
            if hasattr(self, "_menubar"):
                self._menubar.set_has_project(False)
            self._update_placeholder_text()
            return
        self._last_project_root = getattr(project, "project_root", None)
        if hasattr(self, "_menubar"):
            self._menubar.set_has_project(True)
        self._update_placeholder_text()

    def _update_placeholder_text(self) -> None:
        if self._active_workspace_id is not None:
            ws_line = f"Workspace: {self._active_workspace_id}"
        else:
            ws_line = "Workspace: (none)"

        if self._last_project_root is not None:
            project_line = f"Project: {self._last_project_root}"
        else:
            project_line = "No project open."

        self._label.setText(f"{ws_line}\n\n{project_line}")

    def _show_workspace_widget(self, workspace_id: PluginId | None) -> None:
        """
        Show the selected workspace's UI widget if provided by the plugin.

        Workspace widgets must be created on the Qt thread. Plugin runtimes are
        enabled off the UI thread; this method is safe to call multiple times
        (it caches created widgets).
        """
        if workspace_id is None:
            self._workspace_stack.setCurrentWidget(self._label)
            return

        widget = self._workspace_widgets.get(workspace_id)
        if widget is not None:
            self._workspace_stack.setCurrentWidget(widget)
            return

        app_ctx = self._get_app_context()
        host = getattr(app_ctx, "plugin_host", None) if app_ctx is not None else None
        if host is None:
            self._workspace_stack.setCurrentWidget(self._label)
            return

        try:
            plugin = host.get_enabled_plugin(workspace_id)
            record = host.get_enabled_record(workspace_id)
        except Exception:
            plugin = None
            record = None

        if plugin is None or record is None:
            self._workspace_stack.setCurrentWidget(self._label)
            return

        create_fn = getattr(plugin, "create_workspace_widget", None)
        if not callable(create_fn):
            self._workspace_stack.setCurrentWidget(self._label)
            return

        try:
            from datalens.services.plugins.runtime.contracts import PluginAppContext

            ctx = PluginAppContext(app=app_ctx, plugin=record.definition)  # type: ignore[arg-type]
            created = create_fn(self._workspace_stack, ctx)
        except Exception:
            log.warning("Failed to create workspace widget (best-effort)", exc_info=True)
            self._workspace_stack.setCurrentWidget(self._label)
            return

        if not isinstance(created, QWidget):
            self._workspace_stack.setCurrentWidget(self._label)
            return

        self._workspace_widgets[workspace_id] = created
        self._workspace_stack.addWidget(created)
        self._workspace_stack.setCurrentWidget(created)

    def _refresh_workspace_nav(self) -> None:
        items: list[PluginNavItem] = []
        for record in self._plugins:
            definition = record.definition
            if self._enabled_plugin_ids is not None and definition.id not in self._enabled_plugin_ids:
                continue
            if not any(f.kind == PluginKind.WORKSPACE for f in definition.features):
                continue

            icon_path: Path | None = None
            nav_icon = definition.nav_icon
            if isinstance(nav_icon, str):
                nav_icon = nav_icon.strip()
                if nav_icon:
                    candidate = Path(nav_icon)
                    if not candidate.is_absolute():
                        icon_path = record.location.root_dir / candidate

            items.append(
                PluginNavItem(
                    plugin_id=definition.id,
                    name=definition.name,
                    nav_label=nav_label_for(definition),
                    icon_path=icon_path,
                )
            )

        items.sort(key=lambda i: i.name.lower())
        self._sidebar.set_items(items)

        preferred: PluginId | None = None
        app_ctx = self._get_app_context()
        ws = getattr(app_ctx, "workspace_state", None) if app_ctx is not None else None
        if ws is not None:
            try:
                snap = ws.snapshot()
                if getattr(snap, "active_workspace_id", None):
                    preferred = PluginId(str(snap.active_workspace_id))
            except Exception:
                log.debug("Failed to read workspace state (best-effort)", exc_info=True)

        available_ids = {i.plugin_id for i in items}
        selected = preferred if preferred in available_ids else (items[0].plugin_id if items else None)
        self._active_workspace_id = selected
        self._sidebar.set_selected(selected)
        self._show_workspace_widget(selected)
        self._publish_active_workspace(selected)
        self._update_placeholder_text()

    def _publish_active_workspace(self, workspace_id: PluginId | None) -> None:
        app_ctx = self._get_app_context()
        if app_ctx is None:
            return
        try:
            # Focus transition order:
            # 1) defocus old workspace
            # 2) switch active workspace id
            # 3) focus new workspace
            host = getattr(app_ctx, "plugin_host", None)
            if host is not None:
                try:
                    old = host.focused_workspace()
                except Exception:
                    old = None
                if old != workspace_id:
                    host.set_focused_workspace(app_ctx=app_ctx, plugin_id=None)

            app_ctx.workspace_state.set_active_workspace_id(str(workspace_id) if workspace_id is not None else None)
        except Exception:
            log.debug("Failed to publish active workspace id (best-effort)", exc_info=True)
        try:
            host = getattr(app_ctx, "plugin_host", None)
            if host is not None:
                host.set_focused_workspace(app_ctx=app_ctx, plugin_id=workspace_id)
        except Exception:
            log.debug("Failed to dispatch workspace focus change (best-effort)", exc_info=True)

    def _on_workspace_selected(self, plugin_id: object) -> None:
        selected = PluginId(str(plugin_id))
        self._active_workspace_id = selected
        self._sidebar.set_selected(selected)
        self._show_workspace_widget(selected)
        self._publish_active_workspace(selected)
        self._update_placeholder_text()

    def on_project_changed(self) -> None:
        """
        Refresh UI state after a project open/close/switch.

        This is intentionally lightweight: it updates gating text/menu state and
        restores any persisted per-project main window UI state.
        """
        self._ui_state_last_snapshot = None
        self._restore_ui_state_from_project_db()
        self._refresh_project_state()

    def _open_project(self, project_root: Path) -> None:
        from datalens.infra.background.loader_context import LoaderContext
        from datalens.infra.background.loader_runner import run_with_loader
        from datalens.services.project_service import ProjectCloseError, open_project_with_plugins, close_project
        from datalens.services.settings_store import SettingsStore
        from datalens.domain.system.settings import AppSettings
        from dataclasses import replace

        app_ctx = self._get_app_context()
        if app_ctx is None:
            QMessageBox.critical(self, "Open Project", "Application context is not available.")
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
            # Persist MRU updates off the UI thread.
            try:
                store = SettingsStore()
                updated = store.update(update_recents)
                return tuple(updated.recent_projects)
            except Exception:
                return None

        def on_done(result: object) -> None:
            if isinstance(result, tuple) and all(isinstance(p, Path) for p in result):
                self._recent_projects = list(result)
                self._menubar.set_recent_projects(self._recent_projects)
            self.on_project_changed()

        def on_error(exc: Exception) -> None:
            if isinstance(exc, ProjectCloseError):
                dialog = QMessageBox(self)
                dialog.setIcon(QMessageBox.Critical)
                dialog.setWindowTitle("Failed to Close Project")
                dialog.setText(str(exc))
                dialog.setInformativeText(
                    "Retry to attempt a safe close again, cancel to keep the current project open, "
                    "or force close and open the new project (may lose unsaved work)."
                )
                retry = dialog.addButton("Retry", QMessageBox.AcceptRole)
                cancel = dialog.addButton("Cancel", QMessageBox.RejectRole)
                force_btn = dialog.addButton("Force Close + Open", QMessageBox.DestructiveRole)
                dialog.setDefaultButton(retry)
                dialog.exec()

                clicked = dialog.clickedButton()
                if clicked is retry:
                    self._open_project(project_root)
                    return
                if clicked is force_btn:
                    def force_task(ctx: LoaderContext) -> object:
                        ctx.log("Force closing current project (best-effort)...")
                        close_project(app_ctx)
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
                        parent=self,
                        title="Opening Project...",
                        task=force_task,
                        on_result=on_done,
                        on_error=lambda e: QMessageBox.critical(self, "Open Project", str(e)),
                        dialog_options={"spinner_size": 80, "title_point_size": 18, "subtitle_point_size": 12},
                    )
                    return
                return

            QMessageBox.critical(self, "Open Project", str(exc))
            self.on_project_changed()

        run_with_loader(
            parent=self,
            title="Opening Project...",
            task=task,
            on_result=on_done,
            on_error=on_error,
            dialog_options={"spinner_size": 80, "title_point_size": 18, "subtitle_point_size": 12},
        )

    def _close_project_interactive(self) -> None:
        from datalens.services.project_service import close_project, close_project_blocking

        app_ctx = self._get_app_context()
        if app_ctx is None or getattr(app_ctx, "active_project", None) is None:
            return

        self._run_project_close_loader(
            app_ctx=app_ctx,
            close_project=close_project,
            close_project_blocking=close_project_blocking,
            force_close_label="Force Close",
            on_closed=lambda: self.on_project_changed(),
            on_cancel=lambda: None,
            close_window_after=False,
        )

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

        from datalens.services.project_service import close_project, close_project_blocking

        self._run_project_close_loader(
            app_ctx=app_ctx,
            close_project=close_project,
            close_project_blocking=close_project_blocking,
            force_close_label="Force Close",
            on_closed=lambda: (setattr(self, "_close_in_progress", False), QTimer.singleShot(0, self.close)),
            on_cancel=lambda: setattr(self, "_close_in_progress", False),
            close_window_after=True,
        )

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
    ) -> None:
        """
        Shared close-project loader flow used by interactive close and window close.

        This keeps the UI thread free while flushing/closing runs on the loader worker.
        """
        from datalens.infra.background.loader_context import LoaderContext
        from datalens.infra.background.loader_runner import run_with_loader

        # Ensure the last UI-state snapshot is submitted before the DB flush.
        try:
            self._ui_state_queue.flush()
        except Exception:
            pass

        def run_close(*, force: bool) -> None:
            def task(ctx: LoaderContext) -> object:
                if force:
                    ctx.log("Force closing project (best-effort)...")
                    close_project(app_ctx)
                else:
                    ctx.log("Flushing project...")
                    close_project_blocking(app_ctx, timeout_seconds=30.0)

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
                dialog = QMessageBox(self)
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
                parent=self,
                title="Closing Project...",
                task=task,
                on_result=on_done,
                on_error=on_error,
                dialog_options={"spinner_size": 80, "title_point_size": 18, "subtitle_point_size": 12},
            )

        run_close(force=False)
