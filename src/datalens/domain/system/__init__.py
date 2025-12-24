from __future__ import annotations

"""
System-level domain types.

These are cross-cutting, app/user scoped schemas that multiple systems use:
- settings/user profile
- lightweight runtime state snapshots (workspace/plugin)
- (planned) shortcut bindings
"""

from .settings import AppSettings
from .shortcuts import (
    ShortcutChord,
    ShortcutCommandId,
    ShortcutCommandSpec,
    ShortcutOverrides,
    ShortcutPageSpec,
    ShortcutScope,
    ShortcutSectionSpec,
)
from .frames import CameraIntrinsics, FrameBundle
from .user_profile import UserProfile
from .system_info import GpuInfo, SystemInfoSnapshot
from .workspace_state import WorkspaceStateSnapshot
from .plugin_state import PluginStateEntry, PluginStateSnapshot

__all__ = [
    "AppSettings",
    "ShortcutChord",
    "ShortcutCommandId",
    "ShortcutCommandSpec",
    "ShortcutOverrides",
    "ShortcutPageSpec",
    "ShortcutScope",
    "ShortcutSectionSpec",
    "CameraIntrinsics",
    "FrameBundle",
    "UserProfile",
    "GpuInfo",
    "SystemInfoSnapshot",
    "WorkspaceStateSnapshot",
    "PluginStateEntry",
    "PluginStateSnapshot",
]
