# src/datalens/ui/theme.py
from __future__ import annotations
from dataclasses import dataclass
from PySide6 import QtGui

from datalens.domain.ui.theme import ThemeSettings

@dataclass
class AppTheme:
    """Qt-friendly wrapper around ThemeSettings."""

    settings: ThemeSettings

    def primary_color(self) -> QtGui.QColor:
        return QtGui.QColor(self.settings.primary_color)

    def secondary_color(self) -> QtGui.QColor:
        return QtGui.QColor(self.settings.secondary_color)

    def tertiary_color(self) -> QtGui.QColor:
        return QtGui.QColor(self.settings.tertiary_color)

    def text_color(self) -> QtGui.QColor:
        return QtGui.QColor(self.settings.text_color)

    def with_alpha(self, hex_color: str, alpha: float) -> QtGui.QColor:
        c = QtGui.QColor(hex_color)
        c.setAlphaF(alpha)
        return c
