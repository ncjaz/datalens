from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton

from .common import make_section_box


def build_buttons_section(
    parent: QWidget,
    *,
    theme: AppTheme,
    on_refresh_tooltip_demo: Callable[[DatalensButton | None], None],
    on_log_clicked: Callable[[], None],
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

    layout.setColumnStretch(1, 1)
    layout.setColumnStretch(2, 1)
    return box


__all__ = ["build_buttons_section"]

