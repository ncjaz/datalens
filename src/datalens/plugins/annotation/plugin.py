from __future__ import annotations

from datalens.domain.plugin import PluginId
from datalens.services.plugins.runtime import BasePlugin, PluginAppContext, PluginProjectContext, PluginFutureResult


class AnnotationPlugin(BasePlugin):
    @property
    def plugin_id(self) -> PluginId:
        return PluginId("annotation")

    def on_load(self, ctx: PluginAppContext) -> None:
        # TODO(v2): Wire plugin feature registration and any app-scoped services.
        return None

    def on_unload(self, ctx: PluginAppContext) -> None:
        # TODO(v2): Disconnect UI/actions and stop any app-scoped services.
        return None

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Create/open the actual annotation workspace and connect UI events
        # to debounced persistence (V1-style).
        return None

    def on_project_migrate(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Replace schema_version=1 with the plugin's real schema version once
        # the annotation plugin owns tables beyond `plugin_kv`.
        return ctx.db.plugin_meta_set(plugin_version=ctx.plugin.version, schema_version=1)

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        # TODO(v2): Flush any annotation background pipelines (export queues, etc.)
        # and return futures so the host can await them during shutdown.
        return None


def get_plugin() -> BasePlugin:
    return AnnotationPlugin()
