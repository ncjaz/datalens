from __future__ import annotations

from datalens.domain.plugin import PluginId
from datalens.services.plugins.runtime import BasePlugin, PluginAppContext, PluginProjectContext, PluginFutureResult


class CapturePlugin(BasePlugin):
    @property
    def plugin_id(self) -> PluginId:
        return PluginId("capture")

    def on_load(self, ctx: PluginAppContext) -> None:
        return None

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        return None

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        return None


def get_plugin() -> BasePlugin:
    return CapturePlugin()

