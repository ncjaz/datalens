from __future__ import annotations

from PySide6.QtWidgets import QMainWindow

from datalens.core.logging import get_logger
from datalens.ui.menus.contracts import EditMenuController


log = get_logger(__name__)


class QtEditMenuController(EditMenuController):
    def __init__(self, main_window: QMainWindow) -> None:
        self._main_window = main_window
        self._preferences_dialog = None

    def _should_route_document_undo(self) -> bool:
        """
        Return True if Ctrl+Z/Ctrl+Y should affect the active workspace.

        If a dialog/popup window is active, prefer leaving undo/redo to that UI
        (or no-op) rather than mutating the active document underneath.
        """
        try:
            return bool(self._main_window.isActiveWindow())
        except Exception:
            return False

    def _is_preferences_focused(self) -> bool:
        dlg = self._preferences_dialog
        if dlg is None:
            return False
        try:
            return bool(dlg.isVisible() and dlg.isActiveWindow())
        except Exception:
            return False

    def undo(self) -> None:
        # While a preferences/configuration window is focused, prefer leaving
        # Ctrl+Z/Ctrl+Y to local widget behavior (or no-op) instead of mutating
        # the active document/workspace.
        if not self._should_route_document_undo():
            return
        if self._is_preferences_focused():
            return
        undo_redo = getattr(self._main_window, "_undo_redo", None)
        if undo_redo is None:
            return
        try:
            undo_redo.undo()
        except Exception:
            log.debug("Undo dispatch failed (best-effort)", exc_info=True)
            return

    def redo(self) -> None:
        if not self._should_route_document_undo():
            return
        if self._is_preferences_focused():
            return
        undo_redo = getattr(self._main_window, "_undo_redo", None)
        if undo_redo is None:
            return
        try:
            undo_redo.redo()
        except Exception:
            log.debug("Redo dispatch failed (best-effort)", exc_info=True)
            return

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
