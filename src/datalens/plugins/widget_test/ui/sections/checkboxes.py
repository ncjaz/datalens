from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.checkboxes import DatalensCheckBox

from .common import make_section_box


def build_checkboxes_section(parent: QWidget, *, theme: AppTheme) -> QWidget:
    box = make_section_box(parent, "Checkboxes")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    cb1 = DatalensCheckBox("Enable autosave", theme, box)
    cb2 = DatalensCheckBox("Show overlays", theme, box)
    cb2.setChecked(True)
    cb3 = DatalensCheckBox("Disabled option", theme, box)
    cb3.setEnabled(False)

    layout.addWidget(cb1)
    layout.addWidget(cb2)
    layout.addWidget(cb3)
    return box


__all__ = ["build_checkboxes_section"]

