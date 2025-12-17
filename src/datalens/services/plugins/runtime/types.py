from __future__ import annotations

from dataclasses import dataclass

from datalens.services.plugins.registry import PluginRecord
from datalens.services.plugins.runtime.contracts import BasePlugin


class PluginLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class PluginRuntime:
    record: PluginRecord
    instance: BasePlugin

