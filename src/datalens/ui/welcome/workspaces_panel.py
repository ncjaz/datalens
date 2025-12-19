from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget

from datalens.domain.plugin import PluginDefinition, PluginId, PluginStage
from datalens.domain.system.settings import AppSettings
from datalens.services.settings_store import default_settings_store
from datalens.ui.theme import AppTheme
from datalens.ui.widgets.core.checkboxes import DatalensCheckBox


class WelcomeWorkspacesPanel(QFrame):
    """
    Workspace selection panel used by the welcome screen.

    This panel is UI-only: it lists discovered workspace plugins and provides
    checkboxes for enabled/disabled state. Persistence happens in the parent
    WelcomeWindow when the user clicks Continue.
    """

    def __init__(
        self,
        *,
        theme: AppTheme,
        settings: AppSettings,
        plugins: tuple[PluginDefinition, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WelcomeWorkspacesPanel")
        self._theme = theme
        self._settings = settings
        self._plugins = plugins

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(10)

        title = QLabel("Workspaces", self)
        title.setStyleSheet("font-size: 13px; font-weight: 700;")
        layout.addWidget(title)

        hint = QLabel(
            "Select which workspaces (plugins) you want enabled.\n"
            "This choice is saved and used by --skip-welcome.",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.75)}; font-size: 12px;")
        layout.addWidget(hint)

        enabled = set(self._settings.enabled_plugins)
        # First run: if settings.json doesn't exist yet, default to manifest defaults.
        # Once settings.json exists, an empty set is treated as "explicitly none enabled".
        if not enabled and self._plugins and not default_settings_store().path.exists():
            enabled = {p.id for p in self._plugins if p.enabled_by_default}

        self._plugin_checkboxes: dict[PluginId, DatalensCheckBox] = {}

        plugins = list(self._plugins)
        plugins.sort(key=lambda p: ((str(p.group) if p.group else "Other").lower(), p.name.lower()))

        current_group: str | None = None
        for plugin in plugins:
            group_label_text = str(plugin.group) if plugin.group else "Other"
            if group_label_text != current_group:
                current_group = group_label_text
                group_label = QLabel(group_label_text, self)
                group_label.setStyleSheet(f"color: {self._theme.primary_color}; font-weight: 700; font-size: 12px;")
                layout.addWidget(group_label)

            label = plugin.name
            if plugin.stage != PluginStage.RELEASE:
                label = f"{plugin.name} ({plugin.stage.value})"

            checkbox = DatalensCheckBox(label, self._theme, self)
            plugin_key = plugin.id
            checkbox.setChecked(plugin_key in enabled)
            checkbox.setToolTip(plugin.description)
            self._plugin_checkboxes[plugin_key] = checkbox
            layout.addWidget(checkbox)

        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def enabled_workspaces(self) -> frozenset[PluginId]:
        return frozenset(pid for pid, cb in self._plugin_checkboxes.items() if cb.isChecked())
