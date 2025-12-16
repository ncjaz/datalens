from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from datalens.domain.plugin import PluginDefinition, PluginId, PluginStage
from datalens.domain.settings import AppSettings
from datalens.domain.user_profile import UserProfile
from datalens.services.config_service import save_settings
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
        self.resize(960, 560)

        self._theme = theme
        self._settings = settings
        self._plugins = plugins
        self._selected_project_root: Path | None = settings.last_project_root
        self._profile_summary: ProfileSummary | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        # ------------------------------------------------------------------
        # Left column (projects)
        # ------------------------------------------------------------------

        left_column = QVBoxLayout()
        left_column.setSpacing(12)
        layout.addLayout(left_column, 2)

        header = QLabel("DataLens", self)
        header.setStyleSheet("font-size: 26px; font-weight: 700;")
        left_column.addWidget(header)

        subheader = QLabel(
            "Select how you would like to start today. Recent projects will appear here.",
            self,
        )
        subheader.setWordWrap(True)
        subheader.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.80)}; font-size: 13px;")
        left_column.addWidget(subheader)

        profile_summary = ProfileSummary(theme, settings.user_profile or UserProfile(), self)
        profile_summary.editRequested.connect(self._edit_profile)
        self._profile_summary = profile_summary
        left_column.addWidget(profile_summary)

        projects_panel = self._build_projects_panel()
        left_column.addWidget(projects_panel, 1)

        left_column.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # ------------------------------------------------------------------
        # Right column (plugins/workspaces)
        # ------------------------------------------------------------------

        right_column = QVBoxLayout()
        right_column.setSpacing(14)
        layout.addLayout(right_column, 3)

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
        self._cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self._cancel_button)

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
            "The project system will manage datasets, media, and annotations.\n"
            "For now you can choose a folder to act as the project root.",
            container,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.75)}; font-size: 12px;")
        layout.addWidget(hint)

        row = QWidget(container)
        grid = QGridLayout(row)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        self._project_path_edit = QLineEdit(row)
        self._project_path_edit.setReadOnly(True)
        self._project_path_edit.setPlaceholderText("No project selected")
        if self._selected_project_root:
            self._project_path_edit.setText(str(self._selected_project_root))
        grid.addWidget(self._project_path_edit, 0, 0)

        browse = DatalensButton("Browse…", self._theme, ButtonVariant.PRIMARY, None)
        browse.clicked.connect(self._choose_project_root)
        browse.setMinimumWidth(110)
        grid.addWidget(browse, 0, 1)

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

            row = QWidget(container)
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)

            label = plugin.name
            if plugin.stage != PluginStage.RELEASE:
                label = f"{plugin.name} ({plugin.stage.value})"

            checkbox = DatalensCheckBox(label, self._theme, row)
            plugin_key = plugin.id
            checkbox.setChecked(plugin_key in enabled)
            self._plugin_checkboxes[plugin_key] = checkbox
            row_layout.addWidget(checkbox)

            desc = QLabel(plugin.description, row)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.60)}; font-size: 11px;")
            row_layout.addWidget(desc)

            layout.addWidget(row)

        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))
        return container

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        t = self._theme
        border = t.with_alpha_hex(t.tertiary_color, 0.45)
        panel_bg = t.with_alpha_hex(t.secondary_color, 0.55)
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
            """
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _choose_project_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose project folder")
        if not directory:
            return
        self._selected_project_root = Path(directory)
        self._project_path_edit.setText(directory)

    def _on_continue(self) -> None:
        enabled = frozenset(pid for pid, cb in self._plugin_checkboxes.items() if cb.isChecked())

        new_settings = replace(
            self._settings,
            enabled_plugins=enabled,
            last_project_root=self._selected_project_root,
        )
        save_settings(new_settings)
        self._settings = new_settings
        self.accept()

    def _edit_profile(self) -> None:
        dialog = ProfileEditDialog(self._theme, self._settings.user_profile or UserProfile(), self)
        if not dialog.exec():
            return

        profile = dialog.profile().normalized()
        user_profile = profile if (profile.name or profile.email) else None
        self._settings = replace(self._settings, user_profile=user_profile)
        save_settings(self._settings)
        if self._profile_summary is not None:
            self._profile_summary.set_profile(user_profile or UserProfile())
