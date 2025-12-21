from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget

from datalens.core.logging import get_logger
from datalens.services.shortcuts.manager import ShortcutsService
from datalens.ui.shortcuts.chords import event_to_chord, is_text_input_widget

log = get_logger(__name__)


class ShortcutsEventFilter(QObject):
    """
    Application-level event filter that routes input chords to ShortcutsService.

    This filter is intentionally small: it only converts Qt events -> chord
    strings and asks the shortcuts service to dispatch.
    """

    def __init__(self, shortcuts: ShortcutsService) -> None:
        super().__init__()
        self._shortcuts = shortcuts

    @staticmethod
    def _mouse_chords_enabled(widget: QWidget | None) -> bool:
        """
        Global mouse/wheel chords are opt-in.

        Rationale: an application-wide event filter runs *before* widgets see
        input. If we dispatch mouse chords globally, we can easily interfere
        with normal widget interactions (dragging, scrolling, painting tools).

        Widgets (or their parent chain) can opt-in by setting:
        - `datalens.shortcuts.mouse_chords_enabled` = True

        This should typically be set on a canvas/tool widget, not globally.
        """

        if widget is None:
            return False

        key = "datalens.shortcuts.mouse_chords_enabled"
        current: QWidget | None = widget
        while current is not None:
            try:
                if bool(current.property(key)):
                    return True
            except Exception:
                pass
            current = current.parentWidget()
        try:
            window = widget.window()
            if window is not None and bool(window.property(key)):
                return True
        except Exception:
            pass
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
        try:
            app = QApplication.instance()
            if app is not None:
                try:
                    if bool(app.property("datalens.shortcuts.capture_active")):
                        return False
                except Exception:
                    pass

            etype = QEvent.Type(event.type())
            if etype not in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
                return False

            chord = event_to_chord(event)
            if chord is None:
                return False

            widget = watched if isinstance(watched, QWidget) else None
            if etype == QEvent.Type.KeyPress and app is not None:
                # Key events can bubble up the widget hierarchy when the focus widget doesn't
                # accept them. Because this event filter is installed at the application level,
                # we'd see the *same* physical key press multiple times (for the focus widget,
                # then its parents). To avoid double-dispatch, only dispatch once for the
                # current focus widget (or the first receiver if there's no focus widget).
                try:
                    focused = app.focusWidget()
                    if focused is not None:
                        if watched is not focused:
                            return False
                        widget = focused
                except Exception:
                    pass
            window = widget.window() if widget is not None else None
            if window is not None and not window.isActiveWindow():
                return False

            if etype in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel) and not self._mouse_chords_enabled(widget):
                return False

            is_text = is_text_input_widget(widget)
            result = self._shortcuts.dispatch(
                chord=chord,
                window=window,
                focused_widget=widget,
                event_is_text_input=is_text,
            )
            if not result.handled:
                return False
            if not result.consume_event:
                return False
            try:
                event.accept()
            except Exception:
                pass
            return True
        except Exception:
            # Never allow exceptions to escape a Qt event filter: they can destabilize
            # input delivery and may terminate the process depending on the platform.
            try:
                etype = QEvent.Type(event.type()).name
            except Exception:
                etype = str(int(event.type()))
            log.warning(
                "Shortcuts event filter failed (best-effort)",
                exc_info=True,
                extra={"operation": "shortcuts", "phase": "event_filter_error", "event_type": etype},
            )
            return False


__all__ = ["ShortcutsEventFilter"]
