from __future__ import annotations

from pathlib import Path
from dataclasses import replace

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QVBoxLayout,
    QWidget,
)

from datalens.infra.paths import datalens_user_data_dir
from datalens.services.settings_store import default_debounced_settings_writer, default_settings_store


class FilePathsPage(QWidget):
    """
    Preferences page: File paths.

    This is informational (read-only) for now. It helps users locate key
    app/user-scoped files without digging through docs.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._store = default_settings_store()
        self._writer = default_debounced_settings_writer()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("File Paths")
        title.setObjectName("PreferencesTitle")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(title)

        settings = self._store.load()
        default_user_dir = datalens_user_data_dir()
        effective_user_dir = settings.user_data_dir or default_user_dir

        self._user_data_dir_edit = QLineEdit(str(effective_user_dir))
        self._user_data_dir_edit.setPlaceholderText(str(default_user_dir))
        self._user_data_dir_edit.setClearButtonEnabled(True)

        browse_btn = QPushButton("Browse\u2026")
        browse_btn.clicked.connect(self._browse_user_data_dir)

        open_btn = QPushButton("Open in Explorer")
        open_btn.clicked.connect(self._open_user_data_dir)

        user_dir_row = QHBoxLayout()
        user_dir_row.setContentsMargins(0, 0, 0, 0)
        user_dir_row.setSpacing(8)
        user_dir_row.addWidget(self._user_data_dir_edit, 1)
        user_dir_row.addWidget(browse_btn)

        layout.addLayout(user_dir_row)
        layout.addWidget(open_btn, alignment=Qt.AlignLeft)

        hint = QLabel(f"Leave blank to use the default: {default_user_dir}")
        hint.setWordWrap(True)
        hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)

        settings_path = self._store.path
        self._settings_path_edit = QLineEdit(str(settings_path))
        self._settings_path_edit.setReadOnly(True)

        form.addRow("Settings file", self._settings_path_edit)

        layout.addLayout(form)
        layout.addStretch(1)

        self._user_data_dir_edit.editingFinished.connect(self._persist_user_data_dir)

    def _effective_user_data_dir(self) -> Path:
        raw = self._user_data_dir_edit.text().strip()
        if not raw:
            return datalens_user_data_dir()
        return Path(raw)

    def _persist_user_data_dir(self) -> None:
        raw = self._user_data_dir_edit.text().strip()
        value = Path(raw) if raw else None

        def mutator(current):
            return replace(current, user_data_dir=value)

        self._writer.request_update(mutator)

        # Refresh the field to show the effective directory when cleared.
        if value is None:
            self._user_data_dir_edit.setText(str(datalens_user_data_dir()))

    def _browse_user_data_dir(self) -> None:
        start_dir = str(self._effective_user_data_dir())
        directory = QFileDialog.getExistingDirectory(self, "Select user data directory", start_dir)
        if not directory:
            return
        self._user_data_dir_edit.setText(directory)
        self._persist_user_data_dir()

    def _open_user_data_dir(self) -> None:
        path = self._effective_user_data_dir()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
