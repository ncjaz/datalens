from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QWidget

from datalens.ui.shortcuts.chords import event_to_chord, to_int


class _CaptureNextChordFilter(QObject):
    def __init__(self, *, on_captured: Callable[[str | None], None]) -> None:
        super().__init__()
        self._on_captured = on_captured

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
        etype = QEvent.Type(event.type())
        if etype not in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
            return False

        if etype == QEvent.Type.KeyPress:
            try:
                if to_int(getattr(event, "key")()) == to_int(Qt.Key_Escape):
                    self._on_captured(None)
                    return True
            except Exception:
                pass

        chord = event_to_chord(event)
        if chord is None:
            return False
        self._on_captured(chord)
        return True


class ShortcutBindingEditor(QWidget):
    """
    Simple chord editor for the Preferences -> Keyboard Shortcuts page.

    - "Record..." captures the next key/mouse/wheel chord.
    - "Clear" unbinds.
    - Esc cancels a recording.
    """

    chordChanged = Signal(object)  # str | None
    resetRequested = Signal()
    recordingChanged = Signal(bool)

    def __init__(
        self,
        *,
        initial: str | None = None,
        show_reset: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._capture_filter: _CaptureNextChordFilter | None = None
        self._recording = False
        self._chord: str | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # V1-style compact binding UI: a single button shows the current chord and
        # is clicked to (re)bind. This avoids a wide, read-only text field.
        self._bind_btn = QPushButton(self)
        self._bind_btn.setMinimumWidth(120)
        self._bind_btn.clicked.connect(self._toggle_record)  # type: ignore[arg-type]
        layout.addWidget(self._bind_btn, 0)

        self._clear_btn = QPushButton("Clear", self)
        self._clear_btn.clicked.connect(self._clear)  # type: ignore[arg-type]
        layout.addWidget(self._clear_btn, 0)

        self._reset_btn: QPushButton | None = None
        if show_reset:
            self._reset_btn = QPushButton("Reset", self)
            self._reset_btn.clicked.connect(lambda *_: self.resetRequested.emit())  # type: ignore[arg-type]
            layout.addWidget(self._reset_btn, 0)

        self.set_chord(initial, emit_signal=False)

    def chord(self) -> str | None:
        return self._chord

    def is_recording(self) -> bool:
        return bool(self._recording)

    def set_reset_enabled(self, enabled: bool) -> None:
        """
        Enable/disable the Reset control, if present.

        This is used by the Preferences UI to visually indicate whether a binding
        is currently following defaults (Reset disabled) or user-overridden (Reset enabled).
        """
        if self._reset_btn is not None:
            self._reset_btn.setEnabled(bool(enabled))

    def set_chord(self, chord: str | None, *, emit_signal: bool = True) -> None:
        self._chord = chord.strip() if isinstance(chord, str) and chord.strip() else None
        self._bind_btn.setText(self._chord or "Set…")
        if emit_signal:
            self.chordChanged.emit(self._chord)

    def _clear(self) -> None:
        self.set_chord(None)

    def _toggle_record(self) -> None:
        if self._recording:
            self._stop_record(cancel=True)
            return
        self._start_record()

    def _start_record(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        self._recording = True
        self.recordingChanged.emit(True)
        try:
            app.setProperty("datalens.shortcuts.capture_active", True)
        except Exception:
            pass
        self._bind_btn.setText("Press a key…")
        self._bind_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)

        def on_captured(chord: str | None) -> None:
            self._stop_record(cancel=False)
            if chord is None:
                return
            self.set_chord(chord)

        self._capture_filter = _CaptureNextChordFilter(on_captured=on_captured)
        app.installEventFilter(self._capture_filter)

        # Re-enable the button after the event loop tick so the UI updates.
        self._bind_btn.setEnabled(True)

    def _stop_record(self, *, cancel: bool) -> None:
        app = QApplication.instance()
        if app is not None and self._capture_filter is not None:
            try:
                app.removeEventFilter(self._capture_filter)
            except Exception:
                pass
        if app is not None:
            try:
                app.setProperty("datalens.shortcuts.capture_active", False)
            except Exception:
                pass
        self._capture_filter = None
        self._recording = False
        self.recordingChanged.emit(False)
        self._bind_btn.setText(self._chord or "Set…")
        self._bind_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)
        if cancel:
            return


__all__ = ["ShortcutBindingEditor"]
