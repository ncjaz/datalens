from __future__ import annotations

from datalens.domain.plugin import PluginId
from datalens.services.plugins.runtime import BasePlugin, PluginAppContext, PluginProjectContext, PluginFutureResult


class ReviewPlugin(BasePlugin):
    @property
    def plugin_id(self) -> PluginId:
        return PluginId("review")

    def on_load(self, ctx: PluginAppContext) -> None:
        # TODO(v2): Wire plugin feature registration (workspace) and any app-scoped services.
        return None

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Restore review UI state (filters/sort) from `ctx.db.kv_get`.
        return None

    def on_project_migrate(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Replace schema_version=1 with the plugin's real schema version once
        # the review plugin owns tables beyond `plugin_kv`.
        return ctx.db.plugin_meta_set(plugin_version=ctx.plugin.version, schema_version=1)

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Flush any long-running review tasks (indexes, exports) before close.
        return None


def get_plugin() -> BasePlugin:
    return ReviewPlugin()
