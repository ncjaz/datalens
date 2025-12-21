from __future__ import annotations

"""
Toast notification types and data structures.

Defines the type system for toast notifications including icon types,
positioning options, and toast parameters.
"""

from dataclasses import dataclass
from enum import Enum


class ToastIconType(Enum):
    """Type of toast notification icon."""

    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"


class ToastPosition(Enum):
    """Position of toast notifications on screen."""

    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    CENTER_LEFT = "center_left"
    CENTER = "center"
    CENTER_RIGHT = "center_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"


@dataclass
class ToastParams:
    """
    Parameters for creating a toast notification.

    This dataclass is used to queue toast requests and pass parameters
    between the manager and widget layers.
    """

    title: str
    message: str = ""
    icon_type: ToastIconType = ToastIconType.INFO
    duration: int = 5000  # milliseconds, 0 = no auto-dismiss
    position: ToastPosition = ToastPosition.BOTTOM_RIGHT
    trigger: str = "direct_call"  # direct_call, event_hub, signal
    caller_module: str | None = None


__all__ = [
    "ToastIconType",
    "ToastPosition",
    "ToastParams",
]
