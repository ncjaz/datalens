from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId, PluginKind
from datalens.services.plugins.registry import PluginRecord
from datalens.ui.widgets.navigation.plugin_sidebar import PluginNavItem, PluginSidebar, nav_label_for

from .app_context import try_get_app_context

log = get_logger(__name__)


class WorkspacesController:
    """
    Workspace navigation + display for MainWindow.

    Responsibilities:
    - build sidebar + workspace stack UI
    - create/caches workspace widgets (Qt thread)
    - update placeholder text for project/no-project + plugin states
    - publish active workspace to runtime services (focus/defocus + state)
    """

    def __init__(
        self,
        window: QWidget,
        *,
        plugins: list[PluginRecord],
        enabled_plugin_ids: set[PluginId] | None,
    ) -> None:
        self._window = window
        self._plugins = list(plugins)
        self._enabled_plugin_ids = enabled_plugin_ids

        self._active_workspace_id: PluginId | None = None
        self._last_project_root: Path | None = None
        self._workspace_placeholder_reason: str | None = None

        self.sidebar = PluginSidebar(window)
        self.sidebar.pluginSelected.connect(self._on_workspace_selected)

        self._label = QLabel("", window)
        self._label.setAlignment(Qt.AlignCenter)

        self.workspace_stack = QStackedWidget(window)
        self.workspace_stack.addWidget(self._label)
        self._workspace_widgets: dict[PluginId, QWidget] = {}

        right = QWidget(window)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.workspace_stack, 1)

        central = QWidget(window)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar, 0)
        layout.addWidget(right, 1)
        self.central_widget = central

        self.refresh_workspace_nav()
        self._refresh_project_state()

    @property
    def active_workspace_id(self) -> PluginId | None:
        return self._active_workspace_id

    def on_plugins_enabled(self) -> None:
        if self._active_workspace_id is None:
            return
        self.show_workspace_widget(self._active_workspace_id)
        self.publish_active_workspace(self._active_workspace_id)
        self._update_placeholder_text()

    def on_project_changed(self) -> None:
        self._refresh_project_state()

    def set_plugins(self, plugins: list[PluginRecord], enabled_plugin_ids: set[PluginId] | None) -> None:
        self._plugins = list(plugins)
        self._enabled_plugin_ids = enabled_plugin_ids
        self.refresh_workspace_nav()

    def _refresh_project_state(self) -> None:
        app_ctx = try_get_app_context()
        project = getattr(app_ctx, "active_project", None) if app_ctx is not None else None
        self._last_project_root = getattr(project, "project_root", None) if project is not None else None
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

        reason = self._workspace_placeholder_reason
        if reason:
            self._label.setText(f"{ws_line}\n\n{project_line}\n\n{reason}")
        else:
            self._label.setText(f"{ws_line}\n\n{project_line}")

    def refresh_workspace_nav(self) -> None:
        items: list[PluginNavItem] = []
        for record in self._plugins:
            definition = record.definition
            # PluginDefinition does not have a single `kind`; it can expose multiple
            # features (workspace + service, etc.). Only include plugins that expose
            # at least one WORKSPACE feature.
            if not any(getattr(f, "kind", None) == PluginKind.WORKSPACE for f in getattr(definition, "features", ())):
                continue
            if self._enabled_plugin_ids is not None and definition.id not in self._enabled_plugin_ids:
                continue
            icon_path: Path | None = None
            nav_icon = getattr(definition, "nav_icon", None)
            if isinstance(nav_icon, str) and nav_icon.strip():
                try:
                    icon_path = record.location.root_dir / nav_icon
                except Exception:
                    icon_path = None
            items.append(
                PluginNavItem(
                    plugin_id=definition.id,
                    name=definition.name,
                    nav_label=nav_label_for(definition),
                    icon_path=icon_path,
                )
            )

        self.sidebar.set_items(items)

        preferred: PluginId | None = None
        app_ctx = try_get_app_context()
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
        self.set_active_workspace(selected)

    def set_active_workspace(self, workspace_id: PluginId | None) -> None:
        self._active_workspace_id = workspace_id
        self.sidebar.set_selected(workspace_id)
        self.show_workspace_widget(workspace_id)
        self.publish_active_workspace(workspace_id)
        self._update_placeholder_text()

    def show_workspace_widget(self, workspace_id: PluginId | None) -> None:
        if workspace_id is None:
            self._workspace_placeholder_reason = None
            self.workspace_stack.setCurrentWidget(self._label)
            return

        widget = self._workspace_widgets.get(workspace_id)
        if widget is not None:
            self._workspace_placeholder_reason = None
            self.workspace_stack.setCurrentWidget(widget)
            return

        app_ctx = try_get_app_context()
        host = getattr(app_ctx, "plugin_host", None) if app_ctx is not None else None
        if host is None:
            self._workspace_placeholder_reason = "Plugins are not enabled yet."
            self.workspace_stack.setCurrentWidget(self._label)
            return

        try:
            plugin = host.get_enabled_plugin(workspace_id)
            record = host.get_enabled_record(workspace_id)
        except Exception:
            plugin = None
            record = None

        if plugin is None or record is None:
            self._workspace_placeholder_reason = "Workspace plugin is not enabled."
            self.workspace_stack.setCurrentWidget(self._label)
            return

        create_fn = getattr(plugin, "create_workspace_widget", None)
        if not callable(create_fn):
            self._workspace_placeholder_reason = "Workspace plugin provides no UI."
            self.workspace_stack.setCurrentWidget(self._label)
            return

        try:
            from datalens.services.plugins.runtime.contracts import PluginAppContext

            ctx = PluginAppContext(app=app_ctx, plugin=record.definition)  # type: ignore[arg-type]
            created = create_fn(self.workspace_stack, ctx)
        except Exception:
            log.warning("Failed to create workspace widget (best-effort)", exc_info=True)
            self._workspace_placeholder_reason = "Workspace UI failed to load (see logs)."
            self.workspace_stack.setCurrentWidget(self._label)
            return

        if not isinstance(created, QWidget):
            self._workspace_placeholder_reason = "Workspace UI returned an invalid widget."
            self.workspace_stack.setCurrentWidget(self._label)
            return

        self._workspace_widgets[workspace_id] = created
        self.workspace_stack.addWidget(created)
        self._workspace_placeholder_reason = None
        self.workspace_stack.setCurrentWidget(created)

    def publish_active_workspace(self, workspace_id: PluginId | None) -> None:
        app_ctx = try_get_app_context()
        if app_ctx is None:
            return
        try:
            host = getattr(app_ctx, "plugin_host", None)
            if host is not None:
                try:
                    old = host.focused_workspace()
                except Exception:
                    old = None
                if old != workspace_id:
                    host.set_focused_workspace(app_ctx=app_ctx, plugin_id=None)

            app_ctx.workspace_state.set_active_workspace_id(str(workspace_id) if workspace_id is not None else None)
            try:
                if getattr(app_ctx, "shortcuts", None) is not None:
                    if workspace_id is not None:
                        app_ctx.shortcuts.tag_window_with_plugin(self._window, workspace_id)
                    else:
                        self._window.setProperty("datalens.plugin_id", "")
            except Exception:
                pass
        except Exception:
            log.debug("Failed to publish active workspace id (best-effort)", exc_info=True)
        try:
            host = getattr(app_ctx, "plugin_host", None)
            if host is not None:
                host.set_focused_workspace(app_ctx=app_ctx, plugin_id=workspace_id)
        except Exception:
            log.debug("Failed to dispatch workspace focus change (best-effort)", exc_info=True)

    def _on_workspace_selected(self, plugin_id: object) -> None:
        self.set_active_workspace(PluginId(str(plugin_id)))


__all__ = ["WorkspacesController"]
