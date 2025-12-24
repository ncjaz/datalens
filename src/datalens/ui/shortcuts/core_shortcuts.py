from __future__ import annotations

from datalens.core.context import get_app_context
from datalens.domain.plugin import PluginId
from datalens.domain.system.shortcuts import (
    ShortcutCommandId,
    ShortcutCommandSpec,
    ShortcutPageSpec,
    ShortcutScope,
    ShortcutSectionSpec,
)
from datalens.ui.menus.contracts import MenuControllers


_CORE_PLUGIN_ID = PluginId("core")


def register_core_shortcuts(*, controllers: MenuControllers) -> None:
    """
    Register core app shortcuts (File/Edit/etc) with the shortcuts service.

    This intentionally avoids setting `QAction` shortcuts so the shortcuts
    system is the single source of truth (prevents double-fire).
    """

    app_ctx = get_app_context()
    shortcuts = app_ctx.shortcuts

    # Idempotent: allow re-registration during window rebuilds.
    try:
        shortcuts.unregister_plugin(_CORE_PLUGIN_ID)
    except Exception:
        pass

    page = ShortcutPageSpec(
        page_id="core",
        title="Core",
        sections=(
            ShortcutSectionSpec(
                section_id="file",
                title="File",
                commands=(
                    ShortcutCommandSpec(
                        command_id=ShortcutCommandId("new_project"),
                        title="New Project",
                        default_chord="Ctrl+N",
                        scope=ShortcutScope.GLOBAL,
                        allow_in_text_inputs=True,
                        consume_event=True,
                    ),
                    ShortcutCommandSpec(
                        command_id=ShortcutCommandId("open_project"),
                        title="Open Project",
                        default_chord="Ctrl+O",
                        scope=ShortcutScope.GLOBAL,
                        allow_in_text_inputs=True,
                        consume_event=True,
                    ),
                    ShortcutCommandSpec(
                        command_id=ShortcutCommandId("close_project"),
                        title="Close Project",
                        default_chord="Ctrl+W",
                        scope=ShortcutScope.GLOBAL,
                        allow_in_text_inputs=True,
                        consume_event=True,
                    ),
                    ShortcutCommandSpec(
                        command_id=ShortcutCommandId("quit"),
                        title="Quit",
                        default_chord="Ctrl+Q",
                        scope=ShortcutScope.GLOBAL,
                        allow_in_text_inputs=True,
                        consume_event=True,
                    ),
                ),
            ),
            ShortcutSectionSpec(
                section_id="edit",
                title="Edit",
                commands=(
                    ShortcutCommandSpec(
                        command_id=ShortcutCommandId("undo"),
                        title="Undo",
                        default_chord="Ctrl+Z",
                        scope=ShortcutScope.WINDOW,
                        allow_in_text_inputs=False,
                        consume_event=True,
                    ),
                    ShortcutCommandSpec(
                        command_id=ShortcutCommandId("redo"),
                        title="Redo",
                        default_chord="Ctrl+Y",
                        scope=ShortcutScope.WINDOW,
                        allow_in_text_inputs=False,
                        consume_event=True,
                    ),
                    ShortcutCommandSpec(
                        command_id=ShortcutCommandId("preferences"),
                        title="Preferences",
                        default_chord="Ctrl+,",
                        scope=ShortcutScope.GLOBAL,
                        allow_in_text_inputs=True,
                        consume_event=True,
                    ),
                    ShortcutCommandSpec(
                        command_id=ShortcutCommandId("keyboard_shortcuts"),
                        title="Keyboard Shortcuts",
                        # Multi-step sequences aren't supported yet; keep simple.
                        default_chord="Ctrl+Alt+K",
                        scope=ShortcutScope.GLOBAL,
                        allow_in_text_inputs=True,
                        consume_event=True,
                    ),
                ),
            ),
        ),
    )

    shortcuts.register_page(
        plugin_id=_CORE_PLUGIN_ID,
        plugin_name="Core",
        page=page,
        callbacks={
            "new_project": controllers.file.new_project,
            "open_project": controllers.file.open_project,
            "close_project": controllers.file.close_project,
            "quit": controllers.file.quit_app,
            "undo": controllers.edit.undo,
            "redo": controllers.edit.redo,
            "preferences": controllers.edit.open_preferences,
            "keyboard_shortcuts": controllers.edit.open_keyboard_shortcuts,
        },
    )


__all__ = ["register_core_shortcuts"]
