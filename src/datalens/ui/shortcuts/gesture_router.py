from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent
from PySide6.QtGui import QMouseEvent

from datalens.domain.system.shortcuts import GestureBindingSpec, GesturePhase
from datalens.ui.shortcuts.chords import event_to_chord, to_int


GestureCallback = Callable[[GestureBindingSpec, GesturePhase, QEvent], bool]


class GestureRouter:
    """
    Widget-level router for stateful mouse gestures (press/drag/release).

    This is intentionally *not* an application-wide event filter. Widgets opt-in
    by calling these handlers from their `mousePressEvent/mouseMoveEvent/
    mouseReleaseEvent` methods so normal widget input keeps working.
    """

    def __init__(self, *, bindings: tuple[GestureBindingSpec, ...], callback: GestureCallback) -> None:
        self._callback = callback
        self._bindings_by_chord: dict[str, list[GestureBindingSpec]] = {}
        for spec in bindings:
            chord = str(spec.begin_chord) if spec.begin_chord is not None else ""
            chord = chord.strip()
            if not chord:
                continue
            self._bindings_by_chord.setdefault(chord, []).append(spec)

        self._active: GestureBindingSpec | None = None
        self._active_button: int | None = None

    @property
    def active_gesture_id(self) -> str | None:
        return str(self._active.gesture_id) if self._active is not None else None

    def cancel(self, *, event: QEvent | None = None) -> bool:
        active = self._active
        if active is None:
            return False
        self._active = None
        self._active_button = None
        if event is None:
            return False
        handled = bool(self._callback(active, GesturePhase.CANCEL, event))
        return handled and bool(active.consume_event)

    def handle_mouse_press(self, event: QMouseEvent) -> bool:
        if self._active is not None:
            return False

        chord = event_to_chord(event)
        if chord is None:
            return False

        specs = self._bindings_by_chord.get(chord, [])
        for spec in specs:
            handled = bool(self._callback(spec, GesturePhase.BEGIN, event))
            if not handled:
                continue
            self._active = spec
            self._active_button = to_int(event.button())
            return bool(spec.consume_event)
        return False

    def handle_mouse_move(self, event: QMouseEvent) -> bool:
        active = self._active
        if active is None:
            return False
        button = self._active_button or 0
        if button and not (to_int(event.buttons()) & button):
            return False
        handled = bool(self._callback(active, GesturePhase.UPDATE, event))
        return handled and bool(active.consume_event)

    def handle_mouse_release(self, event: QMouseEvent) -> bool:
        active = self._active
        if active is None:
            return False
        button = self._active_button or 0
        if button and to_int(event.button()) != button:
            return False
        self._active = None
        self._active_button = None
        handled = bool(self._callback(active, GesturePhase.END, event))
        return handled and bool(active.consume_event)


__all__ = ["GestureCallback", "GestureRouter"]
