from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QGridLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.icons.animated.autodiscovery import AutoDiscoveryAnimator
from datalens.ui.widgets.icons.animated.icon_animator import ButtonIconAnimator
from datalens.ui.widgets.icons.animated.refresh import RefreshAnimator
from datalens.ui.widgets.icons.annotation_toggle_icon import annotation_toggle_icon
from datalens.ui.widgets.icons.auto_icon import auto_icon
from datalens.ui.widgets.icons.autodiscovery_icon import autodiscovery_icon
from datalens.ui.widgets.icons.chevron_icon import chevron_icon
from datalens.ui.widgets.icons.eye_icon import eye_icon
from datalens.ui.widgets.icons.lock_icon import lock_icon
from datalens.ui.widgets.icons.refresh_icon import refresh_icon
from datalens.ui.widgets.icons.reset_icon import reset_icon
from datalens.ui.widgets.icons.settings_icon import settings_icon

from .common import make_section_box


def build_icons_section(
    parent: QWidget,
    *,
    theme: AppTheme,
    animators_out: list[ButtonIconAnimator],
) -> QWidget:
    box = make_section_box(parent, "Icons / Glyphs")
    layout = QGridLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setHorizontalSpacing(14)
    layout.setVerticalSpacing(12)

    icons: list[tuple[str, object]] = [
        ("Settings (themed)", settings_icon(theme, size=24)),
        ("AutoDiscovery (V1)", autodiscovery_icon(theme, size=24)),
        ("AutoDiscovery (Animated)", autodiscovery_icon(theme, size=24)),
        ("Refresh (themed)", refresh_icon(theme, size=24)),
        ("Refresh (Animated)", refresh_icon(theme, size=24)),
        ("Reset (V2)", reset_icon(theme, size=24)),
        ("AUTO (V2)", auto_icon(theme, size=24)),
        ("Chevron Up (V1)", chevron_icon(theme, direction="up", size=24)),
        ("Chevron Down (V1)", chevron_icon(theme, direction="down", size=24)),
        ("Chevron Left (V1)", chevron_icon(theme, direction="left", size=24)),
        ("Chevron Right (V1)", chevron_icon(theme, direction="right", size=24)),
        ("Jump Start (V1)", chevron_icon(theme, direction="left", size=24, bar="start")),
        ("Jump End (V1)", chevron_icon(theme, direction="right", size=24, bar="end")),
        ("Eye Open (V1)", eye_icon(theme, size=24, open=True)),
        ("Eye Closed (V1)", eye_icon(theme, size=24, open=False)),
        ("Lock Open (V1)", lock_icon(theme, size=24, open=True)),
        ("Lock Locked (V1)", lock_icon(theme, size=24, open=False)),
        ("Annotations Off (V1)", annotation_toggle_icon(theme, active=False, enabled=True, size=48)),
        ("Annotations On (V1)", annotation_toggle_icon(theme, active=True, enabled=True, size=48)),
    ]

    def add_cell(row: int, col: int, title: str, icon_obj) -> QWidget:
        cell = QWidget(box)
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setSpacing(4)

        btn = QToolButton(cell)
        btn.setIcon(icon_obj)
        btn.setIconSize(QSize(24, 24))
        btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        btn.setAutoRaise(True)
        btn.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        btn.setFocusPolicy(Qt.NoFocus)
        cell_layout.addWidget(btn, alignment=Qt.AlignHCenter)

        label = QLabel(title, cell)
        label.setAlignment(Qt.AlignHCenter)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
        cell_layout.addWidget(label)

        layout.addWidget(cell, row, col)
        return cell

    cols = 4
    for i, (name, icon_obj) in enumerate(icons):
        cell = add_cell(i // cols, i % cols, name, icon_obj)
        if name == "AutoDiscovery (Animated)":
            button = cell.findChild(QToolButton)
            if button is not None:
                animator = AutoDiscoveryAnimator(theme, size=24, parent=cell)
                animator.start(button)
                animators_out.append(animator)
        if name == "Refresh (Animated)":
            button = cell.findChild(QToolButton)
            if button is not None:
                animator = RefreshAnimator(theme, size=24, parent=cell)
                animator.start(button)
                animators_out.append(animator)

    for c in range(cols):
        layout.setColumnStretch(c, 1)
    return box


__all__ = ["build_icons_section"]
