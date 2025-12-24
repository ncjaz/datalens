from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from datalens.api.ui_commands import ShortcutButtonBinding
from datalens.domain.plugin import PluginId
from datalens.ui.shortcuts import wire_button_to_binding
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton

from .common import make_section_box


def build_buttons_section(
    parent: QWidget,
    *,
    theme: AppTheme,
    on_refresh_tooltip_demo: Callable[[DatalensButton | None], None],
    on_log_clicked: Callable[[], None],
    count_to_10_binding: ShortcutButtonBinding | None = None,
) -> QWidget:
    box = make_section_box(parent, "Buttons")
    layout = QGridLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setHorizontalSpacing(10)
    layout.setVerticalSpacing(10)

    variants: list[tuple[str, ButtonVariant]] = [
        ("Primary", ButtonVariant.PRIMARY),
        ("Secondary", ButtonVariant.SECONDARY),
        ("Tertiary", ButtonVariant.TERTIARY),
        ("Confirm", ButtonVariant.CONFIRM),
        ("Cancel", ButtonVariant.CANCEL),
        ("Warning", ButtonVariant.WARNING),
    ]

    for row, (label, variant) in enumerate(variants):
        layout.addWidget(QLabel(label, box), row, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
        btn = DatalensButton(label, theme, variant, box)
        layout.addWidget(btn, row, 1)
        disabled = DatalensButton("Disabled", theme, variant, box)
        disabled.setEnabled(False)
        layout.addWidget(disabled, row, 2)

    tooltip_row = len(variants)
    layout.addWidget(
        QLabel("Tooltip", box),
        tooltip_row,
        0,
        alignment=Qt.AlignRight | Qt.AlignVCenter,
    )

    tooltip_demo = DatalensButton("Shortcut tooltip demo", theme, ButtonVariant.PRIMARY, box)
    tooltip_demo.setObjectName("WidgetTest:ShortcutTooltipDemo")
    on_refresh_tooltip_demo(tooltip_demo)
    tooltip_demo.clicked.connect(lambda *_: on_log_clicked())
    layout.addWidget(tooltip_demo, tooltip_row, 1, 1, 2)

    # Demonstrate wire_button_to_binding() pattern (manual button creation + wiring)
    if count_to_10_binding is not None:
        manual_row = tooltip_row + 1
        layout.addWidget(
            QLabel("Manual wire", box),
            manual_row,
            0,
            alignment=Qt.AlignRight | Qt.AlignVCenter,
        )

        # Create button with custom styling
        manual_btn = DatalensButton("Count (Manual)", theme, ButtonVariant.TERTIARY, box, outlined=True)
        manual_btn.setMinimumWidth(140)

        # Wire to binding (alternative to create_button() for custom styling)
        wire_button_to_binding(manual_btn, binding=count_to_10_binding, plugin_id=PluginId("widget_test"))

        layout.addWidget(manual_btn, manual_row, 1, 1, 2)

    layout.setColumnStretch(1, 1)
    layout.setColumnStretch(2, 1)
    return box


__all__ = ["build_buttons_section"]

