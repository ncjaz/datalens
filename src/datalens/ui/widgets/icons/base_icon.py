# src/datalens/ui/widgets/icons/base_icon.py
from __future__ import annotations
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter
from PySide6.QtCore import QSize

from datalens.domain.ui.icons import IconDefinition, IconRole
from datalens.ui.theme import AppTheme
from datalens.ui.widgets.core.themed_widget import ThemedWidget

class BaseIconWidget(ThemedWidget):
    """
    Base icon widget.

    - Knows its IconDefinition.
    - Has helpers: primary_color(), secondary_color(), etc.
    - Concrete subclasses implement _paint_icon().
    """

    def __init__(
        self,
        icon_def: IconDefinition,
        app_theme: AppTheme,
        parent: QWidget | None = None,
    ):
        super().__init__(app_theme, parent)
        self._icon_def = icon_def
        self.setFixedSize(QSize(24, 24))  # or 32, 56, etc.

    def paintEvent(self, event):
        painter = QPainter(self)
        self._paint_icon(painter)

    def _paint_icon(self, painter: QPainter) -> None:
        """
        Subclasses implement this and use primary_color(), etc.

        Example:
            pen = QPen(self.primary_color())
        """
        raise NotImplementedError

    @property
    def icon_def(self) -> IconDefinition:
        return self._icon_def

    @property
    def role(self) -> IconRole:
        return self._icon_def.role
