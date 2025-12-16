from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from datalens.core.logging import get_logger
from datalens.domain.settings import AppSettings
from datalens.domain.plugin import PluginId
from datalens.domain.user_profile import UserProfile
from datalens.domain.ui.theme import ThemeOpacitySettings


def _settings_from_dict(data: dict[str, Any]) -> AppSettings:
    last_project_root_raw = data.get("last_project_root")
    last_project_root = Path(last_project_root_raw) if isinstance(last_project_root_raw, str) else None

    recent_projects_raw = data.get("recent_projects", [])
    recent_projects: list[Path] = []
    if isinstance(recent_projects_raw, list):
        for item in recent_projects_raw:
            if not isinstance(item, str):
                continue
            try:
                path = Path(item)
            except Exception:
                continue
            if path.exists():
                recent_projects.append(path)

    welcome_splitter_state_b64 = data.get("welcome_splitter_state_b64")
    if not isinstance(welcome_splitter_state_b64, str):
        welcome_splitter_state_b64 = None

    enabled_plugins_raw = data.get("enabled_plugins", [])
    enabled_plugins: frozenset[PluginId] = frozenset(
        PluginId(p) for p in enabled_plugins_raw if isinstance(p, str)
    )

    plugin_settings_raw = data.get("plugin_settings", {})
    plugin_settings = plugin_settings_raw if isinstance(plugin_settings_raw, dict) else {}

    theme_name = data.get("theme_name", "default")
    if not isinstance(theme_name, str):
        theme_name = "default"

    opacity_raw = data.get("theme_opacity", {})
    if not isinstance(opacity_raw, dict):
        opacity_raw = {}

    theme_opacity = ThemeOpacitySettings(
        hover_fill=float(opacity_raw.get("hover_fill", ThemeOpacitySettings.hover_fill)),
        selected_fill=float(opacity_raw.get("selected_fill", ThemeOpacitySettings.selected_fill)),
        subtle_fill=float(opacity_raw.get("subtle_fill", ThemeOpacitySettings.subtle_fill)),
        disabled_text=float(opacity_raw.get("disabled_text", ThemeOpacitySettings.disabled_text)),
        disabled_fill=float(opacity_raw.get("disabled_fill", ThemeOpacitySettings.disabled_fill)),
        disabled_border=float(opacity_raw.get("disabled_border", ThemeOpacitySettings.disabled_border)),
    )

    user_profile_raw = data.get("user_profile")
    if isinstance(user_profile_raw, dict):
        name = user_profile_raw.get("name", "")
        email = user_profile_raw.get("email", "")
        user_profile = UserProfile(
            name=str(name) if isinstance(name, str) else "",
            email=str(email) if isinstance(email, str) else "",
        ).normalized()
    else:
        user_profile = None

    return AppSettings(
        last_project_root=last_project_root,
        recent_projects=tuple(recent_projects),
        welcome_splitter_state_b64=welcome_splitter_state_b64,
        enabled_plugins=enabled_plugins,
        plugin_settings=plugin_settings,
        theme_name=theme_name,
        theme_opacity=theme_opacity,
        user_profile=user_profile,
    )


def _settings_to_dict(settings: AppSettings) -> dict[str, Any]:
    payload = asdict(settings)
    payload["last_project_root"] = str(settings.last_project_root) if settings.last_project_root else None
    payload["recent_projects"] = [str(p) for p in settings.recent_projects]
    payload["welcome_splitter_state_b64"] = settings.welcome_splitter_state_b64
    payload["enabled_plugins"] = list(settings.enabled_plugins)
    payload["theme_opacity"] = asdict(settings.theme_opacity)
    payload["user_profile"] = asdict(settings.user_profile) if settings.user_profile else None
    return payload


def load_app_settings(path: Path) -> AppSettings:
    """
    Load settings from disk.

    Returns defaults if the file does not exist or cannot be parsed.
    """
    try:
        if not path.exists():
            return AppSettings()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return AppSettings()
        return _settings_from_dict(data)
    except Exception as exc:
        # Fall back to defaults but keep the failure visible in logs.
        get_logger(__name__).warning(
            "Failed to load app settings from %s: %s",
            path,
            exc,
            extra={"operation": "load_app_settings", "phase": "error"},
        )
        return AppSettings()


def save_app_settings(path: Path, settings: AppSettings) -> None:
    """Persist settings to disk (atomic write)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_settings_to_dict(settings), indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
