from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from datalens.domain.plugin import PluginDefinition, PluginId
from datalens.ui.qt_settings import QSettingsScope


@dataclass(frozen=True)
class PluginNavItem:
    plugin_id: PluginId
    name: str
    nav_label: str
    icon_path: Path | None


def _derive_nav_label(name: str) -> str:
    words = [w for w in re.split(r"\s+", str(name).strip()) if w]
    if not words:
        return "?"
    if len(words) >= 2:
        label = (words[0][:1] + words[1][:1]).upper()
    else:
        label = words[0][:1].upper()
    return label or "?"


def _resolve_nav_label(defn: PluginDefinition) -> str:
    raw = getattr(defn, "nav_label", None)
    if isinstance(raw, str):
        raw = raw.strip().upper()
        if raw:
            return raw[:2]
    return _derive_nav_label(defn.name)


def nav_label_for(defn: PluginDefinition) -> str:
    """Return the 1-2 letter nav label for a plugin."""
    return _resolve_nav_label(defn)


def _make_letter_icon(label: str, *, size: int = 28) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    bg = QColor(255, 255, 255, 28)
    painter.setBrush(bg)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(0, 0, size, size, 6, 6)

    painter.setPen(QColor(255, 255, 255, 230))
    font = QFont()
    font.setBold(True)
    font.setPointSize(10)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignCenter, (label or "?")[:2].upper())
    painter.end()
    return QIcon(pix)


class PluginSidebar(QFrame):
    """
    Left navigation sidebar for switching between enabled plugin workspaces.

    Collapsed: icons/letters only.
    Expanded: icons/letters + text.
    """

    pluginSelected = Signal(object)  # PluginId

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PluginSidebar")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._settings = QSettingsScope(("ui", "main_window", "sidebar"))

        self._expanded = True
        self._items: list[PluginNavItem] = []
        self._buttons: dict[PluginId, QToolButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        self._root = root

        self._menu_button = QToolButton(self)
        self._menu_button.setObjectName("PluginSidebarMenuButton")
        self._menu_button.setAutoRaise(True)
        self._menu_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._menu_button.setIcon(self.style().standardIcon(QStyle.SP_TitleBarMenuButton))
        self._menu_button.setText("Menu")
        self._menu_button.setCursor(Qt.PointingHandCursor)
        self._menu_button.clicked.connect(self._toggle_expanded)

        self._divider_top = QFrame(self)
        self._divider_top.setFrameShape(QFrame.HLine)
        self._divider_top.setFrameShadow(QFrame.Sunken)

        self._items_container = QWidget(self)
        items_layout = QVBoxLayout(self._items_container)
        items_layout.setContentsMargins(0, 0, 0, 0)
        items_layout.setSpacing(6)
        self._items_layout = items_layout

        self._restore_ui_state()
        self._apply_width()
        self._apply_style()

        root.addWidget(self._menu_button, 0)
        root.addWidget(self._divider_top, 0)
        root.addWidget(self._items_container, 1)

    def set_items(self, items: list[PluginNavItem]) -> None:
        self._items = list(items)
        self._rebuild()

    def set_selected(self, plugin_id: PluginId | None) -> None:
        for pid, btn in list(self._buttons.items()):
            btn.setChecked(bool(plugin_id is not None and pid == plugin_id))

    def is_expanded(self) -> bool:
        return bool(self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self._apply_width()
        self._update_button_styles()
        self._persist_ui_state()

    def _toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)

    def _apply_width(self) -> None:
        self.setFixedWidth(240 if self._expanded else 64)
        self._menu_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if self._expanded else Qt.ToolButtonIconOnly)
        self._menu_button.setText("Menu" if self._expanded else "")
        self._menu_button.setToolTip("Collapse sidebar" if self._expanded else "Expand sidebar")

    def _restore_ui_state(self) -> None:
        try:
            with self._settings.open() as s:
                expanded = s.value("expanded", True)
            self._expanded = bool(expanded)
        except Exception:
            self._expanded = True

    def _persist_ui_state(self) -> None:
        try:
            with self._settings.open() as s:
                s.setValue("expanded", bool(self._expanded))
        except Exception:
            pass

    def _apply_style(self) -> None:
        palette = QApplication.palette()
        bg = palette.window().color()
        fg = palette.windowText().color()
        highlight = palette.highlight().color()
        highlight_text = palette.highlightedText().color()
        hover_bg = QColor(fg)
        hover_bg.setAlpha(18)
        border = QColor(fg)
        border.setAlpha(24)

        self.setStyleSheet(
            "\n".join(
                [
                    "#PluginSidebar {",
                    f"  background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, 255);",
                    f"  border-right: 1px solid rgba({border.red()}, {border.green()}, {border.blue()}, {border.alpha()});",
                    "}",
                    "#PluginSidebar QToolButton {",
                    "  border: none;",
                    "  padding: 8px 10px;",
                    "  border-radius: 10px;",
                    "}",
                    "#PluginSidebar QToolButton:hover {",
                    f"  background-color: rgba({hover_bg.red()}, {hover_bg.green()}, {hover_bg.blue()}, {hover_bg.alpha()});",
                    "}",
                    "#PluginSidebar QToolButton:checked {",
                    f"  background-color: rgba({highlight.red()}, {highlight.green()}, {highlight.blue()}, {highlight.alpha()});",
                    f"  color: rgba({highlight_text.red()}, {highlight_text.green()}, {highlight_text.blue()}, {highlight_text.alpha()});",
                    "}",
                    "#PluginSidebarMenuButton {",
                    "  font-weight: 600;",
                    "}",
                ]
            )
        )

    def _rebuild(self) -> None:
        # Remove existing plugin buttons.
        while self._items_layout.count():
            item = self._items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        for pid, btn in list(self._buttons.items()):
            btn.setParent(None)
            btn.deleteLater()
        self._buttons.clear()

        # Insert buttons into the items container.
        insert_at = 0
        for item in self._items:
            btn = QToolButton(self)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if self._expanded else Qt.ToolButtonIconOnly)
            btn.setText(item.name if self._expanded else "")
            btn.setIconSize(QSize(28, 28))
            btn.setIcon(self._icon_for(item))
            btn.setToolTip(item.name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, pid=item.plugin_id: self.pluginSelected.emit(pid))
            self._items_layout.insertWidget(insert_at, btn)
            insert_at += 1
            self._buttons[item.plugin_id] = btn

        self._items_layout.addStretch(1)
        self._update_button_styles()

    def _update_button_styles(self) -> None:
        style = Qt.ToolButtonTextBesideIcon if self._expanded else Qt.ToolButtonIconOnly
        for btn in self._buttons.values():
            btn.setToolButtonStyle(style)
            if not self._expanded:
                btn.setText("")
            else:
                # The tooltip stores the full name; use it as the label.
                btn.setText(btn.toolTip())

    def _icon_for(self, item: PluginNavItem) -> QIcon:
        if item.icon_path is not None and item.icon_path.exists():
            return QIcon(str(item.icon_path))
        return _make_letter_icon(item.nav_label)
