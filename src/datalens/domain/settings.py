from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, MutableMapping

from .plugin import PluginId
from .ui.theme import ThemeOpacitySettings
from .user_profile import UserProfile


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

    # Recently opened projects (most recent first)
    recent_projects: tuple[Path, ...] = field(default_factory=tuple)

    # Welcome window UI state (app/user scoped).
    welcome_splitter_state_b64: str | None = None

    # IDs of plugins that are enabled globally
    enabled_plugins: frozenset[PluginId] = field(default_factory=frozenset)

    # Arbitrary plugin settings, namespaced by plugin ID
    plugin_settings: Mapping[str, Mapping[str, object]] = field(default_factory=dict)

    # Theme / UI-related settings can be added here or in a separate theme dataclass
    theme_name: str = "default"
    theme_opacity: ThemeOpacitySettings = field(default_factory=ThemeOpacitySettings)

    # Optional user profile information (used by welcome screen and future gating)
    user_profile: UserProfile | None = None

    def is_plugin_enabled(self, plugin_id: PluginId) -> bool:
        return plugin_id in self.enabled_plugins
