from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, MutableMapping

from .plugins import PluginId


@dataclass(frozen=True)
class AppSettings:
    """
    Root settings schema that can be persisted in a simple JSON/YAML
    config file and/or SQL.

    - Plugin-specific settings live under `plugin_settings` using their
      plugin ID as the first key.
    """

    # Last opened project root (if any)
    last_project_root: Path | None = None

    # IDs of plugins that are enabled globally
    enabled_plugins: frozenset[PluginId] = field(default_factory=frozenset)

    # Arbitrary plugin settings, namespaced by plugin ID
    plugin_settings: Mapping[str, Mapping[str, object]] = field(default_factory=dict)

    # Theme / UI-related settings can be added here or in a separate theme dataclass
    theme_name: str = "default"

    def is_plugin_enabled(self, plugin_id: PluginId) -> bool:
        return plugin_id in self.enabled_plugins
