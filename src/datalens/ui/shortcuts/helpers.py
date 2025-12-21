"""
Shortcut helper utilities for plugin/widget UI code.

These helpers exist to reduce boilerplate for common integration points:

- Opting a widget subtree into global mouse/wheel chord dispatch
  (`datalens.shortcuts.mouse_chords_enabled` property).
- Tagging a popout window with a plugin id so workspace-scoped shortcuts route
  correctly when multiple top-level windows exist.
- Subscribing to shortcut changes to refresh tooltips or UI labels.
- Wiring `DatalensButton` instances to already-registered `ShortcutButtonBinding` objects.

The shortcuts *source of truth* remains `ShortcutsService` in the app context.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QWidget

from datalens.core.context import get_app_context
from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId


log = get_logger(__name__)


def enable_mouse_wheel_chords(widget: QWidget) -> None:
    """
    Opt a widget subtree into global mouse/wheel chord dispatch.

    The application-wide shortcuts event filter will only dispatch mouse/wheel chords
    if the focused widget (or its parent chain) has the Qt property:
    `datalens.shortcuts.mouse_chords_enabled = True`.
    """

    widget.setProperty("datalens.shortcuts.mouse_chords_enabled", True)


def attach_shortcut_integration(
    widget: QWidget,
    *,
    plugin_id: PluginId | None = None,
    tag_window: bool = False,
    enable_mouse_wheel: bool = False,
    on_shortcuts_changed: Callable[[], None] | None = None,
) -> Callable[[], None]:
    """
    Attach common shortcuts integration to a widget and return a cleanup function.

    Args:
        widget: Root widget for the integration.
        plugin_id: If provided and `tag_window=True`, tags the widget's top-level
            window with this plugin id (intended for plugin popout windows).
        tag_window: Whether to tag the top-level window for workspace-scoped
            routing. Do not enable this for widgets embedded in the main window.
        enable_mouse_wheel: Whether to enable global mouse/wheel chord dispatch
            for this widget subtree.
        on_shortcuts_changed: Optional callback to refresh UI (tooltips/labels).
            Delivered on the Qt event loop via
            `ShortcutsService.subscribe_changed(...)`.

    Cleanup:
    - Removes the internal event filter and unsubscribes from shortcut changes.
    """

    if enable_mouse_wheel:
        enable_mouse_wheel_chords(widget)

    app_ctx = get_app_context()
    unsub: Callable[[], None] | None = None
    if on_shortcuts_changed is not None:
        unsub = app_ctx.shortcuts.subscribe_changed(on_shortcuts_changed)

    class _WindowTagger(QObject):
        def __init__(self) -> None:
            super().__init__(widget)
            self._tagged = False

        def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
            if self._tagged:
                return False
            etype = QEvent.Type(event.type())
            if etype not in (QEvent.Type.Show, QEvent.Type.ParentChange, QEvent.Type.Polish):
                return False
            _try_tag()
            return False

    def _try_tag() -> None:
        nonlocal tagger
        if not tag_window or plugin_id is None:
            return
        if tagger is None or getattr(tagger, "_tagged", False):
            return
        try:
            window = widget.window()
            if window is None:
                return
            app_ctx.shortcuts.tag_window_with_plugin(window, plugin_id)
            tagger._tagged = True  # type: ignore[attr-defined]
        except Exception:
            pass

    tagger: _WindowTagger | None = None
    if tag_window and plugin_id is not None:
        tagger = _WindowTagger()
        widget.installEventFilter(tagger)
        QTimer.singleShot(0, _try_tag)

    def cleanup() -> None:
        nonlocal tagger, unsub
        if tagger is not None:
            try:
                widget.removeEventFilter(tagger)
            except Exception:
                pass
            tagger = None
        if unsub is not None:
            try:
                unsub()
            except Exception:
                pass
            unsub = None

    try:
        widget.destroyed.connect(lambda *_: cleanup())  # type: ignore[arg-type]
    except Exception:
        pass

    return cleanup


def wire_button_to_binding(
    button,
    *,
    binding,
    plugin_id: PluginId,
) -> None:
    """
    Wire a `DatalensButton` to an already-registered `ShortcutButtonBinding`.

    This is a UI-layer convenience helper that connects the button's `clicked`
    signal to the binding's callback and attaches the effective shortcut tooltip.

    **Important**: The shortcut must already be registered via
    `register_shortcuts()` before calling this. This helper assumes registration
    happened in the plugin's `register_shortcuts(ctx)` hook.

    Args:
        button: A `DatalensButton` instance (created by caller).
        binding: A `ShortcutButtonBinding` that was registered during
            `register_shortcuts()` (typically stored on the plugin instance).
        plugin_id: The plugin id that owns the shortcut command.

    Example:
        In plugin `__init__()`:
            self._save_binding = ShortcutButtonBinding(...)

        In `register_shortcuts()`:
            register_shortcut_page_for_buttons(ctx, bindings=[self._save_binding])

        In workspace UI:
            btn = DatalensButton("Save", ctx.app.theme, ButtonVariant.PRIMARY)
            wire_button_to_binding(btn, binding=plugin.save_binding, plugin_id=plugin.plugin_id)

    This reduces the workspace UI code to 2 lines instead of 3-4 lines of manual wiring.
    """

    from datalens.api.ui_commands import ShortcutButtonBinding

    if not isinstance(binding, ShortcutButtonBinding):
        log.warning(
            "wire_button_to_binding expects a ShortcutButtonBinding, got %s",
            type(binding).__name__,
            extra={"operation": "shortcuts", "phase": "wire_button"},
        )
        return

    try:
        button.clicked.connect(lambda *_: binding.callback())
    except Exception:
        log.warning(
            "Failed to connect button click to binding callback",
            exc_info=True,
            extra={"operation": "shortcuts", "phase": "wire_button"},
        )

    try:
        button.attach_shortcut_tooltip(
            plugin_id=plugin_id,
            command_id=str(binding.command.command_id),
            title=binding.command.title,
            description=binding.command.description,
        )
    except Exception:
        log.debug(
            "Failed to attach shortcut tooltip to button (best-effort)",
            exc_info=True,
            extra={"operation": "shortcuts", "phase": "wire_button"},
        )


__all__ = [
    "attach_shortcut_integration",
    "enable_mouse_wheel_chords",
    "wire_button_to_binding",
]
