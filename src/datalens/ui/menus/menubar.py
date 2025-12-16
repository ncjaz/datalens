from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QApplication, QMainWindow, QMenuBar, QMessageBox


class DatalensMenuBar(QMenuBar):
    """
    V2 main menu bar.

    Keep this isolated from MainWindow so the top-level window doesn't become
    monolithic as menus grow.
    """

    newProjectRequested = Signal()

    def __init__(self, main_window: QMainWindow) -> None:
        super().__init__(main_window)
        self._main_window = main_window
        self._build_menus()

    def _build_menus(self) -> None:
        file_menu = self.addMenu("File")
        edit_menu = self.addMenu("Edit")
        help_menu = self.addMenu("Help")

        # Minimal actions so the menus are functional.
        new_project_action = file_menu.addAction("New Project\u2026")
        new_project_action.triggered.connect(self._on_new_project)

        file_menu.addSeparator()

        quit_action = file_menu.addAction("Quit")
        quit_action.triggered.connect(self._on_quit)

        # Placeholders for future Edit actions (undo/redo/preferences).
        edit_menu.addAction("Preferences\u2026").setEnabled(False)

        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self._on_about)

    @Slot()
    def _on_quit(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()

    @Slot()
    def _on_new_project(self) -> None:
        self.newProjectRequested.emit()

    @Slot()
    def _on_about(self) -> None:
        QMessageBox.about(
            self._main_window,
            "About DataLens",
            "DataLens (V2)\n\nEarly development build.",
        )
