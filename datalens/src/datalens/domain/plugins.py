from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NewType, Optional

PluginId = NewType("PluginId", str)


class PluginKind(str, Enum):
    """
    UX categories for plugins.

    - TAB: adds a workspace/tab to the main UI.
    - SERVICE: runs logic in the background (e.g., discovery, sync).
    - DATASOURCE: registers new DataSources.
    - MODEL: registers new model families/variants.
    """

    TAB = "tab"
    SERVICE = "service"
    DATASOURCE = "datasource"
    MODEL = "model"


@dataclass(frozen=True)
class PluginFeature:
    """
    A specific feature exposed by a plugin.

    For example, a single plugin might expose:
      - one TAB feature (annotation workspace)
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
    author: Optional[str]
    homepage: Optional[str]
    # Minimal core compatibility string (e.g. '>=2.0.0')
    core_version_constraint: Optional[str]
    features: tuple[PluginFeature, ...]
    enabled_by_default: bool = True
    builtin: bool = False  # True for plugins bundled with the app
