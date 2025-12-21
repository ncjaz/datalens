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


def attach_effective_shortcut_tooltip(
    *,
    target: object,
    plugin_id,
    command_id: str,
    title: str,
    description: str | None = None,
    include_shortcut: bool = True,
) -> "Callable[[], None]":
    """
    Attach a live-updating "effective shortcut" tooltip to a Qt object.

    This uses the managed shortcuts service (`ShortcutsService`) as the source of
    truth, so it intentionally does not call `QAction.setShortcut(...)` or create
    a `QShortcut` (prevents double-fire).

    The `target` must provide `setToolTip(str)`. If it also provides a `destroyed`
    signal, the subscription is cleaned up automatically on deletion.

    Returns a cleanup function that unsubscribes from shortcut changes.
    """

    from collections.abc import Callable

    from datalens.core.context import get_app_context
    from datalens.core.logging import get_logger

    log = get_logger(__name__)

    try:
        app_ctx = get_app_context()
        shortcuts = app_ctx.shortcuts
    except Exception:
        log.debug("Shortcut tooltip integration unavailable (no app context)", exc_info=True)

        def noop() -> None:
            return None

        return noop

    def _set_tooltip(text: str) -> None:
        try:
            setter = getattr(target, "setToolTip", None)
            if callable(setter):
                setter(text)
        except Exception:
            log.debug("Failed to set tooltip", exc_info=True)

    def refresh() -> None:
        try:
            chord = shortcuts.get_effective_command_chord(plugin_id=plugin_id, command_id=command_id)
            _set_tooltip(
                tooltip_with_shortcut(
                    title=title,
                    description=description,
                    shortcut=chord if include_shortcut else None,
                )
            )
        except Exception:
            log.debug(
                "Failed to refresh shortcut tooltip",
                exc_info=True,
                extra={"plugin_id": str(plugin_id), "command_id": str(command_id)},
            )

    unsub = shortcuts.subscribe_changed(refresh)
    refresh()

    closed = False

    def cleanup() -> None:
        nonlocal closed
        if closed:
            return
        closed = True
        try:
            unsub()
        except Exception:
            log.debug("Failed to unsubscribe shortcut tooltip refresh", exc_info=True)

    try:
        destroyed = getattr(target, "destroyed", None)
        if destroyed is not None:
            destroyed.connect(lambda *_: cleanup())  # type: ignore[attr-defined]
    except Exception:
        log.debug("Failed to attach destroyed cleanup for shortcut tooltip", exc_info=True)

    return cleanup


__all__ = ["attach_effective_shortcut_tooltip", "tooltip_with_shortcut"]
