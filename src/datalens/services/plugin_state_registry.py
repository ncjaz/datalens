from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from datalens.domain.plugin import PluginId
from datalens.domain.system.plugin_state import PluginStateEntry, PluginStateSnapshot


class PluginStateError(RuntimeError):
    pass


PluginStateListener = Callable[[PluginId, str], None]


@dataclass(frozen=True)
class PluginStateHandle:
    """
    Convenience wrapper for a single plugin's namespace.

    Plugins should use this instead of calling the registry with arbitrary
    plugin ids.
    """

    registry: "PluginStateRegistry"
    plugin_id: PluginId

    def set(self, key: str, value: Any) -> None:
        self.registry.set(plugin_id=self.plugin_id, key=key, value=value)

    def get(self, key: str) -> Any | None:
        return self.registry.get(plugin_id=self.plugin_id, key=key)

    def list(self) -> dict[str, PluginStateEntry]:
        return self.registry.list(plugin_id=self.plugin_id)


class PluginStateRegistry:
    """
    Namespaced, in-memory state registry for plugins (lightweight).

    This is not a persistence mechanism; it is a queryable "what is current
    state right now?" surface for debugging and late joiners.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
        self._state: dict[PluginId, dict[str, PluginStateEntry]] = {}
        self._listeners: list[PluginStateListener] = []

    def version(self) -> int:
        with self._lock:
            return self._version

    def handle_for(self, plugin_id: PluginId) -> PluginStateHandle:
        return PluginStateHandle(registry=self, plugin_id=plugin_id)

    def set(self, *, plugin_id: PluginId, key: str, value: Any) -> None:
        k = str(key).strip()
        if not k:
            raise PluginStateError("State key must be non-empty.")
        # Enforce JSON-serializable payloads so the inspector can always render them.
        try:
            json.dumps(value)
        except Exception as exc:
            raise PluginStateError(f"State value for {plugin_id}/{k} is not JSON-serializable: {exc}") from exc

        listeners: list[PluginStateListener]
        with self._lock:
            bucket = self._state.setdefault(plugin_id, {})
            bucket[k] = PluginStateEntry(key=k, value=value, updated_at_monotonic=time.monotonic())
            self._version += 1
            listeners = list(self._listeners)

        for fn in listeners:
            try:
                fn(plugin_id, k)
            except Exception:
                continue

    def get(self, *, plugin_id: PluginId, key: str) -> Any | None:
        with self._lock:
            entry = self._state.get(plugin_id, {}).get(str(key))
            return entry.value if entry is not None else None

    def list(self, *, plugin_id: PluginId) -> dict[str, PluginStateEntry]:
        with self._lock:
            return dict(self._state.get(plugin_id, {}))

    def snapshot(self) -> PluginStateSnapshot:
        with self._lock:
            data = {pid: dict(entries) for pid, entries in self._state.items()}
        return PluginStateSnapshot(entries=data)

    def subscribe(self, listener: PluginStateListener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._listeners.remove(listener)
                except ValueError:
                    pass

        return unsubscribe
