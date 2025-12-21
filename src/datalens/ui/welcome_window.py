from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from datalens.domain.plugin import PluginDefinition
from datalens.domain.system.settings import AppSettings
from datalens.domain.system.user_profile import UserProfile
from datalens.services.settings_store import default_debounced_settings_writer
from datalens.ui.qt_settings import qsettings, restore_geometry, restore_splitter, save_geometry, save_splitter
from datalens.ui.theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton
from datalens.ui.welcome.projects_panel import WelcomeProjectsPanel
from datalens.ui.welcome.profile import ProfileEditDialog, ProfileSummary
from datalens.ui.welcome.workspaces_panel import WelcomeWorkspacesPanel


class WelcomeWindow(QDialog):
    """
    Welcome dialog shown after pre-welcome startup initialization.

    Layout mirrors the V1 two-column welcome screen:
    - Left: project selection / recents (placeholder in V2 for now)
    - Right: plugin/workspace selection

    The user's selection is persisted to :class:`~datalens.domain.system.settings.AppSettings`
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
        self._profile_summary: ProfileSummary | None = None
        self._settings_writer = default_debounced_settings_writer(debounce_seconds=0.25)
        self._splitter: QSplitter | None = None
        self._projects_panel: WelcomeProjectsPanel | None = None
        self._workspaces_panel: WelcomeWorkspacesPanel | None = None

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

        projects_panel = WelcomeProjectsPanel(
            theme=self._theme,
            recent_projects=tuple(self._settings.recent_projects),
            selected_project_root=self._settings.last_project_root,
            parent=left_widget,
        )
        projects_panel.continueRequested.connect(self._on_continue)
        self._projects_panel = projects_panel
        left_column.addWidget(projects_panel, 1)

        left_column.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # ------------------------------------------------------------------
        # Right column (plugins/workspaces)
        # ------------------------------------------------------------------

        right_widget = QWidget(self)
        right_column = QVBoxLayout(right_widget)
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(14)

        plugins_panel = WelcomeWorkspacesPanel(theme=self._theme, settings=self._settings, plugins=self._plugins, parent=right_widget)
        self._workspaces_panel = plugins_panel
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

    def selected_project_root(self) -> Path | None:
        """
        Return the project root selected for *this* continue action.

        This may be None if the user chose to continue without opening a
        project.
        """
        panel = self._projects_panel
        return panel.selected_project_root() if panel is not None else None

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        t = self._theme
        border = t.with_alpha_hex(t.primary_color, 0.45)
        panel_bg = t.with_alpha_hex(t.background_color, 0.55)
        splitter_line = t.with_alpha_hex(t.text_color, 0.10)
        splitter_hover = t.with_alpha_hex(t.primary_color, 0.10)
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {t.background_color};
                color: {t.text_color};
            }}
            QFrame#WelcomeProjectsPanel, QFrame#WelcomeWorkspacesPanel {{
                background-color: {panel_bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            QLineEdit {{
                background-color: {t.with_alpha_hex(t.background_color, 0.70)};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 8px 10px;
                color: {t.text_color};
            }}
            QListWidget {{
                background-color: {t.with_alpha_hex(t.background_color, 0.55)};
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

    def _on_continue(self) -> None:
        enabled = self._workspaces_panel.enabled_workspaces() if self._workspaces_panel is not None else frozenset()
        selected = self._projects_panel.selected_project_root() if self._projects_panel is not None else None

        # Allow continuing without a project (no-project mode). In that case we
        # keep the persisted last/recent project list intact and only update
        # app-scope selections like enabled plugins.
        if selected is None:
            new_settings = replace(self._settings, enabled_plugins=enabled)
        else:
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
