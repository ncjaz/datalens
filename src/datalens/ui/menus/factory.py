from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow

from datalens.ui.menus.contracts import MenuControllers
from datalens.ui.menus.edit.controller import QtEditMenuController
from datalens.ui.menus.file.controller import QtFileMenuController
from datalens.ui.menus.help.controller import QtHelpMenuController
from datalens.ui.menus.menubar import DatalensMenuBar
from datalens.ui.menus.plugins.controller import QtPluginsMenuController
from datalens.ui.shortcuts.core_shortcuts import register_core_shortcuts


def create_menubar(
    main_window: QMainWindow,
    *,
    undo_actions: tuple[QAction, QAction] | None = None,
) -> DatalensMenuBar:
    """
    Create the standard DataLens menu bar for a main window.

    This is a small composition helper so `MainWindow` doesn't accumulate menu
    wiring as the menu tree grows.
    """
    controllers = MenuControllers(
        file=QtFileMenuController(main_window),
        edit=QtEditMenuController(main_window),
        plugins=QtPluginsMenuController(main_window),
        help=QtHelpMenuController(main_window),
    )
    register_core_shortcuts(controllers=controllers)
    return DatalensMenuBar(main_window, controllers=controllers, undo_actions=undo_actions)
