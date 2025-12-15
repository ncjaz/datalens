from __future__ import annotations

from datalens.domain.plugin import PluginId
from datalens.services.plugins.runtime import BasePlugin, PluginAppContext, PluginProjectContext, PluginFutureResult


class MEvalPlugin(BasePlugin):
    @property
    def plugin_id(self) -> PluginId:
        return PluginId("meval")

    def on_load(self, ctx: PluginAppContext) -> None:
        # TODO(v2): Wire evaluation services and UI feature registration.
        return None

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Restore MEval UI state and load project-scoped evaluation artifacts.
        return None

    def on_project_migrate(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Replace schema_version=1 with the plugin's real schema version once
        # the MEval plugin owns tables beyond `plugin_kv`.
        return ctx.db.plugin_meta_set(plugin_version=ctx.plugin.version, schema_version=1)

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Flush any evaluation background work (exports, caches) before close.
        return None


def get_plugin() -> BasePlugin:
    return MEvalPlugin()
