from __future__ import annotations

from dataclasses import dataclass
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from datalens.domain.plugin import PluginId
from datalens.domain.system.plugin_overrides import PluginDefinitionOverride
from datalens.core.events import EventHub, PluginDefinitionsChanged
from datalens.services.plugins.registry import PluginOrigin, PluginRecord
from datalens.services.settings_store import default_settings_store
from datalens.core.context import get_app_context
from datalens.ui.qt_settings import QSettingsScope


@dataclass
class _Fields:
    plugin_id: PluginId | None = None


class ManagePluginsDialog(QDialog):
    """
    Manage discovered plugins + edit per-plugin metadata overrides.

    This does not modify shipped plugin manifests on disk; edits are stored in
    `settings.json` under `plugin_overrides`.
    """

    def __init__(self, *, plugins: list[PluginRecord], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Plugins")
        self.setModal(False)
        self.resize(980, 640)
        self._settings_scope = QSettingsScope(("ui", "plugins", "manage_plugins"))

        self._plugins = sorted(plugins, key=lambda r: (str(r.location.origin), r.definition.name.lower()))
        self._store = default_settings_store()
        self._settings = self._store.load()
        self._active = _Fields()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QLabel("Manage Plugins")
        header.setObjectName("ManagePluginsHeader")
        header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        self._list = QListWidget(splitter)
        self._list.setMinimumWidth(260)
        self._list.currentItemChanged.connect(self._on_selected)

        detail = QWidget(splitter)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)

        info_box = QGroupBox("Plugin")
        info_form = QFormLayout(info_box)
        info_form.setLabelAlignment(Qt.AlignLeft)
        info_form.setHorizontalSpacing(16)
        info_form.setVerticalSpacing(8)

        self._id_label = QLabel("")
        self._id_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_form.addRow("ID", self._id_label)

        self._origin_label = QLabel("")
        info_form.addRow("Origin", self._origin_label)

        self._path_label = QLabel("")
        self._path_label.setWordWrap(True)
        self._path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_form.addRow("Path", self._path_label)

        self._kind_label = QLabel("")
        info_form.addRow("Kind", self._kind_label)

        self._version_label = QLabel("")
        info_form.addRow("Version", self._version_label)

        self._stage_label = QLabel("")
        info_form.addRow("Stage", self._stage_label)

        self._author_label = QLabel("")
        info_form.addRow("Author", self._author_label)

        self._desc_label = QPlainTextEdit()
        self._desc_label.setReadOnly(True)
        self._desc_label.setMinimumHeight(80)
        info_form.addRow("Description", self._desc_label)

        detail_layout.addWidget(info_box)

        overrides_box = QGroupBox("Editable metadata (saved to settings.json)")
        overrides_form = QFormLayout(overrides_box)
        overrides_form.setLabelAlignment(Qt.AlignLeft)
        overrides_form.setHorizontalSpacing(16)
        overrides_form.setVerticalSpacing(8)

        self._enabled_check = QCheckBox("Enabled (applies after restart or next project switch)")
        overrides_form.addRow("Enabled", self._enabled_check)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Override name (leave blank to keep manifest)")
        overrides_form.addRow("Name override", self._name_edit)

        self._group_edit = QLineEdit()
        self._group_edit.setPlaceholderText("Override group (leave blank to keep manifest)")
        overrides_form.addRow("Group override", self._group_edit)

        self._nav_label_edit = QLineEdit()
        self._nav_label_edit.setMaxLength(2)
        self._nav_label_edit.setPlaceholderText("Override nav label (1-2 chars, blank clears)")
        overrides_form.addRow("Nav label override", self._nav_label_edit)

        detail_layout.addWidget(overrides_box)

        hint = QLabel(
            "Note: overrides are applied to discovered plugin metadata. Some UI surfaces "
            "may require a restart to fully reflect changes."
        )
        hint.setWordWrap(True)
        detail_layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        self._save_btn = QPushButton("Save", self)
        buttons.addButton(self._save_btn, QDialogButtonBox.AcceptRole)
        self._reset_btn = QPushButton("Reset Overrides", self)
        buttons.addButton(self._reset_btn, QDialogButtonBox.ResetRole)
        buttons.rejected.connect(self.reject)
        self._save_btn.clicked.connect(self._save)
        self._reset_btn.clicked.connect(self._reset_overrides)
        root.addWidget(buttons)

        self._populate_list()
        self._restore_ui_state()

        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _effective_enabled_plugins(self) -> set[PluginId]:
        enabled = set(getattr(self._settings, "enabled_plugins", ()) or ())
        if enabled:
            return enabled
        # If settings.json doesn't exist yet (first run), default to manifest defaults.
        # Once settings exist, an empty set is treated as "explicitly none enabled".
        if not self._store.path.exists():
            return {r.definition.id for r in self._plugins if bool(getattr(r.definition, "enabled_by_default", True))}
        return set()

    def closeEvent(self, event) -> None:
        self._persist_ui_state()
        super().closeEvent(event)

    def _restore_ui_state(self) -> None:
        self._settings_scope.restore_geometry("geometry", self)

    def _persist_ui_state(self) -> None:
        self._settings_scope.save_geometry("geometry", self)

    def _populate_list(self) -> None:
        self._list.clear()
        enabled = self._effective_enabled_plugins()

        def group_key(record: PluginRecord) -> str:
            raw = getattr(record.definition, "group", None)
            if isinstance(raw, str) and raw.strip():
                return raw.strip().lower()
            return "zzzz"

        records = sorted(self._plugins, key=lambda r: (group_key(r), r.definition.name.lower()))
        for record in records:
            is_enabled = record.definition.id in enabled
            origin = "user" if record.location.origin == PluginOrigin.USER else "shipped"
            group_raw = getattr(record.definition, "group", None)
            group = str(group_raw).strip() if isinstance(group_raw, str) and group_raw.strip() else "Other"
            label = f"[{origin}] {group} / {record.definition.name}  ({record.definition.id})"
            if not is_enabled:
                label = f"{label}  [disabled]"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, str(record.definition.id))
            if record.location.origin == PluginOrigin.USER:
                item.setToolTip(str(record.location.root_dir))
            self._list.addItem(item)

    def _current_record(self) -> PluginRecord | None:
        pid = self._active.plugin_id
        if pid is None:
            return None
        for record in self._plugins:
            if record.definition.id == pid:
                return record
        return None

    def _on_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            self._active.plugin_id = None
            return
        pid_raw = current.data(Qt.UserRole)
        if not isinstance(pid_raw, str) or not pid_raw:
            self._active.plugin_id = None
            return
        self._active.plugin_id = PluginId(pid_raw)
        self._render()

    def _render(self) -> None:
        record = self._current_record()
        if record is None:
            return

        self._id_label.setText(str(record.definition.id))
        self._origin_label.setText(str(record.location.origin.value))
        self._path_label.setText(str(record.location.root_dir))

        kinds = sorted({f.kind.value for f in record.definition.features})
        self._kind_label.setText(", ".join(kinds) if kinds else "")
        self._version_label.setText(record.definition.version)
        self._stage_label.setText(record.definition.stage.value)
        self._author_label.setText(str(getattr(record.definition, "author", "") or ""))
        self._desc_label.setPlainText(str(getattr(record.definition, "description", "") or ""))

        override = (self._settings.plugin_overrides or {}).get(str(record.definition.id))
        if override is None:
            override = PluginDefinitionOverride()

        enabled = self._effective_enabled_plugins()
        self._enabled_check.setChecked(record.definition.id in enabled)

        self._name_edit.setText(override.name or "")
        self._group_edit.setText("" if override.group is None else override.group)
        self._nav_label_edit.setText("" if override.nav_label is None else override.nav_label)

    def _validate_override(self, record: PluginRecord, override: PluginDefinitionOverride) -> str | None:
        if override.name is not None and not override.name.strip():
            return "Name override cannot be empty. Clear it to use the manifest name."
        if override.nav_label is not None:
            text = override.nav_label.strip()
            if text and len(text) > 2:
                return "Nav label override must be 1-2 characters."
        return None

    def _save(self) -> None:
        record = self._current_record()
        if record is None:
            return

        is_enabled = bool(self._enabled_check.isChecked())
        override = PluginDefinitionOverride(
            name=self._name_edit.text().strip() or None,
            group=self._group_edit.text(),
            nav_label=self._nav_label_edit.text(),
        )

        error = self._validate_override(record, override)
        if error:
            QMessageBox.warning(self, "Invalid override", error)
            return

        plugin_id = str(record.definition.id)

        def mutator(s):
            current = dict(getattr(s, "plugin_overrides", {}) or {})
            # Only persist fields that are explicitly set; leaving a field blank
            # in the UI means "no override" for required fields.
            payload = PluginDefinitionOverride(
                name=override.name,
                group=override.group if override.group is not None else None,
                nav_label=override.nav_label if override.nav_label is not None else None,
            )
            if (
                payload.name is None
                and payload.group is None
                and payload.nav_label is None
            ):
                current.pop(plugin_id, None)
            else:
                current[plugin_id] = payload
            from dataclasses import replace

            enabled = set(getattr(s, "enabled_plugins", ()) or ())
            if not enabled and not self._store.path.exists():
                enabled = {r.definition.id for r in self._plugins if bool(getattr(r.definition, "enabled_by_default", True))}
            pid = PluginId(plugin_id)
            if is_enabled:
                enabled.add(pid)
            else:
                enabled.discard(pid)

            return replace(s, plugin_overrides=current, enabled_plugins=frozenset(enabled))

        self._settings = self._store.update(mutator)
        self._apply_overrides_live()
        self._publish_definitions_changed(plugin_ids=(PluginId(plugin_id),), fields=("enabled_plugins", "plugin_overrides"))
        self._populate_list()
        self._render()
        QMessageBox.information(
            self,
            "Saved",
            "Plugin settings saved to settings.json.\n\nChanges take effect after restart or next project switch.",
        )

    def _apply_overrides_live(self) -> None:
        """
        Best-effort: apply definition overrides to the in-memory plugin registry so
        group/name/nav label changes can re-sort UI lists immediately.

        This does not attempt runtime hot-reload of plugins; it only updates the
        discovered metadata surfaces.
        """
        try:
            app_ctx = get_app_context()
        except Exception:
            return
        host = getattr(app_ctx, "plugin_host", None)
        registry = getattr(host, "registry", None) if host is not None else None
        if registry is None:
            return
        try:
            registry.apply_definition_overrides(getattr(self._settings, "plugin_overrides", {}) or {})
        except Exception:
            return
        try:
            host.refresh_records_from_registry()
        except Exception:
            pass
        try:
            parent = self.parent()
            refresh = getattr(parent, "refresh_plugin_records_from_app_context", None)
            if callable(refresh):
                refresh()
        except Exception:
            pass
        try:
            self._plugins = sorted(registry.all(), key=lambda r: (str(r.location.origin), r.definition.name.lower()))
        except Exception:
            pass

    def _publish_definitions_changed(self, *, plugin_ids: tuple[PluginId, ...], fields: tuple[str, ...]) -> None:
        try:
            app_ctx = get_app_context()
        except Exception:
            return
        try:
            app_ctx.events.publish(
                EventHub.PLUGIN_DEFINITIONS_CHANGED,
                PluginDefinitionsChanged(
                    plugin_ids=tuple(plugin_ids),
                    fields=tuple(fields),
                    timestamp_s=time.time(),
                ),
            )
        except Exception:
            return

    def _reset_overrides(self) -> None:
        record = self._current_record()
        if record is None:
            return

        plugin_id = str(record.definition.id)

        def mutator(s):
            current = dict(getattr(s, "plugin_overrides", {}) or {})
            if plugin_id in current:
                current.pop(plugin_id, None)
            from dataclasses import replace

            return replace(s, plugin_overrides=current)

        self._settings = self._store.update(mutator)
        self._apply_overrides_live()
        self._publish_definitions_changed(plugin_ids=(PluginId(plugin_id),), fields=("plugin_overrides",))
        self._render()
        self._populate_list()
