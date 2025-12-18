from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
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
from datalens.services.plugins.registry import PluginOrigin, PluginRecord
from datalens.services.settings_store import default_settings_store
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

        detail_layout.addWidget(info_box)

        overrides_box = QGroupBox("Editable metadata (saved to settings.json)")
        overrides_form = QFormLayout(overrides_box)
        overrides_form.setLabelAlignment(Qt.AlignLeft)
        overrides_form.setHorizontalSpacing(16)
        overrides_form.setVerticalSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Override name (leave blank to keep manifest)")
        overrides_form.addRow("Name override", self._name_edit)

        self._author_edit = QLineEdit()
        self._author_edit.setPlaceholderText("Override author (blank clears)")
        overrides_form.addRow("Author override", self._author_edit)

        self._group_edit = QLineEdit()
        self._group_edit.setPlaceholderText("Override group (blank clears)")
        overrides_form.addRow("Group override", self._group_edit)

        self._nav_label_edit = QLineEdit()
        self._nav_label_edit.setMaxLength(2)
        self._nav_label_edit.setPlaceholderText("Override nav label (1-2 chars, blank clears)")
        overrides_form.addRow("Nav label override", self._nav_label_edit)

        self._desc_edit = QPlainTextEdit()
        self._desc_edit.setPlaceholderText("Override description (leave blank to keep manifest)")
        self._desc_edit.setFixedHeight(110)
        overrides_form.addRow("Description override", self._desc_edit)

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

    def closeEvent(self, event) -> None:
        self._persist_ui_state()
        super().closeEvent(event)

    def _restore_ui_state(self) -> None:
        self._settings_scope.restore_geometry("geometry", self)

    def _persist_ui_state(self) -> None:
        self._settings_scope.save_geometry("geometry", self)

    def _populate_list(self) -> None:
        self._list.clear()
        for record in self._plugins:
            label = f"{record.definition.name}  ({record.definition.id})"
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

        override = (self._settings.plugin_overrides or {}).get(str(record.definition.id))
        if override is None:
            override = PluginDefinitionOverride()

        self._name_edit.setText(override.name or "")
        self._author_edit.setText("" if override.author is None else override.author)
        self._group_edit.setText("" if override.group is None else override.group)
        self._nav_label_edit.setText("" if override.nav_label is None else override.nav_label)
        self._desc_edit.setPlainText(override.description or "")

    def _validate_override(self, record: PluginRecord, override: PluginDefinitionOverride) -> str | None:
        if override.name is not None and not override.name.strip():
            return "Name override cannot be empty. Clear it to use the manifest name."
        if override.description is not None and not override.description.strip():
            return "Description override cannot be empty. Clear it to use the manifest description."
        if override.nav_label is not None:
            text = override.nav_label.strip()
            if text and len(text) > 2:
                return "Nav label override must be 1-2 characters."
        return None

    def _save(self) -> None:
        record = self._current_record()
        if record is None:
            return

        override = PluginDefinitionOverride(
            name=self._name_edit.text().strip() or None,
            description=self._desc_edit.toPlainText().strip() or None,
            author=self._author_edit.text(),
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
                description=override.description,
                author=override.author if override.author is not None else None,
                group=override.group if override.group is not None else None,
                nav_label=override.nav_label if override.nav_label is not None else None,
            )
            if (
                payload.name is None
                and payload.description is None
                and payload.author is None
                and payload.group is None
                and payload.nav_label is None
            ):
                current.pop(plugin_id, None)
            else:
                current[plugin_id] = payload
            from dataclasses import replace

            return replace(s, plugin_overrides=current)

        self._settings = self._store.update(mutator)
        QMessageBox.information(self, "Saved", "Plugin overrides saved to settings.json.")

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
        self._render()

