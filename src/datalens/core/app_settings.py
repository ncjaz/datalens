from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from datalens.core.logging import get_logger
from datalens.domain.system.settings import AppSettings
from datalens.domain.plugin import PluginId
from datalens.domain.system.user_profile import UserProfile
from datalens.domain.system.ui import LoaderUiSettings
from datalens.domain.system.plugin_overrides import PluginDefinitionOverride
from datalens.domain.system.shortcuts import ShortcutOverrides
from datalens.domain.ui.theme import DEFAULT_THEME, ThemeOpacitySettings, ThemeSettings


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

    user_data_dir_raw = data.get("user_data_dir")
    if isinstance(user_data_dir_raw, str) and user_data_dir_raw.strip():
        try:
            user_data_dir = Path(user_data_dir_raw)
        except Exception:
            user_data_dir = None
    else:
        user_data_dir = None

    enabled_plugins_raw = data.get("enabled_plugins", [])
    enabled_plugins: frozenset[PluginId] = frozenset(
        PluginId(p) for p in enabled_plugins_raw if isinstance(p, str)
    )

    plugin_settings_raw = data.get("plugin_settings", {})
    plugin_settings = plugin_settings_raw if isinstance(plugin_settings_raw, dict) else {}

    plugin_overrides_raw = data.get("plugin_overrides", {})
    plugin_overrides: dict[str, PluginDefinitionOverride] = {}
    if isinstance(plugin_overrides_raw, dict):
        for plugin_id, raw in plugin_overrides_raw.items():
            if not isinstance(plugin_id, str) or not plugin_id.strip():
                continue
            if not isinstance(raw, dict):
                continue
            name = raw.get("name")
            description = raw.get("description")
            author = raw.get("author")
            group = raw.get("group")
            nav_label = raw.get("nav_label")

            plugin_overrides[plugin_id] = PluginDefinitionOverride(
                name=str(name) if name is not None else None,
                description=str(description) if description is not None else None,
                author=str(author) if author is not None else None,
                group=str(group) if group is not None else None,
                nav_label=str(nav_label) if nav_label is not None else None,
            )

    theme_name = data.get("theme_name", "default")
    if not isinstance(theme_name, str):
        theme_name = "default"

    theme_settings_raw = data.get("theme_settings")
    if isinstance(theme_settings_raw, dict):
        primary_color = str(theme_settings_raw.get("primary_color", DEFAULT_THEME.primary_color))
        background_color = str(theme_settings_raw.get("background_color", DEFAULT_THEME.background_color))
        secondary_color = str(theme_settings_raw.get("secondary_color", DEFAULT_THEME.secondary_color))
        tertiary_color = str(theme_settings_raw.get("tertiary_color", DEFAULT_THEME.tertiary_color))
        text_color = str(theme_settings_raw.get("text_color", DEFAULT_THEME.text_color))
        chart_grid_color = str(theme_settings_raw.get("chart_grid_color", DEFAULT_THEME.chart_grid_color))
        accent_confirm = str(theme_settings_raw.get("accent_confirm", DEFAULT_THEME.accent_confirm))
        accent_cancel = str(theme_settings_raw.get("accent_cancel", DEFAULT_THEME.accent_cancel))
        accent_warning = str(theme_settings_raw.get("accent_warning", DEFAULT_THEME.accent_warning))

        primary_border = str(theme_settings_raw.get("primary_border", DEFAULT_THEME.primary_border))
        secondary_border = str(theme_settings_raw.get("secondary_border", DEFAULT_THEME.secondary_border))
        tertiary_border = str(theme_settings_raw.get("tertiary_border", DEFAULT_THEME.tertiary_border))
        accent_confirm_border = str(
            theme_settings_raw.get("accent_confirm_border", DEFAULT_THEME.accent_confirm_border)
        )
        accent_cancel_border = str(theme_settings_raw.get("accent_cancel_border", DEFAULT_THEME.accent_cancel_border))
        accent_warning_border = str(
            theme_settings_raw.get("accent_warning_border", DEFAULT_THEME.accent_warning_border)
        )

        surface_base = theme_settings_raw.get("surface_base")
        surface_button = theme_settings_raw.get("surface_button")
        surface_alt = theme_settings_raw.get("surface_alt")

        theme_settings = ThemeSettings(
            primary_color=primary_color,
            background_color=background_color,
            secondary_color=secondary_color,
            tertiary_color=tertiary_color,
            text_color=text_color,
            chart_grid_color=chart_grid_color,
            accent_confirm=accent_confirm,
            accent_cancel=accent_cancel,
            accent_warning=accent_warning,
            primary_border=primary_border,
            secondary_border=secondary_border,
            tertiary_border=tertiary_border,
            accent_confirm_border=accent_confirm_border,
            accent_cancel_border=accent_cancel_border,
            accent_warning_border=accent_warning_border,
            surface_base=str(surface_base) if isinstance(surface_base, str) and surface_base.strip() else None,
            surface_button=str(surface_button) if isinstance(surface_button, str) and surface_button.strip() else None,
            surface_alt=str(surface_alt) if isinstance(surface_alt, str) and surface_alt.strip() else None,
        )
    else:
        theme_settings = DEFAULT_THEME

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

    loader_ui_raw = data.get("loader_ui", {})
    if not isinstance(loader_ui_raw, dict):
        loader_ui_raw = {}

    loader_ui = LoaderUiSettings(
        show_ctx_messages=bool(loader_ui_raw.get("show_ctx_messages", LoaderUiSettings.show_ctx_messages)),
        show_log_progress=bool(loader_ui_raw.get("show_log_progress", LoaderUiSettings.show_log_progress)),
        show_log_info=bool(loader_ui_raw.get("show_log_info", LoaderUiSettings.show_log_info)),
        show_log_warning=bool(loader_ui_raw.get("show_log_warning", LoaderUiSettings.show_log_warning)),
        show_log_error=bool(loader_ui_raw.get("show_log_error", LoaderUiSettings.show_log_error)),
        show_log_critical=bool(loader_ui_raw.get("show_log_critical", LoaderUiSettings.show_log_critical)),
    )

    shortcut_overrides_raw = data.get("shortcut_overrides", {})
    shortcut_bindings_raw: dict[str, dict[str, str | None]] = {}
    shortcut_gesture_bindings_raw: dict[str, dict[str, str | None]] = {}
    shortcut_consume_overrides_raw: dict[str, dict[str, bool]] = {}
    shortcut_mode_toggle_overrides_raw: dict[str, dict[str, bool]] = {}
    if isinstance(shortcut_overrides_raw, dict):
        raw_bindings = shortcut_overrides_raw.get("bindings", {})
        if isinstance(raw_bindings, dict):
            for plugin_id, per_plugin in raw_bindings.items():
                if not isinstance(plugin_id, str) or not plugin_id.strip():
                    continue
                if not isinstance(per_plugin, dict):
                    continue
                normalized: dict[str, str | None] = {}
                for cmd_id, chord in per_plugin.items():
                    if not isinstance(cmd_id, str) or not cmd_id.strip():
                        continue
                    if chord is None:
                        normalized[cmd_id] = None
                        continue
                    if isinstance(chord, str):
                        chord_s = chord.strip()
                        normalized[cmd_id] = chord_s if chord_s else None
                if normalized:
                    shortcut_bindings_raw[plugin_id] = normalized

        raw_gestures = shortcut_overrides_raw.get("gesture_bindings", {})
        if isinstance(raw_gestures, dict):
            for plugin_id, per_plugin in raw_gestures.items():
                if not isinstance(plugin_id, str) or not plugin_id.strip():
                    continue
                if not isinstance(per_plugin, dict):
                    continue
                normalized: dict[str, str | None] = {}
                for gesture_id, chord in per_plugin.items():
                    if not isinstance(gesture_id, str) or not gesture_id.strip():
                        continue
                    if chord is None:
                        normalized[gesture_id] = None
                        continue
                    if isinstance(chord, str):
                        chord_s = chord.strip()
                        normalized[gesture_id] = chord_s if chord_s else None
                if normalized:
                    shortcut_gesture_bindings_raw[plugin_id] = normalized

        raw_consume = shortcut_overrides_raw.get("consume_event_overrides", {})
        if isinstance(raw_consume, dict):
            for plugin_id, per_plugin in raw_consume.items():
                if not isinstance(plugin_id, str) or not plugin_id.strip():
                    continue
                if not isinstance(per_plugin, dict):
                    continue
                normalized: dict[str, bool] = {}
                for cmd_id, val in per_plugin.items():
                    if not isinstance(cmd_id, str) or not cmd_id.strip():
                        continue
                    if isinstance(val, bool):
                        normalized[cmd_id] = val
                if normalized:
                    shortcut_consume_overrides_raw[plugin_id] = normalized

        raw_modes = shortcut_overrides_raw.get("mode_toggle_overrides", {})
        if isinstance(raw_modes, dict):
            for plugin_id, per_plugin in raw_modes.items():
                if not isinstance(plugin_id, str) or not plugin_id.strip():
                    continue
                if not isinstance(per_plugin, dict):
                    continue
                normalized: dict[str, bool] = {}
                for cmd_id, val in per_plugin.items():
                    if not isinstance(cmd_id, str) or not cmd_id.strip():
                        continue
                    if isinstance(val, bool):
                        normalized[cmd_id] = val
                if normalized:
                    shortcut_mode_toggle_overrides_raw[plugin_id] = normalized

    shortcut_overrides = ShortcutOverrides(
        bindings=shortcut_bindings_raw,
        gesture_bindings=shortcut_gesture_bindings_raw,
        consume_event_overrides=shortcut_consume_overrides_raw,
        mode_toggle_overrides=shortcut_mode_toggle_overrides_raw,
    )

    return AppSettings(
        last_project_root=last_project_root,
        recent_projects=tuple(recent_projects),
        welcome_splitter_state_b64=welcome_splitter_state_b64,
        user_data_dir=user_data_dir,
        enabled_plugins=enabled_plugins,
        loader_ui=loader_ui,
        shortcut_overrides=shortcut_overrides,
        plugin_settings=plugin_settings,
        plugin_overrides=plugin_overrides,
        theme_name=theme_name,
        theme_settings=theme_settings,
        theme_opacity=theme_opacity,
        user_profile=user_profile,
    )


def _settings_to_dict(settings: AppSettings) -> dict[str, Any]:
    payload = asdict(settings)
    payload["last_project_root"] = str(settings.last_project_root) if settings.last_project_root else None
    payload["recent_projects"] = [str(p) for p in settings.recent_projects]
    payload["welcome_splitter_state_b64"] = settings.welcome_splitter_state_b64
    payload["user_data_dir"] = str(settings.user_data_dir) if settings.user_data_dir else None
    payload["enabled_plugins"] = list(settings.enabled_plugins)
    payload["theme_settings"] = asdict(settings.theme_settings)
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
