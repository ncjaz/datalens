from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Mapping

from datalens.domain.plugin import PluginDefinition, PluginId
from datalens.domain.system.plugin_overrides import PluginDefinitionOverride


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

    def apply_definition_overrides(self, overrides: Mapping[str, PluginDefinitionOverride]) -> None:
        """
        Apply user/app overrides to manifest-derived plugin definitions.

        This mutates the in-memory registry only; it does not edit plugin
        manifests on disk.
        """
        if not overrides:
            return

        for plugin_id_raw, override in overrides.items():
            if not isinstance(plugin_id_raw, str) or not plugin_id_raw.strip():
                continue
            record = self._by_id.get(PluginId(plugin_id_raw))
            if record is None:
                continue

            defn = record.definition
            name = override.name.strip() if isinstance(override.name, str) else None
            description = override.description.strip() if isinstance(override.description, str) else None

            author_raw = override.author if isinstance(override.author, str) else None
            author = author_raw.strip() if author_raw is not None else None
            if author == "":
                author = None

            group_raw = override.group if isinstance(override.group, str) else None
            group = group_raw.strip() if group_raw is not None else None
            if group == "":
                group = None

            nav_label_raw = override.nav_label if isinstance(override.nav_label, str) else None
            nav_label = nav_label_raw.strip().upper() if nav_label_raw is not None else None
            if nav_label == "":
                nav_label = None
            if nav_label is not None and len(nav_label) > 2:
                nav_label = nav_label[:2]

            updated = replace(
                defn,
                name=name or defn.name,
                description=description or defn.description,
                author=author if override.author is not None else defn.author,
                group=group if override.group is not None else defn.group,
                nav_label=nav_label if override.nav_label is not None else defn.nav_label,
            )
            self._by_id[PluginId(plugin_id_raw)] = replace(record, definition=updated)
