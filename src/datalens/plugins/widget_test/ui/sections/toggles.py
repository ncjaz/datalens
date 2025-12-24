from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from datalens.api.ui_commands import ShortcutTwoStateToggleBinding
from datalens.domain.plugin import PluginId
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.toggle import Toggle, ToggleOption

from .common import make_section_box


def build_toggles_section(
    parent: QWidget,
    *,
    theme: AppTheme,
    demo_toggle_binding: ShortcutTwoStateToggleBinding | None = None,
) -> QWidget:
    box = make_section_box(parent, "Toggles")
    layout = QGridLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setHorizontalSpacing(10)
    layout.setVerticalSpacing(10)

    row = 0
    if demo_toggle_binding is not None:
        demo = demo_toggle_binding.create_toggle(
            theme=theme,
            parent=box,
            plugin_id=PluginId("widget_test"),
        )
        layout.addWidget(QLabel("Shortcut-bound", box), row, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(demo, row, 1)
        row += 1

    toggle1 = Toggle(theme, ToggleOption("global", "Global"), ToggleOption("project", "Project"), parent=box)
    toggle2 = Toggle(theme, ToggleOption("off", "Off"), ToggleOption("on", "On"), parent=box)
    toggle3 = Toggle(theme, ToggleOption("a", "Option A"), ToggleOption("b", "Option B"), parent=box)
    toggle3.setEnabled(False)

    layout.addWidget(QLabel("Global/Project", box), row + 0, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
    layout.addWidget(toggle1, row + 0, 1)
    layout.addWidget(QLabel("Off/On", box), row + 1, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
    layout.addWidget(toggle2, row + 1, 1)
    layout.addWidget(QLabel("Disabled", box), row + 2, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
    layout.addWidget(toggle3, row + 2, 1)
    layout.setColumnStretch(1, 1)
    return box


__all__ = ["build_toggles_section"]
