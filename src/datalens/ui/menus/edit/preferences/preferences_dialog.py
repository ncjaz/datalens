from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from datalens.ui.qt_settings import QSettingsScope
from datalens.ui.menus.edit.preferences.pages.file_paths import FilePathsPage


@dataclass(frozen=True)
class PreferencesPageSpec:
    key: str
    title: str
    widget: QWidget


class PreferencesDialog(QDialog):
    """
    Preferences dialog (Edit -> Preferences).

    Uses a left-side navigation list + right-side stacked pages to achieve
    "vertical tabs with horizontal text" (more flexible than QTabWidget-West).
    """

    applied = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(False)

        self._settings_scope = QSettingsScope(("ui", "preferences"))

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QLabel("Preferences")
        header.setObjectName("PreferencesHeader")
        header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        self._splitter = splitter

        nav = QListWidget(splitter)
        nav.setObjectName("PreferencesNav")
        nav.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        nav.setFixedWidth(220)
        nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav.setSelectionMode(QListWidget.SingleSelection)
        self._nav = nav

        pages = QStackedWidget(splitter)
        pages.setObjectName("PreferencesPages")
        self._pages = pages

        self._page_specs: list[PreferencesPageSpec] = []
        self._add_page("file_paths", "File Paths", FilePathsPage())

        nav.currentRowChanged.connect(self._pages.setCurrentIndex)
        nav.setCurrentRow(0)

        root.addWidget(splitter, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply,
            parent=self,
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)  # type: ignore[union-attr]
        root.addWidget(buttons)

        self._restore_ui_state()

    def _add_page(self, key: str, title: str, widget: QWidget) -> None:
        spec = PreferencesPageSpec(key=key, title=title, widget=widget)
        self._page_specs.append(spec)
        self._pages.addWidget(widget)
        item = QListWidgetItem(title)
        item.setData(Qt.UserRole, key)
        self._nav.addItem(item)

    def _restore_ui_state(self) -> None:
        self._settings_scope.restore_geometry("geometry", self)
        self._settings_scope.restore_splitter("splitter", self._splitter)
        # Restore last selected page (best-effort).
        try:
            with self._settings_scope.open() as s:
                key = s.value("page_key")
            if isinstance(key, str) and key:
                for idx, spec in enumerate(self._page_specs):
                    if spec.key == key:
                        self._nav.setCurrentRow(idx)
                        break
        except Exception:
            pass

    def _persist_ui_state(self) -> None:
        self._settings_scope.save_geometry("geometry", self)
        self._settings_scope.save_splitter("splitter", self._splitter)
        try:
            row = int(self._nav.currentRow())
            key = self._page_specs[row].key if 0 <= row < len(self._page_specs) else ""
            with self._settings_scope.open() as s:
                s.setValue("page_key", key)
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self._persist_ui_state()
        super().closeEvent(event)

    def _on_apply(self) -> None:
        # TODO(v2): Apply semantic settings via SettingsStore/DebouncedSettingsWriter
        # once pages start exposing editable fields.
        self._persist_ui_state()
        self.applied.emit()

    def _on_ok(self) -> None:
        self._on_apply()
        self.accept()

