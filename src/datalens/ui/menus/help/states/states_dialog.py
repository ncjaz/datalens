from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from datalens.core.context import AppContext
from datalens.domain.plugin import PluginId
from datalens.domain.system.plugin_state import PluginStateEntry
from datalens.domain.system.system_info import GpuInfo, SystemInfoSnapshot
from datalens.domain.system.workspace_state import WorkspaceStateSnapshot
from datalens.ui.qt_settings import QSettingsScope


@dataclass
class _Versions:
    workspace: int = -1
    plugins: int = -1
    preferences: int = -1


class StatesDialog(QDialog):
    """
    Read-only inspector for core + plugin state.

    Intended as a lightweight diagnostics tool (Help -> States…).
    """

    def __init__(self, app_ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("States")
        self.setModal(False)
        self._settings_scope = QSettingsScope(("ui", "help", "states"))
        self._app_ctx = app_ctx
        self._versions = _Versions()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QLabel("States")
        header.setObjectName("StatesHeader")
        header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        root.addWidget(header)

        self._tree = QTreeWidget(self)
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Key", "Value", "Updated"])
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        root.addWidget(self._tree, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(500)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start()

        self._restore_ui_state()
        self.refresh(force=True)

    def closeEvent(self, event) -> None:
        self._persist_ui_state()
        super().closeEvent(event)

    def _restore_ui_state(self) -> None:
        self._settings_scope.restore_geometry("geometry", self)

    def _persist_ui_state(self) -> None:
        self._settings_scope.save_geometry("geometry", self)

    def refresh(self, *, force: bool = False) -> None:
        ws_v = self._app_ctx.workspace_state.version()
        ps_v = self._app_ctx.plugin_state.version()
        prefs_v = getattr(self._app_ctx.preferences, "version", lambda: -1)()
        if (
            not force
            and ws_v == self._versions.workspace
            and ps_v == self._versions.plugins
            and prefs_v == self._versions.preferences
        ):
            return
        self._versions.workspace = ws_v
        self._versions.plugins = ps_v
        self._versions.preferences = prefs_v

        self._tree.clear()
        self._add_core_section(self._app_ctx.workspace_state.snapshot())
        self._add_plugins_section()
        self._tree.expandToDepth(1)

    def _add_core_section(self, snapshot: WorkspaceStateSnapshot) -> None:
        root = QTreeWidgetItem(self._tree, ["Core", "", ""])
        root.setFirstColumnSpanned(True)

        def add(key: str, value: Any) -> None:
            QTreeWidgetItem(root, [key, self._fmt(value), ""])

        add("project_root", snapshot.project_root)
        add("active_workspace_id", snapshot.active_workspace_id)
        add("active_item_id", snapshot.active_item_id)
        self._add_system_info(root, snapshot.system_info)

    def _add_system_info(self, parent: QTreeWidgetItem, info: SystemInfoSnapshot | None) -> None:
        root = QTreeWidgetItem(parent, ["system_info", "", ""])
        root.setFirstColumnSpanned(True)
        if info is None:
            QTreeWidgetItem(root, ["(unavailable)", "", ""])
            return

        def add(key: str, value: Any) -> None:
            QTreeWidgetItem(root, [key, self._fmt(value), ""])

        add("os_name", info.os_name)
        add("os_release", info.os_release)
        add("os_version", info.os_version)
        add("machine", info.machine)
        add("cpu_arch", info.cpu_arch)
        add("cpu_bits", info.cpu_bits)
        add("cpu_count_logical", info.cpu_count_logical)
        add("python_version", info.python_version)
        add("ram_total_bytes", info.ram_total_bytes)
        self._add_gpus(root, info.gpus)

    def _add_gpus(self, parent: QTreeWidgetItem, gpus: tuple[GpuInfo, ...]) -> None:
        root = QTreeWidgetItem(parent, ["gpus", "", ""])
        root.setFirstColumnSpanned(True)
        if not gpus:
            QTreeWidgetItem(root, ["(none detected)", "", ""])
            return
        for i, gpu in enumerate(gpus, start=1):
            item = QTreeWidgetItem(root, [f"gpu_{i}", "", ""])
            item.setFirstColumnSpanned(True)
            QTreeWidgetItem(item, ["name", self._fmt(gpu.name), ""])
            QTreeWidgetItem(item, ["vram_total_bytes", self._fmt(gpu.vram_total_bytes), ""])

    def _add_plugins_section(self) -> None:
        root = QTreeWidgetItem(self._tree, ["Plugins", "", ""])
        root.setFirstColumnSpanned(True)

        snap = self._app_ctx.plugin_state.snapshot()
        prefs: dict[str, Any] = {}
        try:
            prefs = dict((self._app_ctx.preferences.snapshot() or {}).get("plugins", {}) or {})
        except Exception:
            prefs = {}

        plugin_ids = {str(pid) for pid in snap.entries.keys()}
        plugin_ids |= {str(pid) for pid in prefs.keys()}
        for pid in sorted(plugin_ids, key=lambda p: p.lower()):
            entries = snap.entries.get(PluginId(pid), {})
            self._add_plugin_state(root, PluginId(pid), entries, prefs.get(pid, {}))

    def _add_plugin_state(
        self,
        parent: QTreeWidgetItem,
        plugin_id: PluginId,
        entries: dict[str, PluginStateEntry],
        preferences: dict[str, Any] | None = None,
    ) -> None:
        plugin_item = QTreeWidgetItem(parent, [str(plugin_id), "", ""])
        plugin_item.setFirstColumnSpanned(True)
        for key in sorted(entries.keys(), key=lambda s: s.lower()):
            entry = entries[key]
            QTreeWidgetItem(
                plugin_item,
                [entry.key, self._fmt(entry.value), f"{entry.updated_at_monotonic:.3f}"],
            )

        prefs_root = QTreeWidgetItem(plugin_item, ["preferences", "", ""])
        prefs_root.setFirstColumnSpanned(True)
        prefs_data = dict(preferences or {})
        if not prefs_data:
            QTreeWidgetItem(prefs_root, ["(none)", "", ""])
        else:
            for key in sorted(prefs_data.keys(), key=lambda s: s.lower()):
                QTreeWidgetItem(prefs_root, [str(key), self._fmt(prefs_data.get(key)), ""])

    def _fmt(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        try:
            return str(value)
        except Exception:
            return "<unprintable>"
