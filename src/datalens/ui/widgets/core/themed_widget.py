# src/datalens/ui/widgets/core/themed.py
from __future__ import annotations
from typing import Protocol
from PySide6.QtWidgets import QWidget

from datalens.ui.theme.app_theme import AppTheme

"""
Should subclass ThemedWidget:
Loader/spinner
Annotation overlays
Icon widgets
Anything drawing with QPainter

Should not subclass ThemedWidget:
Buttons
Checkboxes
Toggles
Layout containers
Dialogs/windows
"""

class ThemedControl(Protocol):
    """
    Optional interface for widgets that can re-apply theme dynamically.
    """

    def apply_theme(self, theme: AppTheme) -> None:
        ...


class ThemedWidget(QWidget):
    """
    Base class for custom-painted widgets that need direct access to AppTheme.

    Use this when you override paintEvent and draw your own visuals using
    QPainter. Buttons/checkboxes that are styled via QSS normally do NOT
    need this.
    """

    def __init__(self, theme: AppTheme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme

    @property
    def theme(self) -> AppTheme:
        return self._theme

    def apply_theme(self, theme: AppTheme) -> None:
        self._theme = theme
        self.update()
