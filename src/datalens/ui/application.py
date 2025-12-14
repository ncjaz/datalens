from __future__ import annotations

from PySide6.QtWidgets import QApplication

from datalens.core.context import AppContext, create_app_context
from datalens.ui.theme import AppTheme


class DatalensApplication(QApplication):
    """
    Minimal QApplication wrapper for V2.

    Stores the shared :class:`~datalens.ui.theme.app_theme.AppTheme` instance so
    dialogs/widgets can resolve it via ``QApplication.instance().app_theme``.
    """

    def __init__(self, argv: list[str], *, theme: AppTheme | None = None) -> None:
        super().__init__(argv)
        self.app_theme: AppTheme = theme or AppTheme()
        self.app_theme.apply_to(self)
        self.app_theme.theme_changed.connect(lambda: self.app_theme.apply_to(self))
        self.app_context: AppContext = create_app_context(self.app_theme)
