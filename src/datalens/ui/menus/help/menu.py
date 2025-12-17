from __future__ import annotations

from PySide6.QtWidgets import QMenu

from datalens.ui.menus.contracts import HelpMenuController


def populate(menu: QMenu, *, controller: HelpMenuController) -> None:
    states_action = menu.addAction("States\u2026")
    states_action.triggered.connect(lambda *_: controller.open_states())

    menu.addSeparator()

    about_action = menu.addAction("About")
    about_action.triggered.connect(lambda *_: controller.open_about())
