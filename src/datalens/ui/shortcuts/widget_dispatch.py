from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QWidget

from datalens.services.shortcuts.manager import ShortcutDispatchResult, ShortcutsService
from datalens.ui.shortcuts.chords import event_to_chord, is_text_input_widget


def dispatch_shortcut_event(
    *,
    shortcuts: ShortcutsService,
    event: QEvent,
    widget: QWidget,
) -> ShortcutDispatchResult:
    """
    Dispatch a shortcut from within a widget's event handler.

    Use this for canvas/tool widgets that want to support mouse/wheel chords
    without relying on the application-wide event filter (which runs before the
    widget sees the event).
    """

    chord = event_to_chord(event)
    if chord is None:
        return ShortcutDispatchResult(handled=False, consume_event=False)

    window = widget.window()
    if window is not None and not window.isActiveWindow():
        return ShortcutDispatchResult(handled=False, consume_event=False)

    return shortcuts.dispatch(
        chord=chord,
        window=window,
        focused_widget=widget,
        event_is_text_input=is_text_input_widget(widget),
    )


def enable_mouse_wheel_chords(widget: QWidget) -> None:
    """
    Opt a widget (and its subtree) into application-level mouse/wheel chord dispatch.

    This sets `datalens.shortcuts.mouse_chords_enabled = True` on the widget.
    """

    widget.setProperty("datalens.shortcuts.mouse_chords_enabled", True)


__all__ = ["dispatch_shortcut_event", "enable_mouse_wheel_chords"]
