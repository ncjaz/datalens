from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QWidget


@dataclass(frozen=True)
class TimerInfo:
    interval_ms: int
    single_shot: bool
    parent_chain: str


def _object_label(obj: object) -> str:
    name = ""
    try:
        name = obj.objectName()  # type: ignore[attr-defined]
    except Exception:
        name = ""
    cls = type(obj).__name__
    return f"{cls}({name})" if name else cls


def _parent_chain(obj: QObject, *, limit: int = 8) -> str:
    parts: list[str] = []
    current: QObject | None = obj
    for _ in range(max(1, int(limit))):
        if current is None:
            break
        parts.append(_object_label(current))
        current = current.parent()
    return " <- ".join(parts)


def dump_top_level_widgets() -> list[str]:
    app = QApplication.instance()
    if app is None:
        return []
    widgets = list(app.topLevelWidgets())
    lines: list[str] = []
    for w in widgets:
        try:
            visible = bool(w.isVisible())
        except Exception:
            visible = False
        lines.append(f"{_object_label(w)} visible={visible}")
    return lines


def dump_active_timers(*, include_inactive: bool = False) -> list[TimerInfo]:
    """
    Best-effort dump of timers attached to the widget tree.

    This is meant for diagnosing cases where a hidden dialog/spinner keeps a
    QTimer running and burns CPU even after a transition (welcome -> main).
    """
    app = QApplication.instance()
    if app is None:
        return []

    timers: list[TimerInfo] = []
    for widget in app.allWidgets():
        if not isinstance(widget, QWidget):
            continue
        for t in widget.findChildren(QTimer):
            try:
                active = bool(t.isActive())
            except Exception:
                active = False
            if not include_inactive and not active:
                continue
            try:
                interval_ms = int(t.interval())
            except Exception:
                interval_ms = -1
            try:
                single = bool(t.isSingleShot())
            except Exception:
                single = False
            timers.append(
                TimerInfo(
                    interval_ms=interval_ms,
                    single_shot=single,
                    parent_chain=_parent_chain(t),
                )
            )
    timers.sort(key=lambda x: x.interval_ms if x.interval_ms >= 0 else 10**9)
    return timers

