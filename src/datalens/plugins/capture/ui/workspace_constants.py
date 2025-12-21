from __future__ import annotations

from datalens.domain.plugin import PluginId

_CAPTURE_PLUGIN_SETTINGS_KEY = "capture"
_SETTING_SCAN_MODE = "scan_mode"
_DEFAULT_SCAN_MODE = "manual"  # Start in manual (one-shot) mode
_CAPTURE_PLUGIN_ID = PluginId(_CAPTURE_PLUGIN_SETTINGS_KEY)

__all__ = [
    "_CAPTURE_PLUGIN_ID",
    "_CAPTURE_PLUGIN_SETTINGS_KEY",
    "_DEFAULT_SCAN_MODE",
    "_SETTING_SCAN_MODE",
]

