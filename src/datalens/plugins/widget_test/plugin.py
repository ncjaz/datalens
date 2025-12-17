from __future__ import annotations

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.services.plugins.runtime import BasePlugin, PluginAppContext, PluginProjectContext, PluginFutureResult


log = get_logger(__name__)


class WidgetTestPlugin(BasePlugin):
    """Plugin runtime entrypoint for `widget test`.

    Notes for plugin authors:
    - All hooks run on the caller thread (typically a background loader stage).
      Keep hooks fast; schedule heavy work to background systems (DB/IoWriter/threadpool).
    - Do not touch Qt widgets from background threads. Only mutate UI on the Qt thread.
    - Project hooks may be called with no UI focus (headless service behavior).

    Hook order (typical):
    - `on_load` once per app run when enabled
    - (optional) `on_project_migrate` then `on_project_opened` when a project is opened
    - `on_project_closing` on close/switch (return Futures for flush waits)
    - `on_unload` when disabled or app exits

    Workspace plugins (kind=`workspace`) may also receive:
    - `on_defocus` then `on_focus` when switching active workspaces
    """

    @property
    def plugin_id(self) -> PluginId:
        return PluginId('widget_test')

    def on_load(self, ctx: PluginAppContext) -> None:
        """App-scope setup.

        Do lightweight registration only (menus, actions, capability providers).
        Avoid blocking I/O and long computations here.
        """
        return None

    def on_unload(self, ctx: PluginAppContext) -> None:
        """App-scope teardown.

        Disconnect signals/actions and stop app-scoped services started in `on_load`.
        """
        return None

    def on_focus(self, ctx: PluginAppContext) -> None:
        """Called when this workspace becomes active in the UI."""
        return None

    def on_defocus(self, ctx: PluginAppContext) -> None:
        """Called when this workspace is no longer active in the UI."""
        return None

    def create_workspace_widget(self, parent, ctx: PluginAppContext):
        """
        Create the workspace widget for this plugin.

        This is called on the Qt UI thread when the workspace becomes visible.
        Keep widget construction reasonably fast; offload heavy work to services.
        """
        from .ui.workspace import WorkspaceWidget

        return WorkspaceWidget(theme=ctx.app.theme, parent=parent)

    def on_project_migrate(self, ctx: PluginProjectContext) -> PluginFutureResult:
        """Project-scope DB migrations (runs before `on_project_opened`)."""
        return ctx.db.plugin_meta_set(plugin_version=ctx.plugin.version, schema_version=1)

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        """Project-scope setup.

        Start watchers/pipelines and restore state from `ctx.db.kv_get(...)`.
        """
        return None

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        """Project-scope teardown.

        Stop pipelines and return Futures representing flush/shutdown work so core can await them.
        """
        return None


def get_plugin() -> BasePlugin:
    return WidgetTestPlugin()
