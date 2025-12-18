from __future__ import annotations

from PySide6.QtWidgets import QMainWindow

from datalens.ui.menus.contracts import EditMenuController


class QtEditMenuController(EditMenuController):
    def __init__(self, main_window: QMainWindow) -> None:
        self._main_window = main_window
        self._preferences_dialog = None

    def open_preferences(self) -> None:
        from datalens.ui.menus.edit.preferences.preferences_dialog import PreferencesDialog

        if self._preferences_dialog is None:
            self._preferences_dialog = PreferencesDialog(parent=self._main_window)
            self._preferences_dialog.finished.connect(lambda *_: setattr(self, "_preferences_dialog", None))
        self._preferences_dialog.show()
        self._preferences_dialog.raise_()
        self._preferences_dialog.activateWindow()

    def open_keyboard_shortcuts(self) -> None:
        from datalens.ui.menus.edit.preferences.preferences_dialog import PreferencesDialog

        if self._preferences_dialog is None:
            self._preferences_dialog = PreferencesDialog(
                parent=self._main_window,
                initial_page_key="keyboard_shortcuts",
            )
            self._preferences_dialog.finished.connect(lambda *_: setattr(self, "_preferences_dialog", None))
        else:
            self._preferences_dialog.set_current_page("keyboard_shortcuts")
        self._preferences_dialog.show()
        self._preferences_dialog.raise_()
        self._preferences_dialog.activateWindow()
