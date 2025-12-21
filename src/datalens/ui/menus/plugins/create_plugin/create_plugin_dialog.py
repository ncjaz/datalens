from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from datalens.domain.plugin import PluginKind, PluginStage
from datalens.ui.qt_settings import QSettingsScope


@dataclass(frozen=True)
class NewPluginManifestDraft:
    """
    UI-only draft values for a `manifest.json`.
    Used by the Plugins menu to scaffold a new plugin folder.
    """

    plugin_id: str
    name: str
    version: str
    stage: PluginStage
    kind: PluginKind
    description: str
    author: str
    nav_label: str = ""


class CreatePluginDialog(QDialog):
    """
    Dialog for collecting new plugin manifest fields.

    This dialog collects fields used for plugin scaffolding.
    """

    def __init__(self, *, plugin_root_dir, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create New Plugin")
        self.setModal(True)
        self._settings_scope = QSettingsScope(("ui", "plugins", "create_plugin"))
        self._plugin_root_dir = plugin_root_dir

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QLabel("Create New Plugin")
        header.setObjectName("CreatePluginHeader")
        header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        root.addWidget(header)

        dest = QLabel(f"Destination: {self._plugin_root_dir}")
        dest.setWordWrap(True)
        dest.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(dest)

        form_box = QGroupBox("Manifest fields")
        form_layout = QFormLayout(form_box)
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)
        form_layout.setHorizontalSpacing(16)
        form_layout.setVerticalSpacing(8)

        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("e.g. annotation_tools")
        self._id_edit.setToolTip("Lowercase letters/numbers, underscores or dashes (2-64 chars).")
        self._id_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[a-z0-9][a-z0-9_-]{1,63}$")))
        form_layout.addRow("Plugin ID", self._id_edit)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Human-readable name")
        form_layout.addRow("Name", self._name_edit)

        self._version_edit = QLineEdit("0.1.0")
        form_layout.addRow("Version", self._version_edit)

        self._stage_combo = QComboBox()
        self._stage_combo.addItems([s.value for s in PluginStage])
        self._stage_combo.setCurrentText(PluginStage.DEV.value)
        form_layout.addRow("Stage", self._stage_combo)

        self._kind_combo = QComboBox()
        self._kind_combo.addItems([k.value for k in PluginKind])
        self._kind_combo.setCurrentText(PluginKind.WORKSPACE.value)
        form_layout.addRow("Kind", self._kind_combo)

        self._author_edit = QLineEdit()
        self._author_edit.setPlaceholderText("Name or org")
        form_layout.addRow("Author", self._author_edit)

        self._nav_label_edit = QLineEdit()
        self._nav_label_edit.setPlaceholderText("Optional (1-2 letters)")
        self._nav_label_edit.setMaxLength(2)
        form_layout.addRow("Nav label", self._nav_label_edit)

        self._desc_edit = QPlainTextEdit()
        self._desc_edit.setPlaceholderText("Short description (optional)")
        self._desc_edit.setFixedHeight(90)
        form_layout.addRow("Description", self._desc_edit)

        root.addWidget(form_box)

        hint = QLabel("After creation, restart DataLens to discover and enable the new plugin.")
        hint.setWordWrap(True)
        hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._restore_ui_state()

    def closeEvent(self, event) -> None:
        self._persist_ui_state()
        super().closeEvent(event)

    def _on_accept(self) -> None:
        from datalens.services.plugins.scaffold import PluginScaffoldError, validate_plugin_id

        raw = self._id_edit.text().strip().lower()
        self._id_edit.setText(raw)
        try:
            validate_plugin_id(raw)
        except PluginScaffoldError as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Invalid Plugin ID", str(exc))
            self._id_edit.setFocus()
            self._id_edit.selectAll()
            return
        self.accept()

    def _restore_ui_state(self) -> None:
        self._settings_scope.restore_geometry("geometry", self)

    def _persist_ui_state(self) -> None:
        self._settings_scope.save_geometry("geometry", self)

    def draft(self) -> NewPluginManifestDraft:
        return NewPluginManifestDraft(
            plugin_id=self._id_edit.text().strip().lower(),
            name=self._name_edit.text().strip(),
            version=self._version_edit.text().strip(),
            stage=PluginStage(str(self._stage_combo.currentText()).strip()),
            kind=PluginKind(str(self._kind_combo.currentText()).strip()),
            description=self._desc_edit.toPlainText().strip(),
            author=self._author_edit.text().strip(),
            nav_label=self._nav_label_edit.text().strip().upper(),
        )
