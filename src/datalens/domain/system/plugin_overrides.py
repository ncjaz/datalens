from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PluginDefinitionOverride:
    """
    Per-plugin user/app overrides for manifest-derived metadata.

    This is intentionally not a security boundary: it is a UX/config mechanism.

    Semantics:
    - ``None`` means "no override; use manifest value".
    - For optional fields, an empty string means "clear the manifest value".
    """

    name: str | None = None
    description: str | None = None
    author: str | None = None
    group: str | None = None
    nav_label: str | None = None


__all__ = ["PluginDefinitionOverride"]

