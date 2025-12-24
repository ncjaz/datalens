from __future__ import annotations

from datalens.domain.plugin import PluginId

_CAPTURE_PLUGIN_SETTINGS_KEY = "capture"
_SETTING_SCAN_MODE = "scan_mode"
_DEFAULT_SCAN_MODE = "manual"  # Start in manual (one-shot) mode
_CAPTURE_PLUGIN_ID = PluginId(_CAPTURE_PLUGIN_SETTINGS_KEY)

_SETTING_STREAM_MODE = "stream_mode"
_DEFAULT_STREAM_MODE = "rgb"

_SETTING_SAVE_FORMATS = "save_formats"
_DEFAULT_SAVE_FORMATS = ("rgb",)

# Depth visualization preferences (user-scoped).
_SETTING_DEPTH_AUTO_SCALE = "depth_auto_scale"
_SETTING_DEPTH_USE_PERCENTILES = "depth_use_percentiles"
_SETTING_DEPTH_PERCENTILE_LOW = "depth_percentile_low"
_SETTING_DEPTH_PERCENTILE_HIGH = "depth_percentile_high"
_SETTING_DEPTH_NEAR_M = "depth_manual_near_m"
_SETTING_DEPTH_FAR_M = "depth_manual_far_m"

_DEFAULT_DEPTH_AUTO_SCALE = True
_DEFAULT_DEPTH_USE_PERCENTILES = True
_DEFAULT_DEPTH_PERCENTILE_LOW = 1.0
_DEFAULT_DEPTH_PERCENTILE_HIGH = 99.0
_DEFAULT_DEPTH_NEAR_M = 0.2
_DEFAULT_DEPTH_FAR_M = 2.0

# Project-scoped settings (stored in ProjectDb plugin_kv).
_PROJECT_OUTPUT_DIR_KEY = "output_dir"

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
    "_DEFAULT_DEPTH_AUTO_SCALE",
    "_DEFAULT_DEPTH_USE_PERCENTILES",
    "_DEFAULT_DEPTH_PERCENTILE_LOW",
    "_DEFAULT_DEPTH_PERCENTILE_HIGH",
    "_DEFAULT_DEPTH_NEAR_M",
    "_DEFAULT_DEPTH_FAR_M",
    "_DEFAULT_SCAN_MODE",
    "_DEFAULT_SAVE_FORMATS",
    "_DEFAULT_STREAM_MODE",
    "_PROJECT_OUTPUT_DIR_KEY",
    "_SETTING_COLORMAP",
    "_SETTING_DEPTH_ALIGNMENT",
    "_SETTING_DEPTH_AUTO_SCALE",
    "_SETTING_DEPTH_USE_PERCENTILES",
    "_SETTING_DEPTH_PERCENTILE_LOW",
    "_SETTING_DEPTH_PERCENTILE_HIGH",
    "_SETTING_DEPTH_NEAR_M",
    "_SETTING_DEPTH_FAR_M",
    "_SETTING_RS_FPS",
    "_SETTING_RS_FORMAT",
    "_SETTING_RS_RESOLUTION",
    "_SETTING_SCAN_MODE",
    "_SETTING_SAVE_FORMATS",
    "_SETTING_STREAM_MODE",
]
