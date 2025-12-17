from __future__ import annotations

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from datalens.ui.menus.contracts import HelpMenuController


class QtHelpMenuController(HelpMenuController):
    def __init__(self, main_window: QMainWindow) -> None:
        self._main_window = main_window
        self._states_dialog = None

    def open_states(self) -> None:
        from datalens.ui.menus.help.states.states_dialog import StatesDialog

        app = QApplication.instance()
        app_ctx = getattr(app, "app_context", None) if app is not None else None
        if app_ctx is None:
            QMessageBox.critical(self._main_window, "States", "Application context is not available.")
            return

        if self._states_dialog is None:
            self._states_dialog = StatesDialog(app_ctx=app_ctx, parent=self._main_window)
            self._states_dialog.finished.connect(lambda *_: setattr(self, "_states_dialog", None))
        self._states_dialog.show()
        self._states_dialog.raise_()
        self._states_dialog.activateWindow()

    def open_about(self) -> None:
        QMessageBox.about(
            self._main_window,
            "About DataLens",
            "DataLens (V2)\n\nEarly development build.",
        )
