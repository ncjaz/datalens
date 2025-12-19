"""
Plugin-facing public API (V2).

Use this module as the preferred import surface when writing plugins.

Principles:
- Non-blocking UI: do not block the Qt UI thread on I/O/CPU.
- No plugin-to-plugin imports: share via Events/Capabilities/Commands.
- Project lifecycle is owned by core: plugins *react* via hooks/events.
"""

from __future__ import annotations

from datalens.core.logging import get_logger
from datalens.domain.plugin import (
    PluginDefinition,
    PluginId,
    PluginKind,
    PluginStage,
)
from datalens.services.db.plugin_db import PluginDb
from datalens.services.db.plugin_migrations import PluginMigration, PluginMigrationError, run_plugin_migrations
from datalens.services.background_io.writer import IoWriter
from datalens.services.capabilities import CapabilityId, CapabilityProvider
from datalens.services.commands import CommandBus, CommandContext, CommandId, RegisteredHandler
from datalens.domain.system.shortcuts import (
    GestureBindingSpec,
    GestureId,
    GesturePhase,
    ShortcutChord,
    ShortcutCommandId,
    ShortcutCommandSpec,
    ShortcutPageSpec,
    ShortcutScope,
    ShortcutSectionSpec,
)
from datalens.services.plugins.runtime.contracts import (
    BasePlugin,
    PluginAppContext,
    PluginFutureResult,
    PluginProjectContext,
    ProjectAwarePlugin,
    SupportsShortcuts,
)
from datalens.core.events import (
    ActiveProjectChanged,
    EventHub,
    FocusedWorkspaceChanged,
    PluginDefinitionsChanged,
    PluginDisabled,
    PluginEnabled,
    PluginsEnabledChanged,
    ProjectClosed,
    ProjectClosing,
    ProjectOpenFailed,
    ProjectOpened,
    Subscription,
)
from datalens.api.sharing import (
    CAP_ANNOTATIONS_CURRENT,
    CAP_MEDIA_CURRENT,
    CAP_PROJECT_STATUS,
    CAP_WORKSPACE_STATE_SNAPSHOT,
    CMD_PROJECT_CLOSE,
    CMD_PROJECT_OPEN,
    CMD_WORKSPACE_FOCUS,
)

__all__ = [
    # Logging
    "get_logger",
    # Domain identifiers / metadata
    "PluginDefinition",
    "PluginId",
    "PluginKind",
    "PluginStage",
    # Persistence helpers
    "PluginDb",
    "PluginMigration",
    "PluginMigrationError",
    "run_plugin_migrations",
    "IoWriter",
    # Capabilities + commands (sharing contracts)
    "CapabilityId",
    "CapabilityProvider",
    "CommandBus",
    "CommandContext",
    "CommandId",
    "RegisteredHandler",
    # Event hub (semantic coordination)
    "EventHub",
    "Subscription",
    "ProjectOpened",
    "ProjectClosing",
    "ProjectClosed",
    "ProjectOpenFailed",
    "ActiveProjectChanged",
    "PluginEnabled",
    "PluginDisabled",
    "PluginsEnabledChanged",
    "FocusedWorkspaceChanged",
    "PluginDefinitionsChanged",
    # Canonical sharing ids (convergence point)
    "CAP_WORKSPACE_STATE_SNAPSHOT",
    "CAP_PROJECT_STATUS",
    "CAP_MEDIA_CURRENT",
    "CAP_ANNOTATIONS_CURRENT",
    "CMD_PROJECT_OPEN",
    "CMD_PROJECT_CLOSE",
    "CMD_WORKSPACE_FOCUS",
    # Shortcuts (domain contracts; used for plugin shortcut pages)
    "GestureBindingSpec",
    "GestureId",
    "GesturePhase",
    "ShortcutChord",
    "ShortcutCommandId",
    "ShortcutCommandSpec",
    "ShortcutPageSpec",
    "ShortcutScope",
    "ShortcutSectionSpec",
    # Runtime hook contracts
    "BasePlugin",
    "PluginAppContext",
    "PluginProjectContext",
    "PluginFutureResult",
    "ProjectAwarePlugin",
    "SupportsShortcuts",
]
