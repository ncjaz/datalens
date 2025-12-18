from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.toggle import Toggle, ToggleOption

from .common import make_section_box


def build_toggles_section(parent: QWidget, *, theme: AppTheme) -> QWidget:
    box = make_section_box(parent, "Toggles")
    layout = QGridLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setHorizontalSpacing(10)
    layout.setVerticalSpacing(10)

    toggle1 = Toggle(theme, ToggleOption("global", "Global"), ToggleOption("project", "Project"), box)
    toggle2 = Toggle(theme, ToggleOption("off", "Off"), ToggleOption("on", "On"), box)
    toggle3 = Toggle(theme, ToggleOption("a", "Option A"), ToggleOption("b", "Option B"), box)
    toggle3.setEnabled(False)

    layout.addWidget(QLabel("Global/Project", box), 0, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
    layout.addWidget(toggle1, 0, 1)
    layout.addWidget(QLabel("Off/On", box), 1, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
    layout.addWidget(toggle2, 1, 1)
    layout.addWidget(QLabel("Disabled", box), 2, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
    layout.addWidget(toggle3, 2, 1)
    layout.setColumnStretch(1, 1)
    return box


__all__ = ["build_toggles_section"]

