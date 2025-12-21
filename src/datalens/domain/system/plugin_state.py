from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from datalens.domain.plugin import PluginId


@dataclass(frozen=True)
class PluginStateEntry:
    key: str
    value: Any
    updated_at_monotonic: float


@dataclass(frozen=True)
class PluginStateSnapshot:
    """
    Read-only snapshot of all registered plugin state.

    Data is grouped by plugin id, then by key.
    """

    entries: dict[PluginId, dict[str, PluginStateEntry]]


__all__ = ["PluginStateEntry", "PluginStateSnapshot"]
