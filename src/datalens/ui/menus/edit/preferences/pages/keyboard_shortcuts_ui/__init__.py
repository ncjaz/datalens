"""
Keyboard shortcuts preferences UI (helpers).

This package exists to keep `pages/keyboard_shortcuts.py` small and cohesive.

The page itself owns persistence + user feedback (message boxes). The UI build
logic (walking snapshot pages/sections/commands and constructing rows) lives
here so it can be tested/refactored independently.
"""

from .rebuild import rebuild_shortcuts_ui
from .types import BindingKey, RebuildResult

__all__ = ["BindingKey", "RebuildResult", "rebuild_shortcuts_ui"]

