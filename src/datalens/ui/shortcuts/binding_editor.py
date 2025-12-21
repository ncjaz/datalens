from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLineEdit, QPushButton, QWidget

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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._edit = QLineEdit(self)
        self._edit.setReadOnly(True)
        self._edit.setPlaceholderText("Unbound")
        self._edit.setMinimumWidth(180)
        layout.addWidget(self._edit, 1)

        self._record_btn = QPushButton("Record...", self)
        self._record_btn.clicked.connect(self._toggle_record)  # type: ignore[arg-type]
        layout.addWidget(self._record_btn, 0)

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
        text = self._edit.text().strip()
        return text or None

    def is_recording(self) -> bool:
        return bool(self._recording)

    def set_chord(self, chord: str | None, *, emit_signal: bool = True) -> None:
        self._edit.setText(chord or "")
        if emit_signal:
            self.chordChanged.emit(chord)

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
        self._record_btn.setText("Press a key...")
        self._record_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)
        self._edit.setPlaceholderText("Recording... (Esc to cancel)")

        def on_captured(chord: str | None) -> None:
            self._stop_record(cancel=False)
            if chord is None:
                return
            self.set_chord(chord)

        self._capture_filter = _CaptureNextChordFilter(on_captured=on_captured)
        app.installEventFilter(self._capture_filter)

        # Re-enable the button after the event loop tick so the UI updates.
        self._record_btn.setEnabled(True)

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
        self._record_btn.setText("Record...")
        self._record_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)
        self._edit.setPlaceholderText("Unbound")
        if cancel:
            return


__all__ = ["ShortcutBindingEditor"]
