from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QMenuBar, QMessageBox


class DatalensMenuBar(QMenuBar):
    """
    V2 main menu bar.

    Keep this isolated from MainWindow so the top-level window doesn't become
    monolithic as menus grow.
    """

    newProjectRequested = Signal()
    openProjectRequested = Signal()
    closeProjectRequested = Signal()
    openRecentProjectRequested = Signal(object)  # Path

    def __init__(self, main_window: QMainWindow) -> None:
        super().__init__(main_window)
        self._main_window = main_window
        self._recent_menu: QMenu | None = None
        self._recent_projects: list[Path] = []
        self._close_project_action = None
        self._build_menus()

    def _build_menus(self) -> None:
        file_menu = self.addMenu("File")
        edit_menu = self.addMenu("Edit")
        help_menu = self.addMenu("Help")

        # Minimal actions so the menus are functional.
        new_project_action = file_menu.addAction("New Project\u2026")
        new_project_action.triggered.connect(self._on_new_project)

        open_project_action = file_menu.addAction("Open Project\u2026")
        open_project_action.triggered.connect(self._on_open_project)

        self._recent_menu = file_menu.addMenu("Recent Projects")
        self._recent_menu.aboutToShow.connect(self._rebuild_recent_projects_menu)

        self._close_project_action = file_menu.addAction("Close Project")
        self._close_project_action.triggered.connect(self._on_close_project)
        self._close_project_action.setEnabled(False)

        file_menu.addSeparator()

        quit_action = file_menu.addAction("Quit")
        quit_action.triggered.connect(self._on_quit)

        # Placeholders for future Edit actions (undo/redo/preferences).
        edit_menu.addAction("Preferences\u2026").setEnabled(False)

        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self._on_about)

    def set_recent_projects(self, projects: list[Path]) -> None:
        self._recent_projects = list(projects)
        self._rebuild_recent_projects_menu()

    def set_has_project(self, has_project: bool) -> None:
        if self._close_project_action is not None:
            self._close_project_action.setEnabled(bool(has_project))

    def _rebuild_recent_projects_menu(self) -> None:
        menu = self._recent_menu
        if menu is None:
            return
        menu.clear()

        if not self._recent_projects:
            placeholder = menu.addAction("No recent projects")
            placeholder.setEnabled(False)
            return

        for p in self._recent_projects[:12]:
            action = menu.addAction(str(p))
            action.triggered.connect(lambda _=False, path=p: self.openRecentProjectRequested.emit(path))

    @Slot()
    def _on_quit(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()

    @Slot()
    def _on_new_project(self) -> None:
        self.newProjectRequested.emit()

    @Slot()
    def _on_open_project(self) -> None:
        self.openProjectRequested.emit()

    @Slot()
    def _on_close_project(self) -> None:
        self.closeProjectRequested.emit()

    @Slot()
    def _on_about(self) -> None:
        QMessageBox.about(
            self._main_window,
            "About DataLens",
            "DataLens (V2)\n\nEarly development build.",
        )
