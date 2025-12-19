from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId

log = get_logger(__name__)

CapabilityId = str


@dataclass(frozen=True)
class CapabilityProvider:
    """
    A registered capability provider.

    Capabilities are the primary "plugin-to-plugin sharing" mechanism in V2:
    - plugins should not import each other or reach into each other's DB tables directly
    - instead, plugins register stable providers under a shared capability id
    - consumers look up providers via the AppContext registry

    This is not a security boundary; it is a coordination mechanism.
    """

    capability_id: CapabilityId
    provider: object
    owner_plugin_id: PluginId | None = None
    priority: int = 0
    description: str = ""


class CapabilitiesRegistry:
    """
    In-memory registry of capability providers.

    - Supports multiple providers per capability id.
    - Provider selection uses highest `priority` first.
    - Intended for stable cross-plugin integration (providers + consumers).
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._providers: dict[CapabilityId, list[CapabilityProvider]] = {}

    def register(self, provider: CapabilityProvider, *, replace_owner: bool = False) -> None:
        cid = str(provider.capability_id).strip()
        if not cid:
            raise ValueError("capability_id must be a non-empty string")

        with self._lock:
            items = list(self._providers.get(cid, ()))
            if replace_owner and provider.owner_plugin_id is not None:
                items = [p for p in items if p.owner_plugin_id != provider.owner_plugin_id]
            items.append(provider)
            items.sort(key=lambda p: int(p.priority), reverse=True)
            self._providers[cid] = items

        log.debug(
            "Capability registered",
            extra={
                "operation": "capabilities",
                "phase": "register",
                "capability_id": cid,
                "owner_plugin_id": str(provider.owner_plugin_id) if provider.owner_plugin_id else None,
                "priority": int(provider.priority),
            },
        )

    def unregister_owner(self, owner_plugin_id: PluginId) -> None:
        owner = PluginId(str(owner_plugin_id))
        with self._lock:
            for cid, items in list(self._providers.items()):
                kept = [p for p in items if p.owner_plugin_id != owner]
                if kept:
                    self._providers[cid] = kept
                else:
                    self._providers.pop(cid, None)

        log.debug(
            "Capability providers removed for plugin",
            extra={"operation": "capabilities", "phase": "unregister_owner", "owner_plugin_id": str(owner)},
        )

    def get_providers(self, capability_id: CapabilityId) -> tuple[CapabilityProvider, ...]:
        cid = str(capability_id).strip()
        with self._lock:
            return tuple(self._providers.get(cid, ()))

    def get_provider(self, capability_id: CapabilityId) -> CapabilityProvider | None:
        providers = self.get_providers(capability_id)
        return providers[0] if providers else None

    def get(self, capability_id: CapabilityId) -> object | None:
        """
        Return the selected provider object for `capability_id` (highest priority).
        """
        p = self.get_provider(capability_id)
        return p.provider if p is not None else None

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        """
        Return a JSON-serializable snapshot for debugging/inspection UIs.
        """
        with self._lock:
            out: dict[str, list[dict[str, Any]]] = {}
            for cid, items in self._providers.items():
                out[cid] = [
                    {
                        "capability_id": str(p.capability_id),
                        "owner_plugin_id": str(p.owner_plugin_id) if p.owner_plugin_id else None,
                        "priority": int(p.priority),
                        "description": str(p.description or ""),
                        "provider_type": type(p.provider).__name__,
                    }
                    for p in items
                ]
            return out


__all__ = ["CapabilitiesRegistry", "CapabilityId", "CapabilityProvider"]

