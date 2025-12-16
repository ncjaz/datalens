from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass

from datalens.domain.plugin import PluginId
from datalens.domain.plugin_meta import PluginMeta
from datalens.services.db.project_db import ProjectDb


@dataclass(frozen=True)
class PluginDb:
    """
    Plugin-scoped database facade.

    This wrapper enforces plugin-owned row boundaries for core-owned tables:
    - `plugin_kv`: the plugin can only read/write its own namespace.
    - `plugin_meta`: the plugin can only read/write its own row.
    """

    project_db: ProjectDb
    plugin_id: PluginId

    def kv_get(self, key: str) -> Future[object | None]:
        return self.project_db.kv_get(self.plugin_id, key)

    def kv_set(self, key: str, value: object) -> Future[None]:
        return self.project_db.kv_set(self.plugin_id, key, value)

    def plugin_meta_get(self) -> Future[PluginMeta | None]:
        return self.project_db.plugin_meta_get(self.plugin_id)

    def plugin_meta_set(self, *, plugin_version: str, schema_version: int) -> Future[None]:
        return self.project_db.plugin_meta_set(
            self.plugin_id,
            plugin_version=plugin_version,
            schema_version=schema_version,
        )

