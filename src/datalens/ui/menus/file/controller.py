from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow

from datalens.ui.menus.contracts import FileMenuController
from datalens.ui.project_dialogs import choose_existing_project_root, choose_new_project_root


class QtFileMenuController(FileMenuController):
    def __init__(self, main_window: QMainWindow) -> None:
        self._main_window = main_window

    def _best_dialog_start_dir(self) -> Path | None:
        try:
            best = getattr(self._main_window, "best_open_start_dir", None)
            if callable(best):
                return Path(best())
        except Exception:
            return None
        return None

    def new_project(self) -> None:
        selected = choose_new_project_root(parent=self._main_window, start_dir=self._best_dialog_start_dir())
        if selected is None:
            return
        self.open_recent_project(selected)

    def open_project(self) -> None:
        selected = choose_existing_project_root(parent=self._main_window, start_dir=self._best_dialog_start_dir())
        if selected is None:
            return
        self.open_recent_project(selected)

    def open_recent_project(self, path: Path) -> None:
        fn = getattr(self._main_window, "open_project", None)
        if callable(fn):
            fn(path)

    def close_project(self) -> None:
        fn = getattr(self._main_window, "close_project", None)
        if callable(fn):
            fn()

    def quit_app(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
