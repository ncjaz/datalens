from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from datalens.ui.shortcuts.binding_editor import ShortcutBindingEditor
from datalens.ui.widgets.icons.reset_icon import reset_icon
from datalens.ui.widgets.core.toggle import Toggle, ToggleOption
from datalens.ui.widgets.core.icon_button import create_icon_button

from .types import BindingKey, RebuildResult


class ShortcutRowsBuilder:
    """
    Small helper that builds and wires individual binding rows.

    The page provides callbacks (persist + scheduling). This builder owns:
    - row widget construction for commands + gestures
    - signal wiring for per-row controls
    - capturing widget references into the `RebuildResult` containers
    """

    def __init__(
        self,
        *,
        result: RebuildResult,
        mode_is_keyboard_only: Callable[[object, object], bool],
        on_binding_changed: Callable[[str, str, str, object], None],
        on_binding_reset: Callable[[str, str, str], None],
        on_consume_changed: Callable[[str, str, str, bool], None],
        on_consume_reset: Callable[[str, str, str], None],
        on_recording_changed: Callable[[bool], None],
        on_mode_changed: Callable[[str, str, bool], None],
        on_mode_reset: Callable[[str, str], None],
    ) -> None:
        self._result = result
        self._mode_is_keyboard_only = mode_is_keyboard_only
        self._on_binding_changed = on_binding_changed
        self._on_binding_reset = on_binding_reset
        self._on_consume_changed = on_consume_changed
        self._on_consume_reset = on_consume_reset
        self._on_recording_changed = on_recording_changed
        self._on_mode_changed = on_mode_changed
        self._on_mode_reset = on_mode_reset

    def add_command_row(
        self,
        section_layout: QFormLayout,
        *,
        plugin_id: str,
        command_id: str,
        title: str,
        description: str,
        scope: str,
        default_chord: object,
        effective_chord: object,
        is_overridden: bool,
        consume_event: bool,
        mode_toggle_default: object,
        mode_toggle_effective: object,
    ) -> None:
        section_box = section_layout.parentWidget()
        if section_box is None:
            return

        label = QLabel(title, section_box)
        label.setToolTip(str(description) if description else "")

        editor = ShortcutBindingEditor(initial=effective_chord, show_reset=True, parent=section_box)
        # Disable reset if the user has not overridden this binding (visual cue).
        try:
            editor.set_reset_enabled(bool(is_overridden))
        except Exception:
            pass
        consume = QCheckBox("Consume", section_box)
        consume.setChecked(bool(consume_event))
        consume_reset = QPushButton("Reset consume", section_box)

        row = QWidget(section_box)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.addWidget(editor, 1)

        supports_mode = isinstance(mode_toggle_default, bool) and self._mode_is_keyboard_only(default_chord, effective_chord)
        key: BindingKey = (plugin_id, "command", command_id)
        if supports_mode:
            app = QApplication.instance()
            theme = getattr(app, "app_theme", None) if app is not None else None
            if theme is not None:
                mode_toggle = Toggle(
                    theme=theme,
                    left=ToggleOption("hold", "Hold"),
                    right=ToggleOption("toggle", "Toggle"),
                    parent=section_box,
                )
                is_toggle = bool(mode_toggle_effective) if isinstance(mode_toggle_effective, bool) else bool(mode_toggle_default)
                mode_toggle.set_current_id("toggle" if is_toggle else "hold", emit=False)
                mode_reset = QPushButton("Reset mode", section_box)
                mode_toggle.setToolTip("Choose whether this command behaves as Hold or Toggle.")
                mode_reset.setToolTip("Reset Hold/Toggle mode to the command default.")
                row_layout.addWidget(mode_toggle, 0)
                row_layout.addWidget(mode_reset, 0)

                self._result.mode_toggles[key] = mode_toggle
                self._result.mode_reset_buttons[key] = mode_reset
                self._result.mode_defaults[key] = bool(mode_toggle_default)

                mode_toggle.selectionChanged.connect(
                    lambda sel, pid=plugin_id, cid=command_id: self._on_mode_changed(pid, cid, sel == "toggle")
                )
                mode_reset.clicked.connect(lambda *_: self._on_mode_reset(plugin_id, command_id))

        row_layout.addWidget(QLabel(f"[{scope}]", section_box), 0)
        row_layout.addWidget(consume, 0)
        row_layout.addWidget(consume_reset, 0)

        tooltip = (((str(description) + "\n\n") if description else "") + f"Scope: {scope}\nDefault: {default_chord or 'Unbound'}")
        editor.setToolTip(tooltip)
        consume.setToolTip("If enabled, the matching Qt input event will not reach the widget.")
        consume_reset.setToolTip("Reset consume_event to the command default.")

        self._result.editors[key] = editor
        self._result.consume_checks[key] = consume
        self._result.consume_reset_buttons[key] = consume_reset
        self._result.binding_scopes[key] = scope
        self._result.last_saved[key] = str(effective_chord).strip() if isinstance(effective_chord, str) else None

        editor.chordChanged.connect(lambda chord, pid=plugin_id, cid=command_id: self._on_binding_changed(pid, "command", cid, chord))
        editor.resetRequested.connect(lambda pid=plugin_id, cid=command_id: self._on_binding_reset(pid, "command", cid))
        editor.recordingChanged.connect(lambda active: self._on_recording_changed(bool(active)))
        consume.toggled.connect(lambda checked, pid=plugin_id, cid=command_id: self._on_consume_changed(pid, "command", cid, bool(checked)))
        consume_reset.clicked.connect(lambda *_: self._on_consume_reset(plugin_id, "command", command_id))

        section_layout.addRow(label, row)

    def add_gesture_row(
        self,
        section_layout: QFormLayout,
        *,
        plugin_id: str,
        gesture_id: str,
        title: str,
        description: str,
        scope: str,
        default_chord: object,
        effective_chord: object,
        is_overridden: bool,
        uses_modifier_defaults: bool,
        consume_event: bool,
    ) -> None:
        section_box = section_layout.parentWidget()
        if section_box is None:
            return

        label = QLabel(f"Gesture: {title}", section_box)
        label.setToolTip(str(description) if description else "")

        # For "modifier defaults" gestures, use an icon reset button so the UX matches
        # the global Primary/Secondary modifier concept (disabled when following defaults).
        show_icon_reset = bool(uses_modifier_defaults)
        editor = ShortcutBindingEditor(initial=effective_chord, show_reset=not show_icon_reset, parent=section_box)
        if not show_icon_reset:
            try:
                editor.set_reset_enabled(bool(is_overridden))
            except Exception:
                pass
        consume = QCheckBox("Consume", section_box)
        consume.setChecked(bool(consume_event))
        consume_reset = QPushButton("Reset consume", section_box)

        row = QWidget(section_box)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.addWidget(editor, 1)
        if show_icon_reset:
            app = QApplication.instance()
            theme = getattr(app, "app_theme", None) if app is not None else None
            if theme is not None:
                reset_btn = create_icon_button(theme, section_box, size=32, icon_size=18, checkable=False)
                reset_btn.setIcon(reset_icon(theme, size=18))
                reset_btn.setEnabled(bool(is_overridden))
                reset_btn.setToolTip("Reset to follow the global Primary/Secondary modifier defaults.")
                reset_btn.clicked.connect(lambda *_: self._on_binding_reset(plugin_id, "gesture", gesture_id))
                row_layout.addWidget(reset_btn, 0)
            else:
                reset_btn = QPushButton("Reset", section_box)
                reset_btn.setEnabled(bool(is_overridden))
                reset_btn.clicked.connect(lambda *_: self._on_binding_reset(plugin_id, "gesture", gesture_id))
                row_layout.addWidget(reset_btn, 0)
        row_layout.addWidget(QLabel(f"[{scope}]", section_box), 0)
        row_layout.addWidget(consume, 0)
        row_layout.addWidget(consume_reset, 0)

        tooltip = (
            ((str(description) + "\n\n") if description else "")
            + f"Scope: {scope}\nDefault: {default_chord or 'Unbound'}\n(begin chord)"
        )
        editor.setToolTip(tooltip)
        consume.setToolTip("If enabled, the widget can stop the mouse event from reaching other handlers.")
        consume_reset.setToolTip("Reset consume_event to the gesture default.")

        key: BindingKey = (plugin_id, "gesture", gesture_id)
        self._result.editors[key] = editor
        self._result.consume_checks[key] = consume
        self._result.consume_reset_buttons[key] = consume_reset
        self._result.binding_scopes[key] = scope
        self._result.last_saved[key] = str(effective_chord).strip() if isinstance(effective_chord, str) else None

        editor.chordChanged.connect(lambda chord, pid=plugin_id, gid=gesture_id: self._on_binding_changed(pid, "gesture", gid, chord))
        if not show_icon_reset:
            editor.resetRequested.connect(
                lambda pid=plugin_id, gid=gesture_id: self._on_binding_reset(pid, "gesture", gid)
            )
        editor.recordingChanged.connect(lambda active: self._on_recording_changed(bool(active)))
        consume.toggled.connect(lambda checked, pid=plugin_id, gid=gesture_id: self._on_consume_changed(pid, "gesture", gid, bool(checked)))
        consume_reset.clicked.connect(lambda *_: self._on_consume_reset(plugin_id, "gesture", gesture_id))

        section_layout.addRow(label, row)


__all__ = ["ShortcutRowsBuilder"]
