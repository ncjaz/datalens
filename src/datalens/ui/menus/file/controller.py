from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

from datalens.ui.menus.contracts import FileMenuController


class QtFileMenuController(FileMenuController):
    def __init__(self, main_window: QMainWindow) -> None:
        self._main_window = main_window

    def new_project(self) -> None:
        QMessageBox.information(self._main_window, "New Project", "New Project is not implemented yet.")

    def open_project(self) -> None:
        start_dir = ""
        try:
            best = getattr(self._main_window, "_best_open_start_dir", None)
            if callable(best):
                start_dir = str(best())
        except Exception:
            start_dir = ""

        directory = QFileDialog.getExistingDirectory(self._main_window, "Open project folder", start_dir)
        if not directory:
            return
        self.open_recent_project(Path(directory))

    def open_recent_project(self, path: Path) -> None:
        fn = getattr(self._main_window, "_open_project", None)
        if callable(fn):
            fn(path)

    def close_project(self) -> None:
        fn = getattr(self._main_window, "_close_project_interactive", None)
        if callable(fn):
            fn()

    def quit_app(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()

