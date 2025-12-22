from __future__ import annotations

from datalens.domain.plugin import PluginId

_CAPTURE_PLUGIN_SETTINGS_KEY = "capture"
_SETTING_SCAN_MODE = "scan_mode"
_DEFAULT_SCAN_MODE = "manual"  # Start in manual (one-shot) mode
_CAPTURE_PLUGIN_ID = PluginId(_CAPTURE_PLUGIN_SETTINGS_KEY)

# Per-device settings keys (stored as "devices/{device_id}/{setting}")
_SETTING_COLORMAP = "colormap"
_SETTING_DEPTH_ALIGNMENT = "depth_alignment"

# RealSense-specific per-device settings
_SETTING_RS_FORMAT = "rs_format"
_SETTING_RS_RESOLUTION = "rs_resolution"
_SETTING_RS_FPS = "rs_fps"

# Default values
_DEFAULT_COLORMAP = "grayscale"
_DEFAULT_DEPTH_ALIGNMENT = "aligned"  # Aligned to RGB by default

__all__ = [
    "_CAPTURE_PLUGIN_ID",
    "_CAPTURE_PLUGIN_SETTINGS_KEY",
    "_DEFAULT_COLORMAP",
    "_DEFAULT_DEPTH_ALIGNMENT",
    "_DEFAULT_SCAN_MODE",
    "_SETTING_COLORMAP",
    "_SETTING_DEPTH_ALIGNMENT",
    "_SETTING_RS_FPS",
    "_SETTING_RS_FORMAT",
    "_SETTING_RS_RESOLUTION",
    "_SETTING_SCAN_MODE",
]

