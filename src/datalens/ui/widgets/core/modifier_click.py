from __future__ import annotations

"""
Small helper for "modifier-click" buttons.

This is intentionally *widget-local* (installs an event filter on a single button)
so it does not interfere with the global shortcuts / gesture routing systems.

Typical use case:
- Click: do a one-shot action (refresh once)
- Shift+Click: toggle a persistent mode (auto-refresh)
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QAbstractButton

from datalens.core.logging import get_logger

log = get_logger(__name__)


def _flag_value(flags: object) -> int:
    value = getattr(flags, "value", flags)
    try:
        return int(value)
    except Exception:
        return 0


def normalize_modifiers(mods: Qt.KeyboardModifiers) -> Qt.KeyboardModifiers:
    """
    Normalize keyboard modifiers so matching is predictable.

    We only consider the common "explicit" modifiers used in UX:
    Shift/Ctrl/Alt/Meta.
    """
    mask = _flag_value(Qt.ShiftModifier) | _flag_value(Qt.ControlModifier) | _flag_value(Qt.AltModifier) | _flag_value(Qt.MetaModifier)
    return Qt.KeyboardModifiers(_flag_value(mods) & mask)


@dataclass(frozen=True)
class ModifierClickAction:
    """
    Declarative mapping: mouse release + modifier set -> callback.

    Matching defaults to exact-match to avoid surprising behavior if a user holds
    multiple modifiers at once.
    """

    required_modifiers: Qt.KeyboardModifiers
    callback: Callable[[], None]
    exact_match: bool = True

    def matches(self, mods: Qt.KeyboardModifiers) -> bool:
        required = normalize_modifiers(self.required_modifiers)
        actual = normalize_modifiers(mods)
        if self.exact_match:
            return _flag_value(actual) == _flag_value(required)
        return (_flag_value(actual) & _flag_value(required)) == _flag_value(required)


class ModifierClickRouter(QObject):
    """
    Route mouse "click" interactions on a button based on held modifiers.

    - Only handles `MouseButtonRelease` for LeftButton.
    - When an action matches, the event is consumed so the button will not emit
      its normal `clicked`/`toggled` signals.
    """

    def __init__(
        self,
        button: QAbstractButton,
        *,
        actions: Sequence[ModifierClickAction],
        log_name: str | None = None,
    ) -> None:
        super().__init__(button)
        self._button = button
        self._actions = tuple(actions)
        self._log_name = str(log_name or button.objectName() or type(button).__name__)
        self._button.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if watched is not self._button:
            return False
        if event.type() != QEvent.MouseButtonRelease:
            return False
        if not isinstance(event, QMouseEvent):
            return False
        if event.button() != Qt.LeftButton:
            return False
        if not self._button.isEnabled():
            return False

        mods = normalize_modifiers(event.modifiers())
        for action in self._actions:
            if action.matches(mods):
                log.debug(
                    "Modifier click routed",
                    extra={
                        "operation": "ui",
                        "phase": "modifier_click",
                        "target": self._log_name,
                        "mods": _flag_value(mods),
                        "required_mods": _flag_value(normalize_modifiers(action.required_modifiers)),
                    },
                )
                try:
                    action.callback()
                except Exception:
                    log.warning("Modifier click action failed (best-effort)", exc_info=True)
                return True

        return False


__all__ = ["ModifierClickAction", "ModifierClickRouter", "normalize_modifiers"]

