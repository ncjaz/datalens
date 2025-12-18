from __future__ import annotations


def tooltip_with_shortcut(
    *,
    title: str,
    shortcut: str | None,
    description: str | None = None,
) -> str:
    """
    Format a tooltip that includes the current shortcut chord (V1-style).

    Keep this ASCII-only so tooltips render consistently across platforms.
    """

    title = (title or "").strip()
    description = (description or "").strip()
    shortcut = (shortcut or "").strip()

    lines: list[str] = []
    if title:
        lines.append(title)
    if description:
        if lines:
            lines.append("")
        lines.append(description)
    if shortcut:
        if lines:
            lines.append("")
        lines.append(f"Shortcut: {shortcut}")
    return "\n".join(lines).strip()


__all__ = ["tooltip_with_shortcut"]

