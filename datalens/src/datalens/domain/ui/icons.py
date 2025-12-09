# src/datalens/domain/icons.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class IconRole(str, Enum):
    """
    High-level semantic roles for icons.

    Keep this generic. Concrete tools/tabs (Annotation, Capture, etc.)
    will come from plugins and can define their own icon IDs while
    still mapping into these broad roles.

    UI code maps these roles to actual artwork + colours.
    """

    PRIMARY_ACTION = "primary_action"
    SECONDARY_ACTION = "secondary_action"

    STATUS_INFO = "status_info"
    STATUS_WARNING = "status_warning"
    STATUS_ERROR = "status_error"

    SETTINGS = "settings"
    PLUGINS = "plugins"


@dataclass(frozen=True)
class IconDefinition:
    """
    Domain description of an icon.

    - `id` is a stable identifier used in settings and plugin manifests.
    - `role` is a semantic hint; the UI/theme layer uses this to choose
      colours or variants.
    """

    id: str          # e.g. "core.settings_gear", "myplugin.star_icon"
    role: IconRole
    label: str       # human-readable label (preferences UI, toolpickers)
