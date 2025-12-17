from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from datalens.ui.menus.contracts import FileMenuController


@dataclass
class FileMenuHandle:
    """
    Handle for updating dynamic File menu state.

    `recent_projects` and "Close Project" enabled state are owned here so the
    menu bar implementation stays small.
    """

    menu: QMenu
    controller: FileMenuController
    recent_menu: QMenu
    close_project_action: QAction
    recent_projects: list[Path]

    def set_recent_projects(self, projects: list[Path]) -> None:
        self.recent_projects = list(projects)

    def set_has_project(self, has_project: bool) -> None:
        self.close_project_action.setEnabled(bool(has_project))

    def rebuild_recent_projects_menu(self) -> None:
        menu = self.recent_menu
        menu.clear()
        if not self.recent_projects:
            placeholder = menu.addAction("No recent projects")
            placeholder.setEnabled(False)
            return
        for p in self.recent_projects[:12]:
            action = menu.addAction(str(p))
            action.triggered.connect(lambda _=False, path=p: self.controller.open_recent_project(path))


def populate(menu: QMenu, *, controller: FileMenuController) -> FileMenuHandle:
    new_project_action = menu.addAction("New Project\u2026")
    new_project_action.triggered.connect(lambda *_: controller.new_project())

    open_project_action = menu.addAction("Open Project\u2026")
    open_project_action.triggered.connect(lambda *_: controller.open_project())

    recent_menu = menu.addMenu("Recent Projects")
    close_project_action = menu.addAction("Close Project")
    close_project_action.setEnabled(False)
    close_project_action.triggered.connect(lambda *_: controller.close_project())

    menu.addSeparator()

    quit_action = menu.addAction("Quit")
    quit_action.triggered.connect(lambda *_: controller.quit_app())

    handle = FileMenuHandle(
        menu=menu,
        controller=controller,
        recent_menu=recent_menu,
        close_project_action=close_project_action,
        recent_projects=[],
    )
    recent_menu.aboutToShow.connect(handle.rebuild_recent_projects_menu)
    return handle
