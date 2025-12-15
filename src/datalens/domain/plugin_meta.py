from __future__ import annotations

from dataclasses import dataclass

from datalens.domain.plugin import PluginId


@dataclass(frozen=True)
class PluginMeta:
    """
    Plugin-owned metadata stored in the core-owned `plugin_meta` table.

    The core app owns the table schema; plugins own their individual rows.
    """

    plugin_id: PluginId
    plugin_version: str
    schema_version: int
    updated_at: str

