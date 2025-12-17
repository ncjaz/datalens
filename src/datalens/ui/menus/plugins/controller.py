from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QMessageBox

from datalens.ui.menus.contracts import PluginsMenuController
from datalens.core.logging import get_logger


log = get_logger(__name__)


class QtPluginsMenuController(PluginsMenuController):
    def __init__(self, main_window: QMainWindow) -> None:
        self._main_window = main_window

    def manage_plugins(self) -> None:
        QMessageBox.information(self._main_window, "Plugins", "Plugin management UI is not implemented yet.")

    def create_new_plugin(self) -> None:
        from datalens.infra.background.loader_context import LoaderContext
        from datalens.infra.background.loader_runner import run_with_loader
        from datalens.infra.paths import datalens_user_data_dir
        from datalens.services.plugins.scaffold import PluginScaffoldRequest, scaffold_plugin
        from datalens.services.settings_store import default_settings_store
        from datalens.ui.menus.plugins.create_plugin.create_plugin_dialog import CreatePluginDialog

        settings = default_settings_store().load()
        user_data_root = getattr(settings, "user_data_dir", None) or datalens_user_data_dir()
        plugins_root = Path(user_data_root) / "plugins"

        dialog = CreatePluginDialog(plugin_root_dir=plugins_root, parent=self._main_window)
        if not dialog.exec():
            return

        draft = dialog.draft()

        def task(ctx: LoaderContext) -> object:
            from dataclasses import replace

            from datalens.domain.plugin import PluginId

            ctx.log("Creating plugin folder…")
            req = PluginScaffoldRequest(
                plugin_id=draft.plugin_id,
                name=draft.name,
                version=draft.version,
                stage=draft.stage,
                kind=draft.kind,
                description=draft.description,
                author=draft.author,
                nav_label=draft.nav_label,
            )
            result = scaffold_plugin(root_dir=plugins_root, request=req)
            ctx.log(f"Wrote: {result.manifest_path}")
            ctx.log(f"Wrote: {result.plugin_py_path}")

            # Enable the plugin in settings so it appears in the nav after restart.
            store = default_settings_store()

            def enable_plugin(s):
                enabled = set(getattr(s, "enabled_plugins", ()) or ())
                enabled.add(PluginId(draft.plugin_id))
                return replace(s, enabled_plugins=frozenset(enabled))

            store.update(enable_plugin)
            log.info(
                "Plugin scaffold created and enabled",
                extra={"operation": "plugin_scaffold", "phase": "enabled", "plugin_id": draft.plugin_id},
            )

            ctx.set_progress(1.0)
            return result

        def on_done(result: object) -> None:
            QMessageBox.information(
                self._main_window,
                "Plugin Created",
                "Plugin scaffold created and enabled in settings.\n\nRestart DataLens to discover it.",
            )

        def on_error(exc: Exception) -> None:
            QMessageBox.critical(self._main_window, "Failed to Create Plugin", str(exc))

        run_with_loader(
            parent=self._main_window,
            title="Creating Plugin…",
            task=task,
            on_result=on_done,
            on_error=on_error,
            dialog_options={"spinner_size": 80, "title_point_size": 18, "subtitle_point_size": 12},
        )
