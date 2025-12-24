from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from datalens.ui.menus.contracts import EditMenuController


def populate(
    menu: QMenu,
    *,
    controller: EditMenuController,
    undo_actions: tuple[QAction, QAction] | None = None,
) -> None:
    if undo_actions is not None:
        undo_action, redo_action = undo_actions
        menu.addAction(undo_action)
        menu.addAction(redo_action)
        menu.addSeparator()

    preferences_action = menu.addAction("Preferences")
    preferences_action.triggered.connect(lambda *_: controller.open_preferences())

    shortcuts_action = menu.addAction("Keyboard Shortcuts\u2026")
    shortcuts_action.triggered.connect(lambda *_: controller.open_keyboard_shortcuts())
