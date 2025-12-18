from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

def _to_int(value: object) -> int:
    """
    Best-effort conversion for PySide6 enum/flag values.

    Some Qt enum/flag wrappers in PySide6 do not support `int(x)` directly
    (they may expose `.value` instead).
    """
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        try:
            raw = getattr(value, "value")
            return int(raw)  # type: ignore[arg-type]
        except Exception:
            return 0


def to_int(value: object) -> int:
    """Public alias for enum/flag conversion used across shortcuts helpers."""
    return _to_int(value)


def format_modifiers(mods: Qt.KeyboardModifiers) -> list[str]:
    parts: list[str] = []
    if mods & Qt.ControlModifier:
        parts.append("Ctrl")
    if mods & Qt.ShiftModifier:
        parts.append("Shift")
    if mods & Qt.AltModifier:
        parts.append("Alt")
    if mods & Qt.MetaModifier:
        parts.append("Meta")
    return parts


def mouse_button_name(button: Qt.MouseButton) -> str | None:
    if button == Qt.LeftButton:
        return "LeftClick"
    if button == Qt.RightButton:
        return "RightClick"
    if button == Qt.MiddleButton:
        return "MiddleClick"
    if button == Qt.BackButton:
        return "BackClick"
    if button == Qt.ForwardButton:
        return "ForwardClick"
    return None


def wheel_direction_name(delta_y: int) -> str | None:
    if delta_y > 0:
        return "WheelUp"
    if delta_y < 0:
        return "WheelDown"
    return None


def event_to_chord(event: QEvent) -> str | None:
    """
    Convert a Qt input event into a canonical chord string.

    Examples:
    - `Ctrl+Shift+M`
    - `Alt+LeftClick`
    - `Ctrl+WheelUp`
    """
    etype = QEvent.Type(event.type())
    if etype == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
        if event.isAutoRepeat():
            return None
        key_value = _to_int(event.key())
        if not key_value:
            return None
        if key_value in (_to_int(Qt.Key_Control), _to_int(Qt.Key_Shift), _to_int(Qt.Key_Alt), _to_int(Qt.Key_Meta)):
            return None
        mods = event.modifiers()
        mods_value = _to_int(mods)
        # Avoid generating chords for plain typing (e.g. 'A') since it is noisy and
        # can interfere with text inputs. We still allow special keys with no modifiers
        # (e.g. Escape/F-keys) and any chord that includes modifiers.
        if mods == Qt.NoModifier and 0x20 <= key_value <= 0x7E:
            return None
        try:
            seq = QKeySequence(mods_value | key_value)
            text = seq.toString(QKeySequence.PortableText).strip()
            return text or None
        except Exception:
            return None

    if etype == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
        button = mouse_button_name(event.button())
        if button is None:
            return None
        parts = format_modifiers(event.modifiers())
        parts.append(button)
        return "+".join(parts)

    if etype == QEvent.Type.Wheel and isinstance(event, QWheelEvent):
        direction = wheel_direction_name(event.angleDelta().y())
        if direction is None:
            return None
        parts = format_modifiers(event.modifiers())
        parts.append(direction)
        return "+".join(parts)

    return None


def is_text_input_widget(widget: QWidget | None) -> bool:
    if widget is None:
        return False
    if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
        return True
    if isinstance(widget, QComboBox):
        return bool(widget.isEditable())
    return False


__all__ = [
    "event_to_chord",
    "format_modifiers",
    "is_text_input_widget",
    "mouse_button_name",
    "to_int",
    "wheel_direction_name",
]
