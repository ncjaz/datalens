from __future__ import annotations

"""
Domain layer public API.

This module re-exports the core domain types that plugins and UI code
are expected to use. Keep this surface small and stable; it forms the
contract between the core app and extensions.
"""

from .projects import ProjectId, ProjectSummary
from .media import MediaId, MediaItemSummary, MediaType
from .annotations.core import AnnotationId, AnnotationSet
from .models.base import ModelFamilyId, ModelVariantId, ModelCapability
from .plugin import PluginId, PluginGroupId, PluginDefinition, PluginFeature, PluginKind
from .datasources import DataSourceId, DataSource, DataSourceKind
from .user_profile import UserProfile
from .ui.icons import IconRole, IconDefinition
from .ui.theme import ThemeSettings, DEFAULT_THEME

__all__ = [
    # Projects
    "ProjectId",
    "ProjectSummary",
    # Media
    "MediaId",
    "MediaItemSummary",
    "MediaType",
    # Annotations
    "AnnotationId",
    "AnnotationSet",
    # Models
    "ModelFamilyId",
    "ModelVariantId",
    "ModelCapability",
    # Plugins
    "PluginId",
    "PluginGroupId",
    "PluginDefinition",
    "PluginFeature",
    "PluginKind",
    # Data sources
    "DataSourceId",
    "DataSource",
    "DataSourceKind",
    # User profile
    "UserProfile",
    # UI domain
    "IconRole",
    "IconDefinition",
    "ThemeSettings",
    "DEFAULT_THEME",
]
