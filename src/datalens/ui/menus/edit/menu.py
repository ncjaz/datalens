from __future__ import annotations

from PySide6.QtWidgets import QMenu

from datalens.ui.menus.contracts import EditMenuController


def populate(menu: QMenu, *, controller: EditMenuController) -> None:
    preferences_action = menu.addAction("Preferences")
    preferences_action.triggered.connect(lambda *_: controller.open_preferences())

    shortcuts_action = menu.addAction("Keyboard Shortcuts\u2026")
    shortcuts_action.triggered.connect(lambda *_: controller.open_keyboard_shortcuts())
