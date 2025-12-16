from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from datalens.domain.plugin import PluginDefinition, PluginId, PluginStage
from datalens.domain.settings import AppSettings
from datalens.domain.user_profile import UserProfile
from datalens.services.settings_store import default_debounced_settings_writer
from datalens.ui.qt_settings import qsettings, restore_geometry, restore_splitter, save_geometry, save_splitter
from datalens.ui.theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton
from datalens.ui.widgets.core.checkboxes import DatalensCheckBox
from datalens.ui.welcome.profile import ProfileEditDialog, ProfileSummary


class WelcomeWindow(QDialog):
    """
    Welcome dialog shown after pre-welcome startup initialization.

    Layout mirrors the V1 two-column welcome screen:
    - Left: project selection / recents (placeholder in V2 for now)
    - Right: plugin/workspace selection

    The user's selection is persisted to :class:`~datalens.domain.settings.AppSettings`
    so ``--skip-welcome`` can restore the last selection.
    """

    def __init__(
        self,
        *,
        theme: AppTheme,
        settings: AppSettings,
        plugins: tuple[PluginDefinition, ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to DataLens")
        self.setModal(True)
        # This dialog is a short-lived launcher; ensure it is destroyed promptly
        # on accept/reject so it can't leave behind hidden widget trees.
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(960, 560)

        self._theme = theme
        self._settings = settings
        self._plugins = plugins
        self._selected_project_root: Path | None = settings.last_project_root
        self._profile_summary: ProfileSummary | None = None
        self._recent_projects_list: QListWidget | None = None
        self._settings_writer = default_debounced_settings_writer(debounce_seconds=0.25)
        self._splitter: QSplitter | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(0)

        # ------------------------------------------------------------------
        # Left column (projects)
        # ------------------------------------------------------------------

        left_widget = QWidget(self)
        left_column = QVBoxLayout(left_widget)
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(12)

        header = QLabel("DataLens", left_widget)
        header.setStyleSheet("font-size: 26px; font-weight: 700;")
        left_column.addWidget(header)

        subheader = QLabel(
            "Select how you would like to start today. Recent projects will appear here.",
            left_widget,
        )
        subheader.setWordWrap(True)
        subheader.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.80)}; font-size: 13px;")
        left_column.addWidget(subheader)

        profile_summary = ProfileSummary(theme, settings.user_profile or UserProfile(), left_widget)
        profile_summary.editRequested.connect(self._edit_profile)
        self._profile_summary = profile_summary
        left_column.addWidget(profile_summary)

        projects_panel = self._build_projects_panel()
        left_column.addWidget(projects_panel, 1)

        left_column.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # ------------------------------------------------------------------
        # Right column (plugins/workspaces)
        # ------------------------------------------------------------------

        right_widget = QWidget(self)
        right_column = QVBoxLayout(right_widget)
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(14)

        plugins_panel = self._build_plugins_panel()
        right_column.addWidget(plugins_panel, 1)

        # ------------------------------------------------------------------
        # Buttons
        # ------------------------------------------------------------------

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        right_column.addLayout(button_row)

        button_row.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self._continue_button = DatalensButton("Continue", theme, ButtonVariant.CONFIRM, None)
        self._continue_button.clicked.connect(self._on_continue)
        button_row.addWidget(self._continue_button)

        self._cancel_button = DatalensButton("Quit", theme, ButtonVariant.CANCEL, None)
        self._cancel_button.clicked.connect(self._on_quit)
        button_row.addWidget(self._cancel_button)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)
        splitter.setOpaqueResize(False)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        self._splitter = splitter

        try:
            settings_store = qsettings()
            restore_geometry(settings_store, "welcome/geometry", self)
            restore_splitter(settings_store, "welcome/splitter", splitter)
        except Exception:
            pass

        layout.addWidget(splitter, 1)

        self._apply_theme()

    def updated_settings(self) -> AppSettings:
        """Return settings updated by the welcome selection."""
        return self._settings

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_projects_panel(self) -> QWidget:
        container = QFrame(self)
        container.setObjectName("WelcomeProjectsPanel")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(10)

        title = QLabel("Project", container)
        title.setStyleSheet("font-size: 13px; font-weight: 700;")
        layout.addWidget(title)

        hint = QLabel(
            "Choose a recent project, or create/open a project folder.",
            container,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.75)}; font-size: 12px;")
        layout.addWidget(hint)

        self._recent_projects_list = QListWidget(container)
        self._recent_projects_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._recent_projects_list.setAlternatingRowColors(True)
        self._recent_projects_list.itemSelectionChanged.connect(self._on_recent_selected)
        self._recent_projects_list.itemDoubleClicked.connect(lambda *_: self._on_continue())

        recents = list(self._settings.recent_projects)
        if recents:
            for path in recents:
                item = QListWidgetItem(str(path))
                item.setToolTip(str(path))
                item.setData(int(Qt.UserRole), str(path))
                self._recent_projects_list.addItem(item)
        else:
            placeholder = QListWidgetItem("No recent projects yet.")
            placeholder.setFlags(Qt.NoItemFlags)
            self._recent_projects_list.addItem(placeholder)

        layout.addWidget(self._recent_projects_list, 1)

        row = QWidget(container)
        grid = QGridLayout(row)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        self._project_path_edit = QLineEdit(row)
        self._project_path_edit.setPlaceholderText("Project path (paste or browse)")
        self._project_path_edit.textChanged.connect(self._on_path_text_changed)
        if self._selected_project_root:
            self._project_path_edit.setText(str(self._selected_project_root))
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
        return container

    def _build_plugins_panel(self) -> QWidget:
        container = QFrame(self)
        container.setObjectName("WelcomePluginsPanel")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(10)

        title = QLabel("Workspaces", container)
        title.setStyleSheet("font-size: 13px; font-weight: 700;")
        layout.addWidget(title)

        hint = QLabel(
            "Select which workspaces (plugins) you want enabled.\n"
            "This choice is saved and used by --skip-welcome.",
            container,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.75)}; font-size: 12px;")
        layout.addWidget(hint)

        enabled = set(self._settings.enabled_plugins)
        if not enabled and self._plugins:
            enabled = {p.id for p in self._plugins if p.enabled_by_default}
        if not enabled:
            enabled = {PluginId("annotation"), PluginId("review")}

        self._plugin_checkboxes: dict[PluginId, DatalensCheckBox] = {}

        plugins = list(self._plugins)
        plugins.sort(key=lambda p: ((str(p.group) if p.group else "Other").lower(), p.name.lower()))

        current_group: str | None = None
        for plugin in plugins:
            group_label_text = str(plugin.group) if plugin.group else "Other"
            if group_label_text != current_group:
                current_group = group_label_text
                group_label = QLabel(group_label_text, container)
                group_label.setStyleSheet(f"color: {self._theme.primary_color}; font-weight: 700; font-size: 12px;")
                layout.addWidget(group_label)

            label = plugin.name
            if plugin.stage != PluginStage.RELEASE:
                label = f"{plugin.name} ({plugin.stage.value})"

            checkbox = DatalensCheckBox(label, self._theme, container)
            plugin_key = plugin.id
            checkbox.setChecked(plugin_key in enabled)
            checkbox.setToolTip(plugin.description)
            self._plugin_checkboxes[plugin_key] = checkbox
            layout.addWidget(checkbox)

        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))
        return container

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        t = self._theme
        border = t.with_alpha_hex(t.primary_color, 0.45)
        panel_bg = t.with_alpha_hex(t.secondary_color, 0.55)
        splitter_line = t.with_alpha_hex(t.text_color, 0.10)
        splitter_hover = t.with_alpha_hex(t.primary_color, 0.10)
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {t.secondary_color};
                color: {t.text_color};
            }}
            QFrame#WelcomeProjectsPanel, QFrame#WelcomePluginsPanel {{
                background-color: {panel_bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            QLineEdit {{
                background-color: {t.with_alpha_hex(t.secondary_color, 0.70)};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 8px 10px;
                color: {t.text_color};
            }}
            QListWidget {{
                background-color: {t.with_alpha_hex(t.secondary_color, 0.55)};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 2px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 10px;
                border-radius: 8px;
                padding: 4px 6px;
            }}
            QListWidget::item:selected {{
                background-color: {t.with_alpha_hex(t.primary_color, 0.20)};
                color: {t.text_color};
            }}
            QSplitter::handle:horizontal {{
                background-color: transparent;
                border-left: 1px solid {splitter_line};
            }}
            QSplitter::handle:horizontal:hover {{
                background-color: {splitter_hover};
            }}
            """
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _set_selected_project(self, path: Path | None) -> None:
        self._selected_project_root = path
        self._project_path_edit.setText(str(path) if path else "")

    def _current_splitter_state_b64(self) -> str | None:
        return None

    def _persist_welcome_ui_state_best_effort(self) -> None:
        """
        Persist welcome window UI state as best-effort user/app settings.

        This should never block the UI thread. It is acceptable for this to be
        dropped on hard crashes because it is second-class UI state.
        """
        splitter = self._splitter
        if splitter is not None:
            try:
                settings_store = qsettings()
                save_geometry(settings_store, "welcome/geometry", self)
                save_splitter(settings_store, "welcome/splitter", splitter)
            except Exception:
                pass
        try:
            self._settings_writer.request_save(self._settings)
        except Exception:
            pass

    def _path_from_edit(self) -> Path | None:
        raw = self._project_path_edit.text().strip()
        if not raw:
            return None
        try:
            return Path(raw)
        except Exception:
            return None

    def _best_dialog_start_dir(self) -> str:
        """
        Return a directory path to use as the initial folder for file dialogs.

        If the user typed a path, try to start there (or its parent) when it exists.
        """
        p = self._path_from_edit()
        if p is None:
            return ""
        try:
            if p.exists() and p.is_dir():
                return str(p)
            parent = p.parent
            if parent.exists() and parent.is_dir():
                return str(parent)
        except Exception:
            return ""
        return ""

    def _on_path_text_changed(self) -> None:
        p = self._path_from_edit()
        if p is None:
            self._selected_project_root = None
            return
        try:
            if p.exists() and p.is_dir():
                self._selected_project_root = p
        except Exception:
            pass

    def _on_recent_selected(self) -> None:
        widget = self._recent_projects_list
        if widget is None:
            return
        items = widget.selectedItems()
        if not items:
            return
        raw = items[0].data(int(Qt.UserRole))
        if not isinstance(raw, str) or not raw:
            return
        self._set_selected_project(Path(raw))

    def _open_existing_project(self) -> None:
        # If the user already typed a valid path, treat it as the chosen project.
        p = self._path_from_edit()
        if p is not None and p.exists() and p.is_dir():
            self._set_selected_project(p)
            return

        directory = QFileDialog.getExistingDirectory(
            self,
            "Open project folder",
            self._best_dialog_start_dir(),
        )
        if not directory:
            return
        self._set_selected_project(Path(directory))

    def _create_new_project(self) -> None:
        # If the user typed a path, create it (if missing) and select it.
        p = self._path_from_edit()
        if p is not None:
            try:
                if p.exists():
                    if not p.is_dir():
                        QMessageBox.warning(self, "New Project", f"Path exists but is not a folder:\n{p}")
                        return
                else:
                    p.mkdir(parents=True, exist_ok=False)
                self._set_selected_project(p)
                return
            except Exception as exc:
                QMessageBox.critical(self, "New Project", f"Failed to create project folder:\n{exc}")
                return

        directory = QFileDialog.getExistingDirectory(
            self,
            "Create new project folder",
            self._best_dialog_start_dir(),
        )
        if not directory:
            return
        self._set_selected_project(Path(directory))

    def _on_continue(self) -> None:
        # Ensure typed paths are considered before validating.
        if self._selected_project_root is None:
            p = self._path_from_edit()
            if p is not None and p.exists() and p.is_dir():
                self._selected_project_root = p

        if self._selected_project_root is None:
            QMessageBox.information(
                self,
                "Select a Project",
                "Select a recent project, or click New/Open to choose a project folder.",
            )
            return

        enabled = frozenset(pid for pid, cb in self._plugin_checkboxes.items() if cb.isChecked())
        selected = self._selected_project_root
        recents: list[Path] = [selected]
        for p in self._settings.recent_projects:
            if p == selected:
                continue
            recents.append(p)
            if len(recents) >= 12:
                break

        new_settings = replace(
            self._settings,
            enabled_plugins=enabled,
            last_project_root=selected,
            recent_projects=tuple(recents),
        )
        self._settings = new_settings
        try:
            self._settings_writer.request_save(self._settings)
        except Exception:
            pass
        self.accept()

    def _on_quit(self) -> None:
        self._persist_welcome_ui_state_best_effort()
        self.reject()

    def _edit_profile(self) -> None:
        dialog = ProfileEditDialog(self._theme, self._settings.user_profile or UserProfile(), self)
        if not dialog.exec():
            return

        profile = dialog.profile().normalized()
        user_profile = profile if (profile.name or profile.email) else None
        self._settings = replace(self._settings, user_profile=user_profile)
        try:
            self._settings_writer.request_save(self._settings)
        except Exception:
            pass
        if self._profile_summary is not None:
            self._profile_summary.set_profile(user_profile or UserProfile())

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._persist_welcome_ui_state_best_effort()
        super().closeEvent(event)
