from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from PySide6.QtCore import QByteArray, QSettings


ORG_NAME = "rsCapture"
APP_NAME = "DataLensV2"


def qsettings() -> QSettings:
    """
    Return the application QSettings store for V2 UI state.

    We use an explicit org/app name so V2 does not accidentally collide with V1
    (which also uses QSettings in places).
    """
    return QSettings(ORG_NAME, APP_NAME)


@contextmanager
def settings_group(settings: QSettings, *parts: str) -> Iterator[QSettings]:
    for part in parts:
        settings.beginGroup(part)
    try:
        yield settings
    finally:
        for _ in parts:
            settings.endGroup()


@dataclass(frozen=True)
class QSettingsScope:
    """
    Helper for namespacing QSettings keys.

    Intended for UI layout/geometry persistence only (not semantic preferences).
    """

    parts: tuple[str, ...]

    @contextmanager
    def open(self) -> Iterator[QSettings]:
        settings = qsettings()
        with settings_group(settings, *self.parts):
            yield settings

    def save_geometry(self, key: str, widget) -> None:
        with self.open() as settings:
            save_geometry(settings, key, widget)

    def restore_geometry(self, key: str, widget) -> bool:
        with self.open() as settings:
            return restore_geometry(settings, key, widget)

    def save_splitter(self, key: str, splitter) -> None:
        with self.open() as settings:
            save_splitter(settings, key, splitter)

    def restore_splitter(self, key: str, splitter) -> bool:
        with self.open() as settings:
            return restore_splitter(settings, key, splitter)


def plugin_ui_scope(plugin_id: str, *parts: str) -> QSettingsScope:
    """
    Return a QSettings scope for plugin UI state.

    Keys are namespaced so plugins can be enabled/disabled without collisions:
    `plugins/<plugin_id>/ui/...`
    """

    return QSettingsScope(("plugins", plugin_id, "ui", *parts))


def restore_qbytearray(settings: QSettings, key: str) -> QByteArray | None:
    value = settings.value(key)
    if isinstance(value, QByteArray) and value:
        return value
    return None


def save_geometry(settings: QSettings, key: str, widget) -> None:
    settings.setValue(key, widget.saveGeometry())


def restore_geometry(settings: QSettings, key: str, widget) -> bool:
    geometry = restore_qbytearray(settings, key)
    if geometry is None:
        return False
    try:
        return bool(widget.restoreGeometry(geometry))
    except Exception:
        return False


def save_splitter(settings: QSettings, key: str, splitter) -> None:
    settings.setValue(key, splitter.saveState())


def restore_splitter(settings: QSettings, key: str, splitter) -> bool:
    state = restore_qbytearray(settings, key)
    if state is None:
        return False
    try:
        return bool(splitter.restoreState(state))
    except Exception:
        return False
