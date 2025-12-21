from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QSizePolicy, QWidget


def make_section_box(parent: QWidget, title: str) -> QGroupBox:
    box = QGroupBox(title, parent)
    box.setStyleSheet("QGroupBox { font-weight: 700; }")
    box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    return box


__all__ = ["make_section_box"]

