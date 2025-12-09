from __future__ import annotations

"""
Domain types that are UI-related but still pure data:
- icons (semantic roles + IDs)
- theme settings (colours etc.)

The actual Qt theme / icon rendering lives in the ui/ package, not here.
"""

from .icons import IconRole, IconDefinition
from .theme import ThemeSettings, DEFAULT_THEME

__all__ = [
    "IconRole",
    "IconDefinition",
    "ThemeSettings",
    "DEFAULT_THEME",
]
