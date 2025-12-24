from __future__ import annotations

from dataclasses import replace
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from datalens.core.context import get_app_context
from datalens.core.logging import get_logger
from datalens.domain.system.shortcuts import ShortcutOverrides
from datalens.services.settings_store import default_debounced_settings_writer
from datalens.ui.menus.edit.preferences.pages.keyboard_shortcuts_ui import rebuild_shortcuts_ui
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton

if TYPE_CHECKING:
    from PySide6.QtWidgets import QCheckBox, QGroupBox, QPushButton

    from datalens.ui.shortcuts.binding_editor import ShortcutBindingEditor
    from datalens.ui.widgets.core.toggle import Toggle

log = get_logger(__name__)

_GENERAL_FILTER_KEY = "__general__"


@dataclass(frozen=True)
class _ModifierDefaults:
    primary: str
    secondary: str

    def as_mapping(self) -> dict[str, str]:
        return {"primary": self.primary, "secondary": self.secondary}


class KeyboardShortcutsPreferencesPage(QWidget):
    """Preferences page: Keyboard Shortcuts (keyboard + mouse chords)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_ctx = get_app_context()
        self._writer = default_debounced_settings_writer()
        self._unsubscribe_changed: object | None = None
        self._refresh_scheduled = False
        self._pending_refresh = False
        self._plugin_boxes: dict[str, QGroupBox] = {}
        self._pending_focus_item: str | None = None
        self._filter_key: str | None = None
        self._general_dirty = False
        self._general_last_applied: _ModifierDefaults | None = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(10)

        title = QLabel("Keyboard Shortcuts")
        title.setObjectName("PreferencesTitle")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._layout.addWidget(title)

        intro = QLabel(
            "Shortcuts are routed by focused top-level window. Workspace-scoped shortcuts only fire for the active "
            "workspace in that window.\n\n"
            "Tip: use Esc to cancel a binding recording.",
            self,
        )
        intro.setWordWrap(True)
        intro.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._layout.addWidget(intro)

        self._conflicts_label = QLabel(self)
        self._conflicts_label.setWordWrap(True)
        self._conflicts_label.setStyleSheet("color: #d18f00;")
        self._layout.addWidget(self._conflicts_label)

        # ------------------------------------------------------------------
        # General (global modifier defaults)
        # ------------------------------------------------------------------

        self._general_box = QGroupBox("General", self)
        general_layout = QVBoxLayout(self._general_box)
        general_layout.setContentsMargins(12, 10, 12, 12)
        general_layout.setSpacing(8)

        general_intro = QLabel(
            "Set the default modifier keys used by modifier-click gestures (e.g. Primary+Click).\n"
            "These defaults apply across plugins unless a specific binding has been manually overridden.",
            self._general_box,
        )
        general_intro.setWordWrap(True)
        general_layout.addWidget(general_intro)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self._primary_combo = QComboBox(self._general_box)
        self._secondary_combo = QComboBox(self._general_box)
        for combo in (self._primary_combo, self._secondary_combo):
            combo.addItems(["Shift", "Ctrl", "Alt", "Meta"])

        form.addRow("Primary Modifier", self._primary_combo)
        form.addRow("Secondary Modifier", self._secondary_combo)
        general_layout.addLayout(form)

        btn_row = QWidget(self._general_box)
        btn_row_layout = QHBoxLayout(btn_row)
        btn_row_layout.setContentsMargins(0, 0, 0, 0)
        btn_row_layout.addStretch(1)
        self._general_apply = DatalensButton("Apply", self._app_ctx.theme, ButtonVariant.CONFIRM, btn_row)
        self._general_apply.clicked.connect(self._apply_modifier_defaults)  # type: ignore[arg-type]
        btn_row_layout.addWidget(self._general_apply, 0)
        general_layout.addWidget(btn_row)

        self._primary_combo.currentIndexChanged.connect(lambda *_: self._mark_general_dirty())
        self._secondary_combo.currentIndexChanged.connect(lambda *_: self._mark_general_dirty())

        self._layout.addWidget(self._general_box)

        self._dynamic_container = QWidget(self)
        self._dynamic_layout = QVBoxLayout(self._dynamic_container)
        self._dynamic_layout.setContentsMargins(0, 0, 0, 0)
        self._dynamic_layout.setSpacing(12)
        self._layout.addWidget(self._dynamic_container)
        self._layout.addStretch(1)

        self._editors: dict[tuple[str, str, str], ShortcutBindingEditor] = {}
        self._consume_checks: dict[tuple[str, str, str], QCheckBox] = {}
        self._consume_reset_buttons: dict[tuple[str, str, str], QPushButton] = {}
        self._mode_toggles: dict[tuple[str, str, str], Toggle] = {}
        self._mode_reset_buttons: dict[tuple[str, str, str], QPushButton] = {}
        self._mode_defaults: dict[tuple[str, str, str], bool] = {}
        self._binding_scopes: dict[tuple[str, str, str], str] = {}
        self._last_saved: dict[tuple[str, str, str], str | None] = {}

        self._rebuild()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._unsubscribe_changed is None:
            self._unsubscribe_changed = self._app_ctx.shortcuts.subscribe_changed(self._on_shortcuts_changed)
        self._rebuild()

    def hideEvent(self, event) -> None:  # type: ignore[override]
        unsub = self._unsubscribe_changed
        self._unsubscribe_changed = None
        if callable(unsub):
            try:
                unsub()
            except Exception:
                log.debug("Failed to unsubscribe shortcuts change listener (best-effort)", exc_info=True)
        super().hideEvent(event)

    def _on_shortcuts_changed(self) -> None:
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_scheduled:
            self._pending_refresh = True
            return
        if any(e.is_recording() for e in self._editors.values()):
            self._pending_refresh = True
            return
        self._refresh_scheduled = True

        def run() -> None:
            self._refresh_scheduled = False
            if any(e.is_recording() for e in self._editors.values()):
                self._pending_refresh = True
                return
            self._pending_refresh = False
            self._rebuild()

        QTimer.singleShot(0, run)

    def _rebuild(self) -> None:
        snap = self._app_ctx.shortcuts.snapshot()
        self._sync_general_from_snapshot(snap)
        result = rebuild_shortcuts_ui(
            dynamic_container=self._dynamic_container,
            dynamic_layout=self._dynamic_layout,
            conflicts_label=self._conflicts_label,
            snap=snap,
            filter_key=self._filter_key,
            mode_is_keyboard_only=lambda default, effective: self._mode_is_keyboard_only(
                default_chord=default,
                effective_chord=effective,
            ),
            on_binding_changed=self._on_binding_changed,
            on_binding_reset=self._on_binding_reset,
            on_consume_changed=self._on_consume_changed,
            on_consume_reset=self._on_consume_reset,
            on_recording_changed=self._on_recording_changed,
            on_mode_changed=self._on_mode_changed,
            on_mode_reset=self._on_mode_reset,
        )

        self._plugin_boxes = result.plugin_boxes
        self._editors = result.editors
        self._consume_checks = result.consume_checks
        self._consume_reset_buttons = result.consume_reset_buttons
        self._mode_toggles = result.mode_toggles
        self._mode_reset_buttons = result.mode_reset_buttons
        self._mode_defaults = result.mode_defaults
        self._binding_scopes = result.binding_scopes
        self._last_saved = result.last_saved

        if self._pending_focus_item:
            target = self._pending_focus_item
            self._pending_focus_item = None
            self.focus_item(target)

    def _mark_general_dirty(self) -> None:
        self._general_dirty = True

    def _sync_general_from_snapshot(self, snap: object) -> None:
        """
        Best-effort sync the General modifier dropdowns from the shortcuts snapshot.

        We avoid overwriting user edits until they press Apply.
        """
        if self._general_dirty:
            return
        defaults = getattr(snap, "modifier_defaults", None)
        if not isinstance(defaults, dict):
            defaults = {}
        primary = str(defaults.get("primary") or "Shift").strip() or "Shift"
        secondary = str(defaults.get("secondary") or "Ctrl").strip() or "Ctrl"
        cur = _ModifierDefaults(primary=primary, secondary=secondary)
        self._general_last_applied = cur
        try:
            idx = self._primary_combo.findText(primary)
            if idx >= 0:
                self._primary_combo.setCurrentIndex(idx)
            idx = self._secondary_combo.findText(secondary)
            if idx >= 0:
                self._secondary_combo.setCurrentIndex(idx)
        except Exception:
            return

    def _current_modifier_defaults(self) -> _ModifierDefaults:
        primary = str(self._primary_combo.currentText() or "Shift").strip() or "Shift"
        secondary = str(self._secondary_combo.currentText() or "Ctrl").strip() or "Ctrl"
        if primary not in ("Shift", "Ctrl", "Alt", "Meta"):
            primary = "Shift"
        if secondary not in ("Shift", "Ctrl", "Alt", "Meta"):
            secondary = "Ctrl"
        return _ModifierDefaults(primary=primary, secondary=secondary)

    def _apply_modifier_defaults(self) -> None:
        new = self._current_modifier_defaults()
        old = self._general_last_applied or _ModifierDefaults(primary="Shift", secondary="Ctrl")
        if new == old:
            self._general_dirty = False
            return

        snap = self._app_ctx.shortcuts.snapshot()

        # We only need to warn when a gesture override hardcodes modifiers (e.g. Alt+Click)
        # instead of using `Primary`/`Secondary` placeholders. Placeholder-based overrides
        # still follow global defaults and do not need a prompt.
        overridden: list[tuple[str, str, str, str]] = []  # (plugin_id, plugin_name, gesture_id, title)

        def uses_placeholders(chord: object) -> bool:
            if not isinstance(chord, str):
                return False
            parts = [p.strip().lower() for p in chord.split("+") if p.strip()]
            return any(p in {"primary", "secondary"} for p in parts)

        try:
            current = self._writer.request_update(lambda cur: cur)  # no-op (no disk write)
            current_overrides: ShortcutOverrides = getattr(current, "shortcut_overrides", ShortcutOverrides())
            gesture_overrides = dict(getattr(current_overrides, "gesture_bindings", {}) or {})
        except Exception:
            gesture_overrides = {}

        try:
            for page in getattr(snap, "pages", ()) or ():
                pid = str(page.get("plugin_id") or "").strip()
                pname = str(page.get("plugin_name") or pid).strip() or pid
                if not pid:
                    continue
                per_overrides = dict(gesture_overrides.get(pid, {}) or {})
                for section in page.get("sections", []) or []:
                    for g in section.get("gestures", []) or []:
                        if not bool(g.get("uses_modifier_defaults", False)):
                            continue
                        gid = str(g.get("gesture_id") or "").strip()
                        if not gid:
                            continue
                        if gid not in per_overrides:
                            continue
                        if uses_placeholders(per_overrides.get(gid)):
                            continue
                        title = str(g.get("title") or gid).strip() or gid
                        overridden.append((pid, pname, gid, title))
        except Exception:
            overridden = []

        reset_overrides = False
        if overridden:
            lines = [f"- {pname}: {title} ({gid})" for _pid, pname, gid, title in overridden]
            dlg = QMessageBox(self)
            dlg.setIcon(QMessageBox.Question)
            dlg.setWindowTitle("Apply modifier defaults")
            dlg.setText("Some bindings use custom modifier overrides.")
            dlg.setInformativeText(
                "Those bindings will NOT follow the new global Primary/Secondary defaults.\n\n"
                "Do you want to reset them so they follow the new defaults?"
            )
            dlg.setDetailedText("\n".join(lines))
            btn_reset = dlg.addButton("Apply and reset overrides", QMessageBox.AcceptRole)
            btn_keep = dlg.addButton("Apply (keep overrides)", QMessageBox.AcceptRole)
            btn_cancel = dlg.addButton(QMessageBox.Cancel)
            dlg.exec()
            clicked = dlg.clickedButton()
            if clicked is btn_cancel:
                return
            reset_overrides = clicked is btn_reset

        to_reset: list[tuple[str, str]] = []
        if reset_overrides and overridden:
            to_reset = [(pid, gid) for pid, _pname, gid, _title in overridden if pid and gid]

        log.info(
            "Applying global modifier defaults",
            extra={
                "operation": "shortcuts",
                "phase": "apply_modifier_defaults",
                "primary_old": old.primary,
                "secondary_old": old.secondary,
                "primary_new": new.primary,
                "secondary_new": new.secondary,
                "reset_overrides": bool(reset_overrides),
                "overrides_detected": len(overridden),
                "overrides_reset": len(to_reset),
            },
        )
        if reset_overrides and to_reset and log.isEnabledFor(10):  # logging.DEBUG
            log.debug(
                "Resetting overridden modifier bindings to follow defaults",
                extra={"operation": "shortcuts", "phase": "reset_modifier_overrides", "items": list(to_reset)},
            )

        def mutator(current):
            overrides: ShortcutOverrides = getattr(current, "shortcut_overrides", ShortcutOverrides())
            bindings, gesture_bindings, consume_overrides, mode_overrides, modifier_defaults = self._override_parts(overrides)

            modifier_defaults = new.as_mapping()
            if reset_overrides and to_reset:
                for pid, gid in to_reset:
                    per = dict(gesture_bindings.get(pid, {}))
                    per.pop(gid, None)
                    if per:
                        gesture_bindings[pid] = per
                    else:
                        gesture_bindings.pop(pid, None)

            return replace(
                current,
                shortcut_overrides=ShortcutOverrides(
                    bindings=bindings,
                    gesture_bindings=gesture_bindings,
                    consume_event_overrides=consume_overrides,
                    mode_toggle_overrides=mode_overrides,
                    modifier_defaults=modifier_defaults,
                ),
            )

        updated = self._writer.request_update(mutator)
        try:
            self._app_ctx.shortcuts.apply_settings(updated)
        except Exception:
            log.debug("Failed to apply modifier defaults to shortcuts service (best-effort)", exc_info=True)
        self._general_dirty = False
        self._general_last_applied = new
        self._schedule_refresh()

    def _on_binding_changed(self, plugin_id: str, kind: str, binding_id: str, chord: object) -> None:
        chord_s = str(chord).strip() if isinstance(chord, str) else None
        key = (plugin_id, kind, binding_id)
        editor = self._editors.get(key)
        if editor is None:
            return

        scope = self._binding_scopes.get(key, "workspace")
        if chord_s:
            if self._has_conflict(plugin_id=plugin_id, scope=scope, chord=chord_s, except_key=key):
                where = "this plugin" if scope != "global" else "global scope"
                QMessageBox.warning(
                    self,
                    "Shortcut conflict",
                    f"A binding already uses '{chord_s}' in scope '{scope}' for {where}.\n\n"
                    "Pick another chord or clear/reset the existing binding first.",
                )
                editor.set_chord(self._last_saved.get(key), emit_signal=False)
                return

        self._persist_binding(plugin_id=plugin_id, kind=kind, binding_id=binding_id, chord=chord_s)
        self._last_saved[key] = chord_s
        self._schedule_refresh()

    def focus_item(self, item_key: str) -> None:
        """
        Scroll the page so the given section is visible.

        Used by the Preferences navigation tree (Keyboard Shortcuts -> General/<plugin>).
        """
        pid = str(item_key).strip()
        if not pid:
            return
        if any(e.is_recording() for e in self._editors.values()):
            return
        self.set_filter(pid)
        if pid == _GENERAL_FILTER_KEY:
            parent: QWidget | None = self.parentWidget()
            scroll: QScrollArea | None = None
            while parent is not None:
                if isinstance(parent, QScrollArea):
                    scroll = parent
                    break
                parent = parent.parentWidget()
            if scroll is None:
                return
            try:
                scroll.ensureWidgetVisible(self._general_box, 0, 16)
            except Exception:
                pass
            return
        box = self._plugin_boxes.get(pid)
        if box is None:
            self._pending_focus_item = pid
            self._schedule_refresh()
            return

        parent: QWidget | None = self.parentWidget()
        scroll: QScrollArea | None = None
        while parent is not None:
            if isinstance(parent, QScrollArea):
                scroll = parent
                break
            parent = parent.parentWidget()
        if scroll is None:
            return
        try:
            scroll.ensureWidgetVisible(box, 0, 16)
        except Exception:
            return

    def set_filter(self, filter_key: str | None) -> None:
        """
        Filter the page to show only one plugin's shortcuts (or show all).

        - `None`/empty: show all plugins
        - `__general__`: show only the General section
        - `<plugin_id>`: show only that plugin's sections
        """
        raw = str(filter_key).strip() if filter_key is not None else ""
        if raw == _GENERAL_FILTER_KEY:
            pid = _GENERAL_FILTER_KEY
        else:
            pid = raw or None
        if pid == self._filter_key:
            return
        self._filter_key = pid
        if any(e.is_recording() for e in self._editors.values()):
            return
        try:
            self._general_box.setVisible(pid is None or pid == _GENERAL_FILTER_KEY)
        except Exception:
            log.debug("Failed to update General section visibility (best-effort)", exc_info=True)
        # Fast path: toggle visibility without a full rebuild.
        if self._plugin_boxes:
            for key, box in self._plugin_boxes.items():
                if pid is None or key == pid:
                    box.show()
                else:
                    box.hide()
        else:
            self._schedule_refresh()

    def _on_consume_changed(self, plugin_id: str, kind: str, binding_id: str, checked: bool) -> None:
        key = (plugin_id, kind, binding_id)
        if key not in self._consume_checks:
            return
        self._persist_consume(plugin_id=plugin_id, kind=kind, binding_id=binding_id, consume=bool(checked))
        self._schedule_refresh()

    def _on_binding_reset(self, plugin_id: str, kind: str, binding_id: str) -> None:
        self._persist_binding_reset(plugin_id=plugin_id, kind=kind, binding_id=binding_id)
        self._schedule_refresh()

    def _on_consume_reset(self, plugin_id: str, kind: str, binding_id: str) -> None:
        self._persist_consume_reset(plugin_id=plugin_id, kind=kind, binding_id=binding_id)
        self._schedule_refresh()

    def _on_recording_changed(self, active: bool) -> None:
        if not active and self._pending_refresh:
            self._schedule_refresh()

    def _has_conflict(self, *, plugin_id: str, scope: str, chord: str, except_key: tuple[str, str, str]) -> bool:
        for (pid, kind, bid), editor in self._editors.items():
            if (pid, kind, bid) == except_key:
                continue
            # GLOBAL scope conflicts across all plugins; other scopes are plugin-local.
            if scope == "global":
                if self._binding_scopes.get((pid, kind, bid)) != scope:
                    continue
            else:
                if pid != plugin_id:
                    continue
                if self._binding_scopes.get((pid, kind, bid)) != scope:
                    continue
            if (editor.chord() or "") == chord:
                return True
        return False

    def _persist_binding(self, *, plugin_id: str, kind: str, binding_id: str, chord: str | None) -> None:
        def mutator(current):
            overrides: ShortcutOverrides = getattr(current, "shortcut_overrides", ShortcutOverrides())
            bindings, gesture_bindings, consume_overrides, mode_overrides, modifier_defaults = self._override_parts(overrides)

            if kind == "gesture":
                per_plugin = dict(gesture_bindings.get(plugin_id, {}))
                per_plugin[binding_id] = chord
                gesture_bindings[plugin_id] = per_plugin
            else:
                per_plugin = dict(bindings.get(plugin_id, {}))
                per_plugin[binding_id] = chord
                bindings[plugin_id] = per_plugin

            return replace(
                current,
                shortcut_overrides=ShortcutOverrides(
                    bindings=bindings,
                    gesture_bindings=gesture_bindings,
                    consume_event_overrides=consume_overrides,
                    mode_toggle_overrides=mode_overrides,
                    modifier_defaults=modifier_defaults,
                ),
            )

        updated = self._writer.request_update(mutator)
        try:
            self._app_ctx.shortcuts.apply_settings(updated)
        except Exception:
            log.debug("Failed to apply shortcut binding change (best-effort)", exc_info=True)

    def _persist_binding_reset(self, *, plugin_id: str, kind: str, binding_id: str) -> None:
        def mutator(current):
            overrides: ShortcutOverrides = getattr(current, "shortcut_overrides", ShortcutOverrides())
            bindings, gesture_bindings, consume_overrides, mode_overrides, modifier_defaults = self._override_parts(overrides)

            if kind == "gesture":
                per_plugin = dict(gesture_bindings.get(plugin_id, {}))
                per_plugin.pop(binding_id, None)
                if per_plugin:
                    gesture_bindings[plugin_id] = per_plugin
                else:
                    gesture_bindings.pop(plugin_id, None)
            else:
                per_plugin = dict(bindings.get(plugin_id, {}))
                per_plugin.pop(binding_id, None)
                if per_plugin:
                    bindings[plugin_id] = per_plugin
                else:
                    bindings.pop(plugin_id, None)

            return replace(
                current,
                shortcut_overrides=ShortcutOverrides(
                    bindings=bindings,
                    gesture_bindings=gesture_bindings,
                    consume_event_overrides=consume_overrides,
                    mode_toggle_overrides=mode_overrides,
                    modifier_defaults=modifier_defaults,
                ),
            )

        updated = self._writer.request_update(mutator)
        try:
            self._app_ctx.shortcuts.apply_settings(updated)
        except Exception:
            log.debug("Failed to apply shortcut binding reset (best-effort)", exc_info=True)

    def _persist_consume(self, *, plugin_id: str, kind: str, binding_id: str, consume: bool) -> None:
        def mutator(current):
            overrides: ShortcutOverrides = getattr(current, "shortcut_overrides", ShortcutOverrides())
            bindings, gesture_bindings, consume_overrides, mode_overrides, modifier_defaults = self._override_parts(overrides)

            per_plugin = dict(consume_overrides.get(plugin_id, {}))
            key = binding_id if kind == "command" else f"gesture:{binding_id}"
            per_plugin[key] = bool(consume)
            consume_overrides[plugin_id] = per_plugin

            return replace(
                current,
                shortcut_overrides=ShortcutOverrides(
                    bindings=bindings,
                    gesture_bindings=gesture_bindings,
                    consume_event_overrides=consume_overrides,
                    mode_toggle_overrides=mode_overrides,
                    modifier_defaults=modifier_defaults,
                ),
            )

        updated = self._writer.request_update(mutator)
        try:
            self._app_ctx.shortcuts.apply_settings(updated)
        except Exception:
            log.debug("Failed to apply consume override change (best-effort)", exc_info=True)

    def _persist_consume_reset(self, *, plugin_id: str, kind: str, binding_id: str) -> None:
        def mutator(current):
            overrides: ShortcutOverrides = getattr(current, "shortcut_overrides", ShortcutOverrides())
            bindings, gesture_bindings, consume_overrides, mode_overrides, modifier_defaults = self._override_parts(overrides)

            per_plugin = dict(consume_overrides.get(plugin_id, {}))
            key = binding_id if kind == "command" else f"gesture:{binding_id}"
            per_plugin.pop(key, None)
            if per_plugin:
                consume_overrides[plugin_id] = per_plugin
            else:
                consume_overrides.pop(plugin_id, None)

            return replace(
                current,
                shortcut_overrides=ShortcutOverrides(
                    bindings=bindings,
                    gesture_bindings=gesture_bindings,
                    consume_event_overrides=consume_overrides,
                    mode_toggle_overrides=mode_overrides,
                    modifier_defaults=modifier_defaults,
                ),
            )

        updated = self._writer.request_update(mutator)
        try:
            self._app_ctx.shortcuts.apply_settings(updated)
        except Exception:
            log.debug("Failed to apply consume override reset (best-effort)", exc_info=True)

    @staticmethod
    def _mode_is_keyboard_only(*, default_chord: object, effective_chord: object) -> bool:
        """
        Return True if the binding represents a keyboard-only chord (no click/wheel tokens).

        Hold/Toggle mode is intended for keyboard-triggered stateful commands. Mouse and wheel
        chords are handled via widget gestures and do not participate in this mode UI.
        """
        raw = str(effective_chord or default_chord or "").strip()
        if not raw:
            return True
        return ("Click" not in raw) and ("Wheel" not in raw)

    def _on_mode_changed(self, plugin_id: str, command_id: str, is_toggle: bool) -> None:
        key = (plugin_id, "command", command_id)
        default_toggle = self._mode_defaults.get(key)
        if default_toggle is None:
            return
        self._persist_mode_toggle(plugin_id=plugin_id, command_id=command_id, is_toggle=is_toggle, default_toggle=default_toggle)

    def _on_mode_reset(self, plugin_id: str, command_id: str) -> None:
        key = (plugin_id, "command", command_id)
        default_toggle = self._mode_defaults.get(key)
        toggle = self._mode_toggles.get(key)
        if default_toggle is None or toggle is None:
            return
        toggle.set_current_id("toggle" if default_toggle else "hold", emit=False)
        self._persist_mode_toggle(plugin_id=plugin_id, command_id=command_id, is_toggle=default_toggle, default_toggle=default_toggle)

    def _persist_mode_toggle(self, *, plugin_id: str, command_id: str, is_toggle: bool, default_toggle: bool) -> None:
        def mutator(current):
            overrides: ShortcutOverrides = getattr(current, "shortcut_overrides", ShortcutOverrides())
            bindings, gesture_bindings, consume_overrides, mode_overrides, modifier_defaults = self._override_parts(overrides)

            per_plugin = dict(mode_overrides.get(plugin_id, {}))
            if bool(is_toggle) == bool(default_toggle):
                per_plugin.pop(command_id, None)
            else:
                per_plugin[command_id] = bool(is_toggle)
            if per_plugin:
                mode_overrides[plugin_id] = per_plugin
            else:
                mode_overrides.pop(plugin_id, None)

            return replace(
                current,
                shortcut_overrides=ShortcutOverrides(
                    bindings=bindings,
                    gesture_bindings=gesture_bindings,
                    consume_event_overrides=consume_overrides,
                    mode_toggle_overrides=mode_overrides,
                    modifier_defaults=modifier_defaults,
                ),
            )

        updated = self._writer.request_update(mutator)
        try:
            self._app_ctx.shortcuts.apply_settings(updated)
        except Exception:
            log.debug("Failed to apply hold/toggle override (best-effort)", exc_info=True)

    @staticmethod
    def _override_parts(overrides: ShortcutOverrides) -> tuple[dict, dict, dict, dict, dict]:
        """
        Return mutable copies of all override maps.

        This centralizes the "preserve fields we don't touch" logic so modifier defaults
        (and any future ShortcutOverrides fields) aren't accidentally dropped.
        """
        bindings = dict(getattr(overrides, "bindings", {}) or {})
        gesture_bindings = dict(getattr(overrides, "gesture_bindings", {}) or {})
        consume_overrides = dict(getattr(overrides, "consume_event_overrides", {}) or {})
        mode_overrides = dict(getattr(overrides, "mode_toggle_overrides", {}) or {})
        modifier_defaults = dict(getattr(overrides, "modifier_defaults", {}) or {})
        return bindings, gesture_bindings, consume_overrides, mode_overrides, modifier_defaults


__all__ = ["KeyboardShortcutsPreferencesPage"]
