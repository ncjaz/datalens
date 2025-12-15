from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from datalens.domain.plugin import PluginDefinition, PluginId


class PluginOrigin(str, Enum):
    """Where a plugin came from (shipped vs. user-installed)."""

    SHIPPED = "shipped"
    USER = "user"


@dataclass(frozen=True)
class PluginLocation:
    origin: PluginOrigin
    root_dir: Path


@dataclass(frozen=True)
class PluginRequirements:
    """
    Derived dependency specifiers for a plugin.

    The loader reads these from `requirements.txt` (if present) so plugin
    authors don't need to duplicate dependency lists in manifests.
    """

    pip_requirements: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginRecord:
    definition: PluginDefinition
    location: PluginLocation
    requirements: PluginRequirements


class PluginRegistry:
    """In-memory registry of discovered plugins."""

    def __init__(self) -> None:
        self._by_id: dict[PluginId, PluginRecord] = {}

    def register(self, record: PluginRecord) -> None:
        plugin_id = record.definition.id
        if plugin_id in self._by_id:
            existing = self._by_id[plugin_id]
            raise ValueError(
                "Duplicate plugin id "
                f"{plugin_id!r}: {existing.location.origin} at {existing.location.root_dir} "
                f"and {record.location.origin} at {record.location.root_dir}"
            )
        self._by_id[plugin_id] = record

    def get(self, plugin_id: PluginId) -> PluginRecord | None:
        return self._by_id.get(plugin_id)

    def all(self) -> list[PluginRecord]:
        return list(self._by_id.values())
