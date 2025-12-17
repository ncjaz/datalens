from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from datalens.ui.project_dialogs import choose_existing_project_root, choose_new_project_root
from datalens.ui.theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton


class WelcomeProjectsPanel(QFrame):
    """
    Project selection panel used by the welcome screen.

    This panel owns all UI for:
    - listing recent projects
    - typing/pasting a project path
    - creating/opening a project folder via dialogs

    It emits `projectSelected(Path|None)` when the current selection changes and
    `continueRequested()` when the user double-clicks a recent project.
    """

    projectSelected = Signal(object)  # Path | None
    continueRequested = Signal()

    def __init__(
        self,
        *,
        theme: AppTheme,
        recent_projects: tuple[Path, ...],
        selected_project_root: Path | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WelcomeProjectsPanel")
        self._theme = theme
        self._selected_project_root: Path | None = selected_project_root

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(10)

        title = QLabel("Project", self)
        title.setStyleSheet("font-size: 13px; font-weight: 700;")
        layout.addWidget(title)

        hint = QLabel(
            "Choose a recent project, or create/open a project folder.",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.75)}; font-size: 12px;")
        layout.addWidget(hint)

        self._recent_projects_list = QListWidget(self)
        self._recent_projects_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._recent_projects_list.setAlternatingRowColors(True)
        self._recent_projects_list.itemSelectionChanged.connect(self._on_recent_selected)
        self._recent_projects_list.itemDoubleClicked.connect(lambda *_: self.continueRequested.emit())
        layout.addWidget(self._recent_projects_list, 1)

        self.set_recent_projects(recent_projects)

        row = QWidget(self)
        grid = QGridLayout(row)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        self._project_path_edit = QLineEdit(row)
        self._project_path_edit.setPlaceholderText("Project path (paste or browse)")
        self._project_path_edit.textChanged.connect(self._on_path_text_changed)
        if selected_project_root:
            self._project_path_edit.setText(str(selected_project_root))
        grid.addWidget(self._project_path_edit, 0, 0)

        actions = QWidget(row)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)

        new_btn = DatalensButton("New", self._theme, ButtonVariant.PRIMARY, None)
        new_btn.clicked.connect(self._create_new_project)
        actions_layout.addWidget(new_btn)

        open_btn = DatalensButton("Open", self._theme, ButtonVariant.PRIMARY, None)
        open_btn.clicked.connect(self._open_existing_project)
        actions_layout.addWidget(open_btn)

        grid.addWidget(actions, 0, 1)
        layout.addWidget(row)

        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def selected_project_root(self) -> Path | None:
        return self._selected_project_root

    def set_selected_project_root(self, path: Path | None) -> None:
        self._selected_project_root = path
        self._project_path_edit.setText(str(path) if path else "")
        self.projectSelected.emit(path)

    def set_recent_projects(self, recent_projects: tuple[Path, ...]) -> None:
        self._recent_projects_list.clear()
        if not recent_projects:
            placeholder = QListWidgetItem("No recent projects yet.")
            placeholder.setFlags(Qt.NoItemFlags)
            self._recent_projects_list.addItem(placeholder)
            return

        for path in recent_projects:
            item = QListWidgetItem(str(path))
            item.setToolTip(str(path))
            item.setData(int(Qt.UserRole), str(path))
            self._recent_projects_list.addItem(item)

    def _path_from_edit(self) -> Path | None:
        raw = self._project_path_edit.text().strip()
        if not raw:
            return None
        try:
            return Path(raw)
        except Exception:
            return None

    def _best_dialog_start_dir(self) -> Path | None:
        """
        Return a directory path to use as the initial folder for file dialogs.

        If the user typed a path, try to start there (or its parent) when it exists.
        """
        p = self._path_from_edit()
        if p is None:
            return None
        try:
            if p.exists() and p.is_dir():
                return p
            parent = p.parent
            if parent.exists() and parent.is_dir():
                return parent
        except Exception:
            return None
        return None

    def _on_path_text_changed(self) -> None:
        p = self._path_from_edit()
        if p is None:
            if self._selected_project_root is not None:
                self._selected_project_root = None
                self.projectSelected.emit(None)
            return
        try:
            if p.exists() and p.is_dir():
                self._selected_project_root = p
                self.projectSelected.emit(p)
        except Exception:
            pass

    def _on_recent_selected(self) -> None:
        items = self._recent_projects_list.selectedItems()
        if not items:
            return
        raw = items[0].data(int(Qt.UserRole))
        if not isinstance(raw, str) or not raw:
            return
        self.set_selected_project_root(Path(raw))

    def _open_existing_project(self) -> None:
        selected = choose_existing_project_root(
            parent=self,
            start_dir=self._best_dialog_start_dir(),
            typed_path=self._path_from_edit(),
        )
        if selected is None:
            return
        self.set_selected_project_root(selected)

    def _create_new_project(self) -> None:
        selected = choose_new_project_root(
            parent=self,
            start_dir=self._best_dialog_start_dir(),
            typed_path=self._path_from_edit(),
        )
        if selected is None:
            return
        self.set_selected_project_root(selected)

