from __future__ import annotations

from datalens.domain.plugin import PluginId
from datalens.services.plugins.runtime import BasePlugin, PluginAppContext, PluginProjectContext, PluginFutureResult


class TrainPlugin(BasePlugin):
    @property
    def plugin_id(self) -> PluginId:
        return PluginId("train")

    def on_load(self, ctx: PluginAppContext) -> None:
        # TODO(v2): Wire training registry/services and UI feature registration.
        return None

    def on_unload(self, ctx: PluginAppContext) -> None:
        # TODO(v2): Disconnect UI/actions and stop any app-scoped services.
        return None

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Restore training UI state and load any project-scoped training metadata.
        return None

    def on_project_migrate(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Replace schema_version=1 with the plugin's real schema version once
        # the train plugin owns tables beyond `plugin_kv`.
        return ctx.db.plugin_meta_set(plugin_version=ctx.plugin.version, schema_version=1)

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Flush/stop training jobs safely and return futures so shutdown can await.
        return None


def get_plugin() -> BasePlugin:
    return TrainPlugin()
