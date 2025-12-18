"""
Hold/Toggle shortcut handling (V1-style) for widget-level tools.

This module implements the "Option A" pattern from `review_and_plan/shortcuts_system.md`:

- The shortcuts system (registry + Preferences UI) owns bindings + the user's Hold/Toggle preference.
- Widgets/tools own the lifecycle (press/release/cancel) so we don't steal input globally.

Use cases:
- A canvas that supports a temporary overlay while a key is held (Hold mode).
- The same overlay can be configured to toggle persistently on key press (Toggle mode).

Important:
- This handler only reacts while the target widget (or one of its children) has focus.
- It includes text-input gating so typing into a QLineEdit does not accidentally trigger tools.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from datalens.core.logging import get_logger
from datalens.core.context import get_app_context
from datalens.domain.plugin import PluginId
from datalens.ui.shortcuts.chords import event_to_chord, is_text_input_widget, to_int

log = get_logger(__name__)


class HoldToggleShortcutHandler(QObject):
    """
    Install on a widget to handle a Hold/Toggle command.

    The command must be registered in the shortcuts registry so users can edit the binding
    and select Hold vs Toggle in Preferences.

    The command is expected to be declared with:
    - `ShortcutCommandSpec.mode_toggle_default` set to True/False
    - `ShortcutCommandSpec.dispatch_globally=False` (handled here, not by global dispatch)
    """

    def __init__(
        self,
        widget: QWidget,
        *,
        plugin_id: PluginId,
        command_id: str,
        on_active_changed: Callable[[bool], None],
        allow_in_text_inputs: bool = False,
        consume_event: bool = True,
    ) -> None:
        super().__init__(widget)
        self._widget = widget
        self._plugin_id = plugin_id
        self._command_id = str(command_id)
        self._on_active_changed = on_active_changed
        self._allow_in_text_inputs = bool(allow_in_text_inputs)
        self._consume_event = bool(consume_event)

        self._active = False
        self._hold_key: int | None = None
        self._effective_chord: str | None = None
        self._mode_is_toggle: bool | None = None
        self._app: QApplication | None = None

        self._unsub_changed: Callable[[], None] | None = None
        self._refresh_from_settings()

        app_ctx = get_app_context()
        self._unsub_changed = app_ctx.shortcuts.subscribe_changed(self._refresh_from_settings)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            self._app = app
            app.installEventFilter(self)

    def cleanup(self) -> None:
        """Uninstall and unsubscribe."""
        if self._unsub_changed is not None:
            try:
                self._unsub_changed()
            except Exception:
                pass
            self._unsub_changed = None
        if self._app is not None:
            try:
                self._app.removeEventFilter(self)
            except Exception:
                pass
            self._app = None

    def _refresh_from_settings(self) -> None:
        app_ctx = get_app_context()
        try:
            self._effective_chord = app_ctx.shortcuts.get_effective_command_chord(
                plugin_id=self._plugin_id,
                command_id=self._command_id,
            )
        except Exception:
            self._effective_chord = None
        try:
            self._mode_is_toggle = app_ctx.shortcuts.get_effective_command_mode_toggle(
                plugin_id=self._plugin_id,
                command_id=self._command_id,
            )
        except Exception:
            self._mode_is_toggle = None

        # If the command becomes unbound or loses mode support, ensure we don't stay active.
        if self._mode_is_toggle is None or not self._effective_chord:
            self._end_hold_or_toggle()

    def _focus_within_target(self) -> bool:
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return False
        try:
            focus = app.focusWidget()
        except Exception:
            return False
        if focus is None:
            return False
        current: QWidget | None = focus
        while current is not None:
            if current is self._widget:
                return True
            try:
                current = current.parentWidget()
            except Exception:
                return False
        return False

    def _should_gate_text_input(self) -> bool:
        if self._allow_in_text_inputs:
            return False
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return False
        try:
            focused = app.focusWidget()
        except Exception:
            return False
        return is_text_input_widget(focused)

    def _set_active(self, active: bool) -> None:
        if bool(active) == bool(self._active):
            return
        self._active = bool(active)
        try:
            self._on_active_changed(self._active)
        except Exception:
            pass

    def _end_hold_or_toggle(self) -> None:
        self._hold_key = None
        self._set_active(False)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
        try:
            if not self._focus_within_target():
                if not self._mode_is_toggle and self._active:
                    self._end_hold_or_toggle()
                return False

            try:
                window = self._widget.window()
            except Exception:
                window = None
            if window is not None and not window.isActiveWindow():
                if not self._mode_is_toggle and self._active:
                    self._end_hold_or_toggle()
                return False

            etype = QEvent.Type(event.type())
            if etype == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
                if event.isAutoRepeat():
                    return False
                if self._mode_is_toggle is None:
                    return False
                if self._should_gate_text_input():
                    return False
                chord = event_to_chord(event)
                if chord is None or not self._effective_chord:
                    return False
                if chord != self._effective_chord:
                    return False

                if self._mode_is_toggle:
                    self._set_active(not self._active)
                    if self._consume_event:
                        try:
                            event.accept()
                        except Exception:
                            pass
                        return True
                return False

                # Hold mode
                self._hold_key = to_int(event.key())
                self._set_active(True)
                if self._consume_event:
                    try:
                        event.accept()
                    except Exception:
                        pass
                    return True
                return False

            if etype == QEvent.Type.KeyRelease and isinstance(event, QKeyEvent):
                if event.isAutoRepeat():
                    return False
                if self._mode_is_toggle is None:
                    return False
                if self._mode_is_toggle:
                    return False
                if self._hold_key is None:
                    return False
                if to_int(event.key()) != self._hold_key:
                    return False
                self._end_hold_or_toggle()
                if self._consume_event:
                    try:
                        event.accept()
                    except Exception:
                        pass
                    return True
                return False

            if etype in (QEvent.Type.FocusOut, QEvent.Type.WindowDeactivate, QEvent.Type.Hide):
                if not self._mode_is_toggle and self._active:
                    # Cancel hold if focus leaves the widget/window.
                    self._end_hold_or_toggle()
            return False
        except Exception:
            log.warning(
                "Hold/Toggle event filter failed (best-effort)",
                exc_info=True,
                extra={"operation": "shortcuts", "phase": "hold_toggle_error", "plugin_id": str(self._plugin_id)},
            )
            return False


def attach_hold_toggle_shortcut(
    widget: QWidget,
    *,
    plugin_id: PluginId,
    command_id: str,
    on_active_changed: Callable[[bool], None],
    allow_in_text_inputs: bool = False,
    consume_event: bool = True,
) -> Callable[[], None]:
    """
    Attach a Hold/Toggle shortcut handler to a widget and return a cleanup function.

    This is a convenience wrapper around `HoldToggleShortcutHandler`.
    """
    handler = HoldToggleShortcutHandler(
        widget,
        plugin_id=plugin_id,
        command_id=command_id,
        on_active_changed=on_active_changed,
        allow_in_text_inputs=allow_in_text_inputs,
        consume_event=consume_event,
    )
    try:
        widget.destroyed.connect(lambda *_: handler.cleanup())  # type: ignore[arg-type]
    except Exception:
        pass

    def cleanup() -> None:
        handler.cleanup()

    return cleanup


__all__ = ["HoldToggleShortcutHandler", "attach_hold_toggle_shortcut"]
