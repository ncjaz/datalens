from __future__ import annotations

"""
Plugin domain types.

This package defines the manifest-backed plugin metadata and IDs used by:
- the plugin loader/registry
- the welcome screen UI
- runtime/plugin lifecycle systems
"""

from dataclasses import dataclass
from enum import Enum
from typing import NewType, Optional

from datalens.domain.plugin.preferences_schema import PluginPreferencesSchema

PluginId = NewType("PluginId", str)
PluginGroupId = NewType("PluginGroupId", str)


class PluginKind(str, Enum):
    """
    UX categories for plugins.

    - WORKSPACE: adds a user-facing workspace to the main UI.
    - SERVICE: runs logic in the background (e.g., discovery, sync).
    - DATASOURCE: registers new DataSources.
    - MODEL: registers new model families/variants.
    """

    WORKSPACE = "workspace"
    SERVICE = "service"
    DATASOURCE = "datasource"
    MODEL = "model"


class PluginStage(str, Enum):
    """
    Maturity level for a plugin.

    This is primarily a UX hint for the welcome screen / plugin manager so
    users can distinguish experimental plugins from stable ones.
    """

    DEV = "dev"
    ALPHA = "alpha"
    BETA = "beta"
    RELEASE = "release"


@dataclass(frozen=True)
class PluginFeature:
    """
    A specific feature exposed by a plugin.

    For example, a single plugin might expose:
      - one WORKSPACE feature (annotation workspace)
      - one SERVICE feature (background sync)
    """

    id: str  # stable, unique within a plugin
    kind: PluginKind
    entrypoint: str  # 'module.path:ClassName' or a hook identifier
    display_name: str
    description: str


@dataclass(frozen=True)
class PluginDefinition:
    """
    Plugin metadata used by the loader, registry, and welcome UI.

    This is normally populated from a plugin manifest file plus a
    small bit of introspection.
    """

    id: PluginId
    name: str
    version: str
    description: str
    features: tuple[PluginFeature, ...]
    stage: PluginStage = PluginStage.RELEASE
    author: Optional[str] = None
    homepage: Optional[str] = None
    # Minimal core compatibility string (e.g. '>=2.0.0')
    core_version_constraint: Optional[str] = None
    # Optional grouping label used by the welcome UI to present related plugins
    # together (e.g. "Data annotation" for annotation + review).
    group: Optional[PluginGroupId] = None
    # Optional 1-2 letter identifier for compact navigation UIs (sidebar).
    nav_label: Optional[str] = None
    # Optional plugin-provided icon path for navigation UIs (relative to plugin root).
    nav_icon: Optional[str] = None
    # Names of Python packages that must be installed manually by the user even
    # if the plugin ships a requirements.txt (e.g. torch with OS/CUDA-specific
    # wheels). The welcome UI can surface these as "manual install" blockers.
    manual_pip_requirements: tuple[str, ...] = ()
    enabled_by_default: bool = True
    builtin: bool = False  # True for plugins bundled with the app
    # Optional preferences schema (manifest-driven). Used by Preferences UI to
    # build pages without importing plugin runtime code.
    preferences: PluginPreferencesSchema | None = None


__all__ = [
    "PluginId",
    "PluginGroupId",
    "PluginDefinition",
    "PluginFeature",
    "PluginKind",
    "PluginStage",
    "PluginPreferencesSchema",
]

# Optional: plugin metadata stored in the core-owned `plugin_meta` table.
from .meta import PluginMeta  # noqa: E402

__all__.append("PluginMeta")
