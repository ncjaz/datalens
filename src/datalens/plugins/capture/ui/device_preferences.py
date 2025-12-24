from __future__ import annotations

from typing import Any

from datalens.core.logging import get_logger

from .workspace_constants import (
    _CAPTURE_PLUGIN_ID,
    _DEFAULT_COLORMAP,
    _DEFAULT_DEPTH_ALIGNMENT,
    _SETTING_COLORMAP,
    _SETTING_DEPTH_ALIGNMENT,
    _SETTING_RS_FPS,
    _SETTING_RS_FORMAT,
    _SETTING_RS_RESOLUTION,
)

log = get_logger(__name__)


def get_device_preference_key(device_id: str, setting: str) -> str:
    """
    Generate a preference key for a specific device and setting.

    Format: "devices/{device_id}/{setting}"

    Args:
        device_id: Unique device identifier (e.g., RealSense serial number)
        setting: Setting name (e.g., "colormap", "rs_format")

    Returns:
        Formatted preference key
    """
    return f"devices/{device_id}/{setting}"


def save_device_preference(self, device_id: str, setting: str, value: Any) -> None:
    """
    Save a device-specific preference.

    Args:
        device_id: Unique device identifier
        setting: Setting name
        value: Setting value
    """
    try:
        key = get_device_preference_key(device_id, setting)
        self._app_ctx.preferences.set(_CAPTURE_PLUGIN_ID, key, value)
        log.debug(
            f"Saved device preference: {setting}={value}",
            extra={
                "operation": "capture",
                "phase": "save_device_pref",
                "device_id": device_id,
                "setting": setting,
            },
        )
    except Exception:
        log.warning(
            f"Failed to save device preference: {setting}",
            exc_info=True,
            extra={
                "operation": "capture",
                "phase": "save_device_pref_error",
                "device_id": device_id,
                "setting": setting,
            },
        )


def load_device_preference(self, device_id: str, setting: str, default: Any = None) -> Any:
    """
    Load a device-specific preference.

    Args:
        device_id: Unique device identifier
        setting: Setting name
        default: Default value if preference not found

    Returns:
        Preference value or default
    """
    try:
        key = get_device_preference_key(device_id, setting)
        value = self._app_ctx.preferences.get(_CAPTURE_PLUGIN_ID, key, default=default)
        log.debug(
            f"Loaded device preference: {setting}={value}",
            extra={
                "operation": "capture",
                "phase": "load_device_pref",
                "device_id": device_id,
                "setting": setting,
            },
        )
        return value
    except Exception:
        log.debug(
            f"Failed to load device preference: {setting}, using default",
            exc_info=True,
            extra={
                "operation": "capture",
                "phase": "load_device_pref_error",
                "device_id": device_id,
                "setting": setting,
            },
        )
        return default


def save_colormap_preference(self, device_id: str, colormap: str) -> None:
    """Save colormap preference for a specific device."""
    save_device_preference(self, device_id, _SETTING_COLORMAP, colormap)


def load_colormap_preference(self, device_id: str) -> str:
    """Load colormap preference for a specific device."""
    return str(load_device_preference(self, device_id, _SETTING_COLORMAP, _DEFAULT_COLORMAP))


def save_depth_alignment_preference(self, device_id: str, alignment: str) -> None:
    """Save depth alignment preference for a specific device."""
    save_device_preference(self, device_id, _SETTING_DEPTH_ALIGNMENT, alignment)


def load_depth_alignment_preference(self, device_id: str) -> str:
    """Load depth alignment preference for a specific device."""
    return str(load_device_preference(self, device_id, _SETTING_DEPTH_ALIGNMENT, _DEFAULT_DEPTH_ALIGNMENT))


def save_realsense_profile_preference(self, device_id: str, format_str: str, width: int, height: int, fps: int) -> None:
    """
    Save RealSense profile preferences for a specific device.

    Args:
        device_id: RealSense serial number
        format_str: Format (e.g., "RGB8", "YUYV")
        width: Resolution width
        height: Resolution height
        fps: Frame rate
    """
    save_device_preference(self, device_id, _SETTING_RS_FORMAT, format_str)
    save_device_preference(self, device_id, _SETTING_RS_RESOLUTION, f"{width}x{height}")
    save_device_preference(self, device_id, _SETTING_RS_FPS, fps)


def load_realsense_profile_preference(self, device_id: str) -> tuple[str | None, tuple[int, int] | None, int | None]:
    """
    Load RealSense profile preferences for a specific device.

    Args:
        device_id: RealSense serial number

    Returns:
        Tuple of (format, (width, height), fps) or (None, None, None) if not found
    """
    format_str = load_device_preference(self, device_id, _SETTING_RS_FORMAT, default=None)
    resolution_str = load_device_preference(self, device_id, _SETTING_RS_RESOLUTION, default=None)
    fps = load_device_preference(self, device_id, _SETTING_RS_FPS, default=None)

    # Parse resolution string (e.g., "1920x1080")
    resolution = None
    if resolution_str:
        try:
            parts = str(resolution_str).split("x")
            if len(parts) == 2:
                resolution = (int(parts[0]), int(parts[1]))
        except Exception:
            log.debug(
                f"Failed to parse resolution: {resolution_str}",
                exc_info=True,
                extra={"operation": "capture", "phase": "parse_resolution_pref"},
            )

    return (format_str, resolution, fps)


__all__ = [
    "get_device_preference_key",
    "load_colormap_preference",
    "load_depth_alignment_preference",
    "load_device_preference",
    "load_realsense_profile_preference",
    "save_colormap_preference",
    "save_depth_alignment_preference",
    "save_device_preference",
    "save_realsense_profile_preference",
]
