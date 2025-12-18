from __future__ import annotations

from PySide6.QtWidgets import QMenu

from datalens.ui.menus.contracts import PluginsMenuController


def populate(menu: QMenu, *, controller: PluginsMenuController) -> None:
    create_action = menu.addAction("Create New Plugin\u2026")
    create_action.triggered.connect(lambda *_: controller.create_new_plugin())

    menu.addSeparator()

    action = menu.addAction("Manage Plugins\u2026")
    action.triggered.connect(lambda *_: controller.manage_plugins())
