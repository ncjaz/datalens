from __future__ import annotations

from datalens.core.context import AppContext, get_app_context


def try_get_app_context() -> AppContext | None:
    """
    Best-effort AppContext accessor.

    `datalens.core.context.get_app_context()` raises when no running Qt app exists.
    UI code often wants a "None means unavailable" API for best-effort updates.
    """
    try:
        return get_app_context()
    except Exception:
        return None


__all__ = ["try_get_app_context"]

