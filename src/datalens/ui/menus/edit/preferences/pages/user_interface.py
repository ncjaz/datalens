from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from datalens.ui.menus.edit.preferences.pages.loader import LoaderPreferencesPage
from datalens.ui.menus.edit.preferences.pages.theme import ThemePreferencesPage


class UserInterfacePreferencesPage(QWidget):
    """
    Preferences page: User Interface.

    This page is a container for UI-related sub-sections. Selecting this page
    shows all UI sub-sections at once; selecting a specific child page focuses
    on that section only.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("User Interface")
        title.setObjectName("PreferencesTitle")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(title)

        layout.addWidget(ThemePreferencesPage(self))
        layout.addWidget(LoaderPreferencesPage(self))
        layout.addStretch(1)


__all__ = ["UserInterfacePreferencesPage"]
