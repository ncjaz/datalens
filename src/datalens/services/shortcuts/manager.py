"""
Runtime shortcuts service.

This module owns:

- Shortcut registration (per-plugin pages + callbacks)
- User overrides (from `AppSettings.shortcut_overrides`)
- Dispatch routing for the focused window + active workspace

This module does not own Qt input plumbing. The app installs a Qt event filter that
converts Qt events into chord strings and calls `ShortcutsService.dispatch(...)`.
See `datalens.ui.shortcuts.event_filter`.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

from PySide6.QtCore import QCoreApplication, QTimer

from PySide6.QtWidgets import QWidget

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.domain.system.settings import AppSettings
from datalens.domain.system.shortcuts import ShortcutOverrides, ShortcutPageSpec, ShortcutScope
from datalens.services.shortcuts.registry import RegisteredCommand, ShortcutRegistry
from datalens.services.workspace_state_service import WorkspaceStateService


log = get_logger(__name__)
_CORE_PLUGIN_ID = PluginId("core")


@dataclass(frozen=True)
class ShortcutConflict:
    plugin_id: PluginId
    scope: ShortcutScope
    chord: str
    binding_ids: tuple[str, ...]


@dataclass(frozen=True)
class ShortcutsSnapshot:
    pages: tuple[dict[str, Any], ...]
    conflicts: tuple[ShortcutConflict, ...]
    # Snapshot of the current global modifier defaults (semantic, persisted in settings.json).
    # Keys are "primary"/"secondary"; values are "Shift"/"Ctrl"/"Alt"/"Meta".
    modifier_defaults: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ShortcutDispatchResult:
    handled: bool
    consume_event: bool


@dataclass(frozen=True)
class _RuntimeMaps:
    global_map: Mapping[str, tuple[RegisteredCommand, bool]]
    window_global_map: Mapping[str, tuple[RegisteredCommand, bool]]
    window_plugin_map: Mapping[str, Mapping[str, tuple[RegisteredCommand, bool]]]
    workspace_map: Mapping[str, Mapping[str, tuple[RegisteredCommand, bool]]]
    conflicts: tuple[ShortcutConflict, ...]


class ShortcutsService:
    """
    Runtime shortcut manager (registry + user overrides + dispatch).

    Design notes:

    - Shortcuts are routed by the focused top-level window.
    - `WORKSPACE` scope is routed by the active workspace plugin id.
    - `WINDOW` scope is routed by the focused window and active plugin id, which allows
      different plugin windows to reuse the same chords without conflicts.
    - `GLOBAL` scope is routed for the focused window and is unique across the app.
    - Callbacks must be fast. If a callback needs I/O or heavy work, schedule it onto
      background systems (loader/threadpool/DB executors) and return quickly.

    UI delivery is owned by a Qt event filter (see `datalens.ui.shortcuts.event_filter`).
    """

    _WINDOW_PLUGIN_ID_PROPERTY = "datalens.plugin_id"

    def __init__(self, *, workspace_state: WorkspaceStateService) -> None:
        self._workspace_state = workspace_state
        self._registry = ShortcutRegistry()

        self._lock = threading.Lock()
        self._overrides = ShortcutOverrides()
        self._runtime = _RuntimeMaps(global_map={}, window_global_map={}, window_plugin_map={}, workspace_map={}, conflicts=())

        self._changed_lock = threading.Lock()
        self._changed_callbacks: list[Callable[[], None]] = []

    @property
    def registry(self) -> ShortcutRegistry:
        """Return the underlying shortcut registry (pages + declared defaults)."""
        return self._registry

    def apply_settings(self, settings: AppSettings) -> None:
        """Apply shortcut overrides from `AppSettings` and rebuild runtime maps."""
        overrides = getattr(settings, "shortcut_overrides", ShortcutOverrides())
        self.set_overrides(overrides)

    def set_overrides(self, overrides: ShortcutOverrides) -> None:
        """Replace overrides and rebuild the runtime dispatch maps."""
        if log.isEnabledFor(10):  # logging.DEBUG
            bindings_count = sum(len(v) for v in getattr(overrides, "bindings", {}).values())
            gestures_count = sum(len(v) for v in getattr(overrides, "gesture_bindings", {}).values())
            consume_count = sum(len(v) for v in getattr(overrides, "consume_event_overrides", {}).values())
            mode_count = sum(len(v) for v in getattr(overrides, "mode_toggle_overrides", {}).values())
            log.debug(
                "Applying shortcut overrides",
                extra={
                    "operation": "shortcuts",
                    "phase": "apply_overrides",
                    "plugins": len(getattr(overrides, "bindings", {})),
                    "bindings": bindings_count,
                    "gestures": gestures_count,
                    "consume_overrides": consume_count,
                    "mode_overrides": mode_count,
                    "modifier_defaults": dict(getattr(overrides, "modifier_defaults", {}) or {}),
                },
            )
        with self._lock:
            self._overrides = overrides
        self._rebuild()

    def register_page(
        self,
        *,
        plugin_id: PluginId,
        plugin_name: str,
        page: ShortcutPageSpec,
        callbacks: Mapping[str, Callable[[], None]],
    ) -> None:
        """
        Register a plugin shortcuts page plus the callbacks for its commands.

        `callbacks` is keyed by `command_id` (string form). The registry validates that
        all referenced command ids exist and that scopes are well-formed.

        This can be called from `BasePlugin.register_shortcuts(...)`.
        """
        if log.isEnabledFor(10):  # logging.DEBUG
            log.debug(
                "Registering shortcuts page",
                extra={
                    "operation": "shortcuts",
                    "phase": "register_page",
                    "plugin_id": str(plugin_id),
                    "page_id": str(page.page_id),
                },
            )
        typed_callbacks: dict[str, Callable[[], None]] = dict(callbacks)
        self._registry.register_page(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            page=page,
            callbacks=typed_callbacks,  # validated in registry
        )
        self._rebuild()

    def unregister_plugin(self, plugin_id: PluginId) -> None:
        """Remove all pages/commands for a plugin and rebuild runtime maps."""
        if log.isEnabledFor(10):  # logging.DEBUG
            log.debug(
                "Unregistering plugin shortcuts",
                extra={"operation": "shortcuts", "phase": "unregister_plugin", "plugin_id": str(plugin_id)},
            )
        self._registry.unregister_plugin(plugin_id)
        self._rebuild()

    def subscribe_changed(self, callback: Callable[[], None]) -> Callable[[], None]:
        """
        Subscribe to shortcut map changes (pages registered/unregistered or overrides applied).

        The callback is delivered on the Qt event loop when a Qt application instance exists.
        This makes it safe for UI code to update widgets/tooltips from the callback even if
        the underlying change originated from a background thread (e.g. plugin load).

        Returns an unsubscribe function.
        """

        with self._changed_lock:
            self._changed_callbacks.append(callback)

        def unsubscribe() -> None:
            with self._changed_lock:
                try:
                    self._changed_callbacks.remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    def _notify_changed(self) -> None:
        with self._changed_lock:
            callbacks = tuple(self._changed_callbacks)

        if not callbacks:
            return

        def deliver(cb: Callable[[], None]) -> None:
            try:
                cb()
            except Exception:
                log.warning(
                    "Shortcuts changed callback failed",
                    exc_info=True,
                    extra={"operation": "shortcuts", "phase": "changed_callback_error"},
                )

        app = QCoreApplication.instance()
        if app is not None:
            for cb in callbacks:
                QTimer.singleShot(0, lambda cb=cb: deliver(cb))
            return

        for cb in callbacks:
            deliver(cb)

    # ------------------------------------------------------------------
    # Snapshot / UI helpers
    # ------------------------------------------------------------------

    def snapshot(self) -> ShortcutsSnapshot:
        """
        Return a UI-friendly snapshot of all registered pages plus detected conflicts.

        Intended for the Preferences UI to render and edit user overrides.
        """
        pages_out: list[dict[str, Any]] = []
        modifier_defaults = self._get_modifier_defaults()
        for page in self._registry.pages_snapshot():
            overrides_for_plugin = self._overrides.for_plugin(page.plugin_id)
            gesture_overrides_for_plugin = self._overrides.gestures_for_plugin(page.plugin_id)
            pages_out.append(
                {
                    "plugin_id": str(page.plugin_id),
                    "plugin_name": page.plugin_name,
                    "page_id": page.page.page_id,
                    "page_title": page.page.title,
                    "sections": [
                        {
                            "section_id": s.section_id,
                            "section_title": s.title,
                            "commands": [
                                {
                                    "command_id": str(c.command_id),
                                    "title": c.title,
                                    "description": c.description,
                                    "default_chord": self._resolve_modifier_placeholders(
                                        str(c.default_chord)
                                    )
                                    if c.default_chord is not None
                                    else None,
                                    "scope": str(c.scope.value),
                                    "allow_in_text_inputs": bool(c.allow_in_text_inputs),
                                    "dispatch_globally": bool(getattr(c, "dispatch_globally", True)),
                                    "mode_toggle_default": getattr(c, "mode_toggle_default", None),
                                    "mode_toggle": self.get_effective_mode_toggle(
                                        plugin_id=page.plugin_id,
                                        command_id=str(c.command_id),
                                        default=getattr(c, "mode_toggle_default", None),
                                    ),
                                    "consume_event": self.get_effective_consume_event(
                                        plugin_id=page.plugin_id, command_id=str(c.command_id), default=bool(c.consume_event)
                                    ),
                                    "effective_chord": self.get_effective_chord(
                                        plugin_id=page.plugin_id,
                                        command_id=str(c.command_id),
                                        default=str(c.default_chord) if c.default_chord is not None else None,
                                    ),
                                    "is_overridden": str(c.command_id) in overrides_for_plugin,
                                }
                                for c in s.commands
                            ],
                            "gestures": [
                                {
                                    "gesture_id": str(g.gesture_id),
                                    "title": g.title,
                                    "description": g.description,
                                    "default_chord": self._resolve_modifier_placeholders(
                                        str(g.begin_chord)
                                    )
                                    if g.begin_chord is not None
                                    else None,
                                    "scope": str(g.scope.value),
                                    "consume_event": self.get_effective_gesture_consume_event(
                                        plugin_id=page.plugin_id,
                                        gesture_id=str(g.gesture_id),
                                        default=bool(g.consume_event),
                                    ),
                                    "effective_chord": self.get_effective_gesture_chord(
                                        plugin_id=page.plugin_id,
                                        gesture_id=str(g.gesture_id),
                                        default=str(g.begin_chord) if g.begin_chord is not None else None,
                                    ),
                                    "is_overridden": str(g.gesture_id) in gesture_overrides_for_plugin,
                                    "uses_modifier_defaults": self._chord_uses_modifier_defaults(
                                        str(g.begin_chord) if g.begin_chord is not None else ""
                                    ),
                                }
                                for g in getattr(s, "gestures", ())
                            ],
                        }
                        for s in page.page.sections
                    ],
                }
            )
        runtime = self._runtime
        return ShortcutsSnapshot(pages=tuple(pages_out), conflicts=runtime.conflicts, modifier_defaults=modifier_defaults)

    def get_effective_chord(self, *, plugin_id: PluginId, command_id: str, default: str | None = None) -> str | None:
        """
        Resolve the effective chord for a command.

        Resolution order:
        1) User override (including unbind via `None`)
        2) The provided `default` argument (if given)
        3) The command's registered default chord (if any)

        Returns `None` when the command is unbound or has no default.

        Most UI callers should prefer `get_effective_command_chord(...)`.
        """
        overrides_for_plugin = self._overrides.for_plugin(plugin_id)
        if command_id in overrides_for_plugin:
            chord = overrides_for_plugin.get(command_id)
            return self._resolve_modifier_placeholders(str(chord).strip()) if chord else None
        if default is not None:
            return self._resolve_modifier_placeholders(str(default).strip()) if str(default).strip() else None
        for cmd in self._registry.plugin_commands_snapshot(plugin_id):
            if str(cmd.command_id) == command_id:
                if cmd.spec.default_chord is None:
                    return None
                return self._resolve_modifier_placeholders(str(cmd.spec.default_chord).strip())
        return None

    def get_effective_command_chord(self, *, plugin_id: PluginId, command_id: str) -> str | None:
        """
        Return the effective chord for a command (user override if present, else default).

        This is a convenience wrapper intended for UI/tooltips so callers don't
        need to know about defaults.
        """

        return self.get_effective_chord(plugin_id=plugin_id, command_id=command_id, default=None)

    def get_effective_consume_event(self, *, plugin_id: PluginId, command_id: str, default: bool) -> bool:
        """Return the effective `consume_event` value (user override if present, else `default`)."""
        by_plugin = self._overrides.consume_overrides_for_plugin(plugin_id)
        if command_id in by_plugin:
            return bool(by_plugin.get(command_id))
        return bool(default)

    def get_effective_mode_toggle(
        self, *, plugin_id: PluginId, command_id: str, default: bool | None
    ) -> bool | None:
        """
        Return the effective Hold/Toggle mode for a command, if supported.

        `default` is the registered `ShortcutCommandSpec.mode_toggle_default`:
        - `None`: mode selection not supported
        - `False`: default Hold
        - `True`: default Toggle
        """
        if default is None:
            return None
        by_plugin = self._overrides.mode_toggle_overrides_for_plugin(plugin_id)
        if command_id in by_plugin:
            return bool(by_plugin.get(command_id))
        return bool(default)

    def get_effective_command_mode_toggle(self, *, plugin_id: PluginId, command_id: str) -> bool | None:
        """
        Return the effective Hold/Toggle mode for a command (user override if present, else default).

        This helper falls back to the registered `ShortcutCommandSpec.mode_toggle_default`.
        """
        default: bool | None = None
        for cmd in self._registry.plugin_commands_snapshot(plugin_id):
            if str(cmd.command_id) == command_id:
                default = getattr(cmd.spec, "mode_toggle_default", None)
                break
        return self.get_effective_mode_toggle(plugin_id=plugin_id, command_id=command_id, default=default)

    def get_effective_gesture_chord(
        self, *, plugin_id: PluginId, gesture_id: str, default: str | None = None
    ) -> str | None:
        """
        Resolve the effective begin chord for a gesture (press/drag/release tool).

        Gestures are not dispatched globally; widgets/tools should read the effective begin
        chord and drive their own gesture lifecycle.
        """
        overrides_for_plugin = self._overrides.gestures_for_plugin(plugin_id)
        if gesture_id in overrides_for_plugin:
            chord = overrides_for_plugin.get(gesture_id)
            return self._resolve_modifier_placeholders(str(chord).strip()) if chord else None
        if default is not None:
            return self._resolve_modifier_placeholders(str(default).strip()) if str(default).strip() else None
        for g in self._registry.plugin_gestures_snapshot(plugin_id):
            if str(g.gesture_id) == gesture_id:
                if g.spec.begin_chord is None:
                    return None
                return self._resolve_modifier_placeholders(str(g.spec.begin_chord).strip())
        return None

    def _get_modifier_defaults(self) -> dict[str, str]:
        """
        Return the effective global modifier defaults.

        These are semantic user settings (not UI state) and are used to resolve
        placeholder chords like `Primary+LeftClick` in gesture bindings.
        """
        defaults = dict(getattr(self._overrides, "modifier_defaults", {}) or {})
        primary = str(defaults.get("primary") or "").strip() or "Shift"
        secondary = str(defaults.get("secondary") or "").strip() or "Ctrl"
        # Enforce canonical names used by chord formatting.
        primary = primary[:1].upper() + primary[1:].lower()
        secondary = secondary[:1].upper() + secondary[1:].lower()
        if primary not in ("Shift", "Ctrl", "Alt", "Meta"):
            primary = "Shift"
        if secondary not in ("Shift", "Ctrl", "Alt", "Meta"):
            secondary = "Ctrl"
        return {"primary": primary, "secondary": secondary}

    @staticmethod
    def _chord_uses_modifier_defaults(chord: str) -> bool:
        """
        Return True if a chord uses `Primary` or `Secondary` placeholder tokens.

        This is used by the Preferences UI to decide whether a binding "follows"
        the global modifier defaults.
        """
        raw = str(chord or "").strip().lower()
        if not raw:
            return False
        return ("primary" in raw.split("+")) or ("secondary" in raw.split("+"))

    def _resolve_modifier_placeholders(self, chord: str) -> str:
        """
        Resolve placeholder tokens `Primary` and `Secondary` into concrete modifiers.

        Resolution is based on `ShortcutOverrides.modifier_defaults`:
        - Primary -> defaults["primary"] (fallback Shift)
        - Secondary -> defaults["secondary"] (fallback Ctrl)
        """
        raw = str(chord or "").strip()
        if not raw:
            return ""
        parts = [p.strip() for p in raw.split("+") if p.strip()]
        if not parts:
            return raw
        defaults = self._get_modifier_defaults()
        out: list[str] = []
        for p in parts:
            low = p.lower()
            if low == "primary":
                out.append(defaults["primary"])
            elif low == "secondary":
                out.append(defaults["secondary"])
            else:
                out.append(p)
        return "+".join(out)

    def get_effective_gesture_consume_event(self, *, plugin_id: PluginId, gesture_id: str, default: bool) -> bool:
        """Return the effective consume flag for a gesture (user override if present, else `default`)."""
        by_plugin = self._overrides.consume_overrides_for_plugin(plugin_id)
        key = f"gesture:{gesture_id}"
        if key in by_plugin:
            return bool(by_plugin.get(key))
        return bool(default)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def resolve_window_plugin_id(self, window: QWidget | None) -> PluginId | None:
        """
        Return the workspace plugin id associated with a top-level window, if known.

        The event filter passes the focused top-level window. For the main window we fall
        back to `WorkspaceStateService.active_workspace_id`. Plugin popout windows can be
        explicitly tagged via `tag_window_with_plugin(...)`.
        """
        if window is None:
            return None
        try:
            raw = window.property(self._WINDOW_PLUGIN_ID_PROPERTY)
            if isinstance(raw, str) and raw.strip():
                return PluginId(raw)
        except Exception:
            pass
        try:
            snap = self._workspace_state.snapshot()
            active = snap.active_workspace_id
            if active:
                return PluginId(str(active))
        except Exception:
            pass
        return None

    def tag_window_with_plugin(self, window: QWidget, plugin_id: PluginId) -> None:
        """
        Mark a top-level window as "owned" by a plugin for routing.

        This is used for plugin popout windows so shortcuts route correctly when
        multiple plugin windows are open.
        """
        window.setProperty(self._WINDOW_PLUGIN_ID_PROPERTY, str(plugin_id))
        if log.isEnabledFor(10):  # logging.DEBUG
            try:
                window_name = window.objectName() or type(window).__name__
            except Exception:
                window_name = type(window).__name__
            log.debug(
                "Tagged window with plugin id",
                extra={
                    "operation": "shortcuts",
                    "phase": "tag_window",
                    "plugin_id": str(plugin_id),
                    "window": str(window_name),
                },
            )

    def dispatch(
        self,
        *,
        chord: str,
        window: QWidget | None,
        focused_widget: QWidget | None,
        event_is_text_input: bool,
    ) -> ShortcutDispatchResult:
        """
        Attempt to dispatch `chord`.

        `chord` is the normalized chord string produced by the UI event filter
        (examples: `Ctrl+S`, `Shift+LeftClick`, `Ctrl+WheelUp`).

        Returns a dispatch result that indicates both:
        - whether a shortcut callback ran (`handled`)
        - whether the underlying Qt event should be consumed (`consume_event`)

        `event_is_text_input` indicates the focused widget is a text input; this method
        enforces `allow_in_text_inputs` accordingly.

        This must be fast and non-blocking; do not do I/O here.
        """
        if not chord:
            return ShortcutDispatchResult(handled=False, consume_event=False)
        runtime = self._runtime
        active_plugin = self.resolve_window_plugin_id(window)
        debug = log.isEnabledFor(10)  # logging.DEBUG

        if active_plugin is not None:
            by_chord = runtime.workspace_map.get(str(active_plugin), {})
            found = by_chord.get(chord)
            if found is not None:
                cmd, consume = found
                if event_is_text_input and not bool(cmd.spec.allow_in_text_inputs):
                    if debug:
                        log.debug(
                            "Shortcut blocked by text input",
                            extra={
                                "operation": "shortcuts",
                                "phase": "blocked_text_input",
                                "scope": "workspace",
                                "plugin_id": str(cmd.plugin_id),
                                "command_id": str(cmd.command_id),
                                "chord": str(chord),
                            },
                        )
                    return ShortcutDispatchResult(handled=False, consume_event=False)
                if debug:
                    log.debug(
                        "Shortcut dispatched",
                        extra={
                            "operation": "shortcuts",
                            "phase": "dispatch",
                            "scope": "workspace",
                            "plugin_id": str(cmd.plugin_id),
                            "command_id": str(cmd.command_id),
                            "chord": str(chord),
                            "consume_event": bool(consume),
                        },
                    )
                self._invoke(cmd)
                return ShortcutDispatchResult(handled=True, consume_event=bool(consume))

        if active_plugin is not None:
            by_chord = runtime.window_plugin_map.get(str(active_plugin), {})
            found = by_chord.get(chord)
            if found is not None:
                cmd, consume = found
                if event_is_text_input and not bool(cmd.spec.allow_in_text_inputs):
                    if debug:
                        log.debug(
                            "Shortcut blocked by text input",
                            extra={
                                "operation": "shortcuts",
                                "phase": "blocked_text_input",
                                "scope": "window_plugin",
                                "plugin_id": str(cmd.plugin_id),
                                "command_id": str(cmd.command_id),
                                "chord": str(chord),
                            },
                        )
                    return ShortcutDispatchResult(handled=False, consume_event=False)
                if debug:
                    log.debug(
                        "Shortcut dispatched",
                        extra={
                            "operation": "shortcuts",
                            "phase": "dispatch",
                            "scope": "window_plugin",
                            "plugin_id": str(cmd.plugin_id),
                            "command_id": str(cmd.command_id),
                            "chord": str(chord),
                            "consume_event": bool(consume),
                        },
                    )
                self._invoke(cmd)
                return ShortcutDispatchResult(handled=True, consume_event=bool(consume))

        found = runtime.window_global_map.get(chord)
        if found is not None:
            cmd, consume = found
            if event_is_text_input and not bool(cmd.spec.allow_in_text_inputs):
                if debug:
                    log.debug(
                        "Shortcut blocked by text input",
                        extra={
                            "operation": "shortcuts",
                            "phase": "blocked_text_input",
                            "scope": "window_global",
                            "plugin_id": str(cmd.plugin_id),
                            "command_id": str(cmd.command_id),
                            "chord": str(chord),
                        },
                    )
                return ShortcutDispatchResult(handled=False, consume_event=False)
            if debug:
                log.debug(
                    "Shortcut dispatched",
                    extra={
                        "operation": "shortcuts",
                        "phase": "dispatch",
                        "scope": "window_global",
                        "plugin_id": str(cmd.plugin_id),
                        "command_id": str(cmd.command_id),
                        "chord": str(chord),
                        "consume_event": bool(consume),
                    },
                )
            self._invoke(cmd)
            return ShortcutDispatchResult(handled=True, consume_event=bool(consume))

        found = runtime.global_map.get(chord)
        if found is not None:
            cmd, consume = found
            if event_is_text_input and not bool(cmd.spec.allow_in_text_inputs):
                if debug:
                    log.debug(
                        "Shortcut blocked by text input",
                        extra={
                            "operation": "shortcuts",
                            "phase": "blocked_text_input",
                            "scope": "global",
                            "plugin_id": str(cmd.plugin_id),
                            "command_id": str(cmd.command_id),
                            "chord": str(chord),
                        },
                    )
                return ShortcutDispatchResult(handled=False, consume_event=False)
            if debug:
                log.debug(
                    "Shortcut dispatched",
                    extra={
                        "operation": "shortcuts",
                        "phase": "dispatch",
                        "scope": "global",
                        "plugin_id": str(cmd.plugin_id),
                        "command_id": str(cmd.command_id),
                        "chord": str(chord),
                        "consume_event": bool(consume),
                    },
                )
            self._invoke(cmd)
            return ShortcutDispatchResult(handled=True, consume_event=bool(consume))
        return ShortcutDispatchResult(handled=False, consume_event=False)

    def _invoke(self, cmd: RegisteredCommand) -> None:
        try:
            cmd.callback()
        except Exception:
            log.warning(
                "Shortcut callback failed",
                exc_info=True,
                extra={
                    "operation": "shortcuts",
                    "phase": "callback_error",
                    "plugin_id": str(cmd.plugin_id),
                    "command_id": str(cmd.command_id),
                },
            )

    # ------------------------------------------------------------------
    # Rebuild (defaults + overrides -> runtime maps)
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        started = time.perf_counter()
        commands = self._registry.commands_snapshot()
        overrides = self._overrides.bindings
        consume_overrides = self._overrides.consume_event_overrides
        debug = log.isEnabledFor(10)  # logging.DEBUG

        conflicts_guard: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        conflicts_report: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        workspace_map: dict[str, dict[str, tuple[RegisteredCommand, bool]]] = defaultdict(dict)
        window_global_map: dict[str, tuple[RegisteredCommand, bool]] = {}
        window_plugin_map: dict[str, dict[str, tuple[RegisteredCommand, bool]]] = defaultdict(dict)
        global_map: dict[str, tuple[RegisteredCommand, bool]] = {}

        # Deterministic order: registry snapshot order.
        for cmd in commands:
            plugin_id_s = str(cmd.plugin_id)
            cmd_id_s = str(cmd.command_id)
            overrides_for_plugin = overrides.get(plugin_id_s, {})
            if cmd_id_s in overrides_for_plugin:
                chord = overrides_for_plugin.get(cmd_id_s)
            else:
                chord = str(cmd.spec.default_chord) if cmd.spec.default_chord is not None else None
            if chord is None or not str(chord).strip():
                continue
            chord_s = str(chord)
            scope = cmd.spec.scope

            # Conflicts:
            # - WORKSPACE scope: unique per plugin (routed by active workspace plugin id).
            # - WINDOW scope: unique per plugin (routed by focused window + active plugin id).
            #   Core may also register WINDOW shortcuts; those are treated as window-global.
            # - GLOBAL scope: unique across *all* plugins.
            if scope == ShortcutScope.GLOBAL:
                conflict_key = ("global", scope.value, chord_s)
                conflicts_guard[conflict_key].append(f"{plugin_id_s}:{cmd_id_s}")
                conflicts_report[conflict_key].append(f"{plugin_id_s}:{cmd_id_s}")
            elif scope == ShortcutScope.WINDOW and cmd.plugin_id == _CORE_PLUGIN_ID:
                conflict_key = ("window_global", scope.value, chord_s)
                conflicts_guard[conflict_key].append(f"{plugin_id_s}:{cmd_id_s}")
                conflicts_report[conflict_key].append(f"{plugin_id_s}:{cmd_id_s}")
            else:
                conflict_key = (plugin_id_s, scope.value, chord_s)
                conflicts_guard[conflict_key].append(cmd_id_s)
                conflicts_report[conflict_key].append(cmd_id_s)
            if len(conflicts_guard[conflict_key]) > 1:
                # Don't register a second binding for the same chord/scope.
                continue

            if not bool(getattr(cmd.spec, "dispatch_globally", True)):
                # Some commands are declared for Preferences/UI discovery only and are
                # handled by widget-local input logic (e.g. Hold/Toggle actions).
                continue

            consume = bool(cmd.spec.consume_event)
            by_consume = consume_overrides.get(plugin_id_s, {})
            if cmd_id_s in by_consume:
                consume = bool(by_consume.get(cmd_id_s))

            if scope == ShortcutScope.WORKSPACE:
                workspace_map[plugin_id_s][chord_s] = (cmd, consume)
            elif scope == ShortcutScope.WINDOW:
                if cmd.plugin_id == _CORE_PLUGIN_ID:
                    window_global_map[chord_s] = (cmd, consume)
                else:
                    window_plugin_map[plugin_id_s][chord_s] = (cmd, consume)
            else:
                global_map[chord_s] = (cmd, consume)

        # Add gesture bindings to conflict reporting (these are not dispatched globally).
        gesture_overrides = self._overrides.gesture_bindings
        for g in self._registry.gestures_snapshot():
            plugin_id_s = str(g.plugin_id)
            gesture_id_s = str(g.gesture_id)
            overrides_for_plugin = gesture_overrides.get(plugin_id_s, {})
            if gesture_id_s in overrides_for_plugin:
                chord = overrides_for_plugin.get(gesture_id_s)
            else:
                chord = str(g.spec.begin_chord) if g.spec.begin_chord is not None else None
            if chord is None or not str(chord).strip():
                continue
            chord_s = str(chord)
            scope = g.spec.scope
            if scope == ShortcutScope.GLOBAL:
                conflict_key = ("global", scope.value, chord_s)
                conflicts_report[conflict_key].append(f"{plugin_id_s}:gesture:{gesture_id_s}")
            else:
                conflict_key = (plugin_id_s, scope.value, chord_s)
                conflicts_report[conflict_key].append(f"gesture:{gesture_id_s}")

        conflict_out: list[ShortcutConflict] = []
        for (plugin_id_s, scope_s, chord), binding_ids in conflicts_report.items():
            if len(binding_ids) <= 1:
                continue
            try:
                scope = ShortcutScope(scope_s)
            except Exception:
                scope = ShortcutScope.GLOBAL
            conflict_out.append(
                ShortcutConflict(
                    plugin_id=PluginId(plugin_id_s),
                    scope=scope,
                    chord=chord,
                    binding_ids=tuple(binding_ids),
                )
            )

        runtime = _RuntimeMaps(
            global_map=dict(global_map),
            window_global_map=dict(window_global_map),
            window_plugin_map={k: dict(v) for k, v in window_plugin_map.items()},
            workspace_map={k: dict(v) for k, v in workspace_map.items()},
            conflicts=tuple(conflict_out),
        )
        with self._lock:
            self._runtime = runtime

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if debug:
            log.debug(
                "Shortcuts rebuilt",
                extra={
                    "operation": "shortcuts",
                    "phase": "rebuild_done",
                    "elapsed_ms": round(elapsed_ms, 1),
                    "commands": len(commands),
                    "conflicts": len(conflict_out),
                },
            )
        if elapsed_ms >= 50.0:
            log.info(
                "Shortcuts rebuild took %.1f ms",
                elapsed_ms,
                extra={"operation": "shortcuts", "phase": "rebuild"},
            )

        self._notify_changed()
