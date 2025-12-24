from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QButtonGroup,
)

from datalens.api.tools import ToolDefinition, ToolHost, ToolKind
from datalens.core.logging import get_logger
from datalens.services.plugin_preferences_service import PluginPreferencesService
from datalens.ui.canvas.tools.base import CanvasTool
from datalens.ui.canvas.tools.tool_manager import ToolManager
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.icon_button import apply_icon_button_theme, create_icon_button
from datalens.ui.widgets.icons.lock_icon import lock_icon

log = get_logger(__name__)


@dataclass(frozen=True)
class _ToolOrderEntry:
    tool_id: str
    section: str
    order: int


class _ReorderDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        theme: AppTheme,
        tool_defs: dict[str, ToolDefinition],
        order: list[str],
        default_order: list[str],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Customize Tools")
        self.setModal(True)
        self._tool_defs = tool_defs
        self._order = list(order)
        self._default_order = list(default_order)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        subtitle = QLabel("Drag tools to reorder the toolbar.", self)
        subtitle.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.78)}; font-size: 11px;")
        layout.addWidget(subtitle)

        self._list = QListWidget(self)
        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self._list, 1)

        self._populate_list(self._order)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        reset_btn = QPushButton("Reset", self)
        buttons.addButton(reset_btn, QDialogButtonBox.ResetRole)
        layout.addWidget(buttons)

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        reset_btn.clicked.connect(self._reset)

    def _populate_list(self, order: Iterable[str]) -> None:
        self._list.clear()
        for tool_id in order:
            tool_def = self._tool_defs.get(tool_id)
            if tool_def is None:
                continue
            item = QListWidgetItem(f"{tool_def.label}  [{tool_def.section}]")
            item.setData(Qt.ItemDataRole.UserRole, tool_id)
            self._list.addItem(item)

    def _reset(self) -> None:
        self._populate_list(self._default_order)

    def tool_order(self) -> list[str]:
        result: list[str] = []
        for idx in range(self._list.count()):
            item = self._list.item(idx)
            tool_id = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(tool_id, str):
                result.append(tool_id)
        return result


class ToolsToolbar(QFrame):
    def __init__(
        self,
        *,
        tool_definitions: list[ToolDefinition],
        canvas_type: str,
        canvas_host: ToolHost,
        theme: AppTheme,
        plugin_id: str,
        preferences: PluginPreferencesService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._canvas_host = canvas_host
        self._plugin_id = str(plugin_id)
        self._preferences = preferences
        self._tool_defs = {
            td.tool_id: td for td in tool_definitions if canvas_type in td.canvas_types
        }
        self._tool_instances: dict[str, CanvasTool] = {}
        self._buttons: dict[str, QToolButton] = {}
        self._mode_button_group = QButtonGroup(self)
        self._mode_button_group.setExclusive(True)
        self._dividers: list[QFrame] = []
        self._tool_order: list[str] = []
        self._lock_button: QToolButton | None = None
        self._tool_unsub: Callable[[], None] | None = None

        self.setObjectName("ToolsToolbar")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)

        self._update_shell_stylesheet()
        self._load_toolbar_order()
        self._rebuild_layout()
        self._restore_initial_state()
        self._subscribe_tool_manager()

        log.info(
            "Tools toolbar ready",
            extra={
                "operation": "tools",
                "phase": "toolbar_ready",
                "plugin_id": self._plugin_id,
                "canvas_type": str(canvas_type),
                "tool_count": len(self._tool_defs),
            },
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._unsubscribe_tool_manager()
        super().closeEvent(event)

    def update_theme(self, theme: AppTheme) -> None:
        self._theme = theme
        self._update_shell_stylesheet()
        for button in self._buttons.values():
            apply_icon_button_theme(button, theme)
        for tool_id, tool_def in self._tool_defs.items():
            button = self._buttons.get(tool_id)
            if button is not None:
                button.setIcon(tool_def.icon_factory(theme))
        for divider in self._dividers:
            divider.setStyleSheet(self._divider_stylesheet())
        if self._lock_button is not None:
            checked = bool(self._lock_button.isChecked())
            self._lock_button.setIcon(lock_icon(theme, size=18, open=checked))

    def _update_shell_stylesheet(self) -> None:
        background = self._theme.with_alpha_hex(self._theme.secondary_color, 0.82)
        self.setStyleSheet(
            "QFrame#ToolsToolbar {"
            f"background-color: {background};"
            "border-radius: 18px;"
            "padding: 8px;"
            "}"
        )

    def _divider_stylesheet(self) -> str:
        return (
            "QFrame {"
            f"background-color: {self._theme.with_alpha_hex(self._theme.secondary_color, 0.3)};"
            "max-height: 1px;"
            "margin: 4px 8px;"
            "}"
        )

    def _subscribe_tool_manager(self) -> None:
        manager = getattr(self._canvas_host, "tools", None)
        if not isinstance(manager, ToolManager):
            return
        self._tool_unsub = manager.subscribe(self._on_active_tool_changed)

    def _unsubscribe_tool_manager(self) -> None:
        unsub = self._tool_unsub
        self._tool_unsub = None
        if callable(unsub):
            try:
                unsub()
            except Exception:
                pass

    def _on_active_tool_changed(self, tool: CanvasTool | None) -> None:
        tool_id = getattr(tool, "tool_id", None)
        if tool_id not in self._buttons:
            self._set_mode_checked(None)
            return
        tool_def = self._tool_defs.get(tool_id)
        if tool_def is None or tool_def.kind is not ToolKind.MODE:
            return
        self._set_mode_checked(tool_id)
        self._save_preference(self._pref_key("active_mode_id"), tool_id)

    def _load_preference(self, key: str, default: object) -> object:
        if self._preferences is None:
            return default
        try:
            return self._preferences.get(self._plugin_id, key, default=default)
        except Exception:
            log.debug(
                "Tools toolbar preference read failed (best-effort)",
                exc_info=True,
                extra={"operation": "tools", "phase": "prefs_get_error", "key": key},
            )
            return default

    def _save_preference(self, key: str, value: object) -> None:
        if self._preferences is None:
            return
        try:
            self._preferences.set(self._plugin_id, key, value)
        except Exception:
            log.debug(
                "Tools toolbar preference write failed (best-effort)",
                exc_info=True,
                extra={"operation": "tools", "phase": "prefs_set_error", "key": key},
            )

    def _pref_key(self, suffix: str) -> str:
        return f"tools.{suffix}".strip(".")

    def _load_toolbar_order(self) -> None:
        stored = self._load_preference(self._pref_key("toolbar.order"), None)
        default_order = self._compute_default_order()

        if stored is None:
            self._tool_order = list(default_order)
            self._save_preference(self._pref_key("toolbar.order"), list(self._tool_order))
            return

        if isinstance(stored, (list, tuple)):
            persisted = [str(x) for x in stored if isinstance(x, str)]
        else:
            persisted = []
        self._tool_order = self._merge_order(persisted, default_order)

    def _compute_default_order(self) -> list[str]:
        entries: list[_ToolOrderEntry] = []
        for tool_def in self._tool_defs.values():
            entries.append(_ToolOrderEntry(tool_def.tool_id, tool_def.section, tool_def.default_order))

        sections: dict[str, list[_ToolOrderEntry]] = {}
        for entry in entries:
            sections.setdefault(entry.section, []).append(entry)

        for items in sections.values():
            items.sort(key=lambda item: (item.order, item.tool_id))

        section_order = sorted(
            sections.items(),
            key=lambda item: (min(e.order for e in item[1]), item[0]),
        )

        result: list[str] = []
        for _, items in section_order:
            result.extend([entry.tool_id for entry in items])
        return result

    def _merge_order(self, persisted: list[str], defaults: list[str]) -> list[str]:
        ordered = [tool_id for tool_id in persisted if tool_id in self._tool_defs]
        for tool_id in defaults:
            if tool_id not in ordered:
                ordered.append(tool_id)
        return ordered

    def _rebuild_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self._dividers.clear()
        previous_section: str | None = None

        for tool_id in self._tool_order:
            tool_def = self._tool_defs.get(tool_id)
            if tool_def is None:
                continue
            if previous_section is not None and tool_def.section != previous_section:
                divider = QFrame(self)
                divider.setFrameShape(QFrame.HLine)
                divider.setStyleSheet(self._divider_stylesheet())
                self._dividers.append(divider)
                self._layout.addWidget(divider)
            button = self._ensure_button(tool_def)
            self._layout.addWidget(button)
            previous_section = tool_def.section

        self._layout.addStretch(1)

        if self._lock_button is None:
            lock_btn = create_icon_button(self._theme, self, size=36, icon_size=18, checkable=True)
            lock_btn.setIcon(lock_icon(self._theme, size=18, open=False))
            lock_btn.setToolTip("Reorder tools")
            lock_btn.toggled.connect(self._on_lock_toggled)
            self._lock_button = lock_btn
        self._layout.addWidget(self._lock_button)

    def _ensure_button(self, tool_def: ToolDefinition) -> QToolButton:
        existing = self._buttons.get(tool_def.tool_id)
        if existing is not None:
            return existing

        checkable = tool_def.kind is not ToolKind.ACTION
        button = create_icon_button(self._theme, self, checkable=checkable)
        button.setIcon(tool_def.icon_factory(self._theme))
        button.setToolTip(tool_def.tooltip)
        button.setObjectName(f"ToolsToolbar:{tool_def.tool_id}")

        if tool_def.kind is ToolKind.MODE:
            self._mode_button_group.addButton(button)
            button.clicked.connect(lambda _checked=False, tid=tool_def.tool_id: self._activate_mode_tool(tid))
        elif tool_def.kind is ToolKind.ACTION:
            button.clicked.connect(lambda _checked=False, tid=tool_def.tool_id: self._execute_action_tool(tid))
        else:
            button.toggled.connect(lambda checked, tid=tool_def.tool_id: self._toggle_tool(tid, checked))

        self._buttons[tool_def.tool_id] = button
        return button

    def _restore_initial_state(self) -> None:
        for tool_id, tool_def in self._tool_defs.items():
            if tool_def.kind is not ToolKind.TOGGLE:
                continue
            button = self._buttons.get(tool_id)
            if button is None:
                continue
            checked = bool(self._load_preference(self._pref_key(f"{tool_id}.enabled"), False))
            button.blockSignals(True)
            button.setChecked(checked)
            button.blockSignals(False)
            if checked:
                self._toggle_tool(tool_id, checked, persist=False, log_event=False)

        active_tool_id = None
        manager = getattr(self._canvas_host, "tools", None)
        if isinstance(manager, ToolManager):
            active_tool_id = getattr(manager.active_tool, "tool_id", None)

        if active_tool_id and active_tool_id in self._buttons:
            self._set_mode_checked(active_tool_id)
            return

        preferred = self._load_preference(self._pref_key("active_mode_id"), None)
        if isinstance(preferred, str) and preferred in self._tool_defs:
            tool_def = self._tool_defs.get(preferred)
            if tool_def is not None and tool_def.kind is ToolKind.MODE:
                self._activate_mode_tool(preferred, log_event=False)
                return

        for tool_id in self._tool_order:
            tool_def = self._tool_defs.get(tool_id)
            if tool_def is not None and tool_def.kind is ToolKind.MODE:
                self._activate_mode_tool(tool_id, log_event=False)
                return

    def _set_mode_checked(self, tool_id: str | None) -> None:
        for tid, button in self._buttons.items():
            tool_def = self._tool_defs.get(tid)
            if tool_def is None or tool_def.kind is not ToolKind.MODE:
                continue
            button.blockSignals(True)
            button.setChecked(bool(tool_id) and tid == tool_id)
            button.blockSignals(False)

    def _get_or_create_tool(self, tool_id: str) -> CanvasTool | None:
        if tool_id in self._tool_instances:
            return self._tool_instances[tool_id]

        tool_def = self._tool_defs.get(tool_id)
        if tool_def is None:
            log.error(
                "Tool missing from definitions",
                extra={"operation": "tools", "phase": "tool_missing", "tool_id": tool_id},
            )
            return None

        try:
            tool = tool_def.create(self._canvas_host)
        except Exception:
            log.error(
                "Failed to create tool",
                exc_info=True,
                extra={"operation": "tools", "phase": "tool_create_error", "tool_id": tool_id},
            )
            button = self._buttons.get(tool_id)
            if button is not None:
                button.setEnabled(False)
            return None

        self._tool_instances[tool_id] = tool
        return tool

    def _activate_mode_tool(self, tool_id: str, *, log_event: bool = True) -> None:
        tool_def = self._tool_defs.get(tool_id)
        if tool_def is None or tool_def.kind is not ToolKind.MODE:
            return
        tool = self._get_or_create_tool(tool_id)
        if tool is None:
            return
        manager = getattr(self._canvas_host, "tools", None)
        if isinstance(manager, ToolManager):
            manager.set_active(tool)
        self._save_preference(self._pref_key("active_mode_id"), tool_id)
        if log_event:
            log.info(
                "Mode tool activated",
                extra={"operation": "tools", "phase": "mode_activate", "tool_id": tool_id, "plugin_id": self._plugin_id},
            )

    def _execute_action_tool(self, tool_id: str) -> None:
        tool_def = self._tool_defs.get(tool_id)
        if tool_def is None or tool_def.kind is not ToolKind.ACTION:
            return
        try:
            tool = tool_def.create(self._canvas_host)
        except Exception:
            log.error(
                "Failed to create action tool",
                exc_info=True,
                extra={"operation": "tools", "phase": "action_create_error", "tool_id": tool_id},
            )
            return

        execute = getattr(tool, "execute", None)
        if not callable(execute):
            log.warning(
                "Action tool missing execute()",
                extra={"operation": "tools", "phase": "action_missing_execute", "tool_id": tool_id},
            )
            return

        try:
            execute()
        except Exception:
            log.warning(
                "Action tool failed",
                exc_info=True,
                extra={"operation": "tools", "phase": "action_error", "tool_id": tool_id},
            )
            return

        log.info(
            "Action tool executed",
            extra={"operation": "tools", "phase": "action_execute", "tool_id": tool_id, "plugin_id": self._plugin_id},
        )

    def _toggle_tool(self, tool_id: str, checked: bool, *, persist: bool = True, log_event: bool = True) -> None:
        tool_def = self._tool_defs.get(tool_id)
        if tool_def is None or tool_def.kind is not ToolKind.TOGGLE:
            return
        tool = self._get_or_create_tool(tool_id)
        if tool is None:
            return
        setter = getattr(tool, "set_enabled", None)
        if callable(setter):
            try:
                setter(bool(checked))
            except Exception:
                log.warning(
                    "Toggle tool failed",
                    exc_info=True,
                    extra={"operation": "tools", "phase": "toggle_error", "tool_id": tool_id},
                )
        else:
            log.warning(
                "Toggle tool missing set_enabled()",
                extra={"operation": "tools", "phase": "toggle_missing_setter", "tool_id": tool_id},
            )

        if persist:
            self._save_preference(self._pref_key(f"{tool_id}.enabled"), bool(checked))

        if log_event:
            log.info(
                "Toggle tool updated",
                extra={
                    "operation": "tools",
                    "phase": "toggle_set",
                    "tool_id": tool_id,
                    "checked": bool(checked),
                    "plugin_id": self._plugin_id,
                },
            )

    def _on_lock_toggled(self, checked: bool) -> None:
        if self._lock_button is not None:
            self._lock_button.setIcon(lock_icon(self._theme, size=18, open=bool(checked)))

        if not checked:
            return

        dialog = _ReorderDialog(
            self,
            theme=self._theme,
            tool_defs=self._tool_defs,
            order=self._tool_order,
            default_order=self._compute_default_order(),
        )
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            new_order = dialog.tool_order()
            if new_order:
                self._tool_order = self._merge_order(new_order, self._compute_default_order())
                self._save_preference(self._pref_key("toolbar.order"), list(self._tool_order))
                self._rebuild_layout()
                log.info(
                    "Tools toolbar reordered",
                    extra={
                        "operation": "tools",
                        "phase": "toolbar_reorder",
                        "plugin_id": self._plugin_id,
                        "tool_count": len(self._tool_order),
                    },
                )

        if self._lock_button is not None:
            self._lock_button.blockSignals(True)
            self._lock_button.setChecked(False)
            self._lock_button.blockSignals(False)
            self._lock_button.setIcon(lock_icon(self._theme, size=18, open=False))


__all__ = ["ToolsToolbar"]
