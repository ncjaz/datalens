from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from datalens.domain.plugin import PluginId
from datalens.domain.ui.theme import ThemeOpacitySettings
from datalens.domain.ui.theme import DEFAULT_THEME, ThemeSettings
from datalens.domain.system.plugin_overrides import PluginDefinitionOverride
from datalens.domain.system.shortcuts import ShortcutOverrides
from datalens.domain.system.ui import LoaderUiSettings
from datalens.domain.system.user_profile import UserProfile


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

    # Optional override for where app/user-scoped data (plugins, caches, etc.) live.
    # Note: `settings.json` remains in the default app data dir; this field is for
    # other user data only.
    user_data_dir: Path | None = None

    # IDs of plugins that are enabled globally
    enabled_plugins: frozenset[PluginId] = field(default_factory=frozenset)

    # Loader dialog UI preferences (app/user scoped).
    loader_ui: LoaderUiSettings = field(default_factory=LoaderUiSettings)

    # Shortcut overrides (semantic preferences). Defaults come from registrations.
    shortcut_overrides: ShortcutOverrides = field(default_factory=ShortcutOverrides)

    # Arbitrary plugin settings, namespaced by plugin ID
    plugin_settings: Mapping[str, Mapping[str, object]] = field(default_factory=dict)

    # User/app overrides for manifest-derived plugin metadata (no on-disk manifest edits).
    plugin_overrides: Mapping[str, PluginDefinitionOverride] = field(default_factory=dict)

    # Theme / UI-related settings can be added here or in a separate theme dataclass
    theme_name: str = "default"
    theme_settings: ThemeSettings = field(default_factory=lambda: DEFAULT_THEME)
    theme_opacity: ThemeOpacitySettings = field(default_factory=ThemeOpacitySettings)

    # Optional user profile information (used by welcome screen and future gating)
    user_profile: UserProfile | None = None

    def is_plugin_enabled(self, plugin_id: PluginId) -> bool:
        return plugin_id in self.enabled_plugins


__all__ = ["AppSettings"]
