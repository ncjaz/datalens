from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QMenuBar

from datalens.ui.menus.contracts import MenuControllers
from datalens.ui.menus.file.menu import FileMenuHandle
from datalens.ui.menus.file.menu import populate as populate_file_menu
from datalens.ui.menus.edit.menu import populate as populate_edit_menu
from datalens.ui.menus.help.menu import populate as populate_help_menu
from datalens.ui.menus.plugins.menu import populate as populate_plugins_menu


class DatalensMenuBar(QMenuBar):
    """
    V2 main menu bar.

    Keep this isolated from MainWindow so the top-level window doesn't become
    monolithic as menus grow.
    """

    def __init__(self, main_window: QMainWindow, *, controllers: MenuControllers) -> None:
        super().__init__(main_window)
        self._main_window = main_window
        self._controllers = controllers
        self._file_handle: FileMenuHandle | None = None
        self._build_menus()

    def _build_menus(self) -> None:
        file_menu = self.addMenu("File")
        edit_menu = self.addMenu("Edit")
        plugins_menu = self.addMenu("Plugins")
        help_menu = self.addMenu("Help")

        self._file_handle = populate_file_menu(file_menu, controller=self._controllers.file)
        populate_edit_menu(edit_menu, controller=self._controllers.edit)
        populate_plugins_menu(plugins_menu, controller=self._controllers.plugins)
        populate_help_menu(help_menu, controller=self._controllers.help)

    def set_recent_projects(self, projects: list[Path]) -> None:
        handle = self._file_handle
        if handle is None:
            return
        handle.set_recent_projects(projects)

    def set_has_project(self, has_project: bool) -> None:
        handle = self._file_handle
        if handle is None:
            return
        handle.set_has_project(has_project)
