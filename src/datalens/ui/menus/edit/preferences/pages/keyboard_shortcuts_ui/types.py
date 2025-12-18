from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QCheckBox, QGroupBox, QPushButton

from datalens.ui.shortcuts.binding_editor import ShortcutBindingEditor
from datalens.ui.widgets.core.toggle import Toggle

BindingKey = tuple[str, str, str]


@dataclass(slots=True)
class RebuildResult:
    """
    References to widgets created during a rebuild.

    The owning page keeps these references to:
    - drive conflict checks
    - toggle visibility by plugin
    - avoid rebuilding while a recorder is active
    """

    plugin_boxes: dict[str, QGroupBox]
    editors: dict[BindingKey, ShortcutBindingEditor]
    consume_checks: dict[BindingKey, QCheckBox]
    consume_reset_buttons: dict[BindingKey, QPushButton]
    mode_toggles: dict[BindingKey, Toggle]
    mode_reset_buttons: dict[BindingKey, QPushButton]
    mode_defaults: dict[BindingKey, bool]
    binding_scopes: dict[BindingKey, str]
    last_saved: dict[BindingKey, str | None]


__all__ = ["BindingKey", "RebuildResult"]

