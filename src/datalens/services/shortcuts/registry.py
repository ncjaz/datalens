from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.domain.system.shortcuts import GestureBindingSpec, GestureId, ShortcutCommandId, ShortcutCommandSpec, ShortcutPageSpec


ShortcutCallback = Callable[[], None]
log = get_logger(__name__)


@dataclass(frozen=True)
class RegisteredCommand:
    plugin_id: PluginId
    plugin_name: str
    page_id: str
    page_title: str
    section_id: str
    section_title: str
    spec: ShortcutCommandSpec
    callback: ShortcutCallback

    @property
    def command_id(self) -> ShortcutCommandId:
        return self.spec.command_id


@dataclass(frozen=True)
class RegisteredGesture:
    plugin_id: PluginId
    plugin_name: str
    page_id: str
    page_title: str
    section_id: str
    section_title: str
    spec: GestureBindingSpec

    @property
    def gesture_id(self) -> GestureId:
        return self.spec.gesture_id


@dataclass(frozen=True)
class RegisteredPage:
    plugin_id: PluginId
    plugin_name: str
    page: ShortcutPageSpec
    commands: tuple[RegisteredCommand, ...]
    gestures: tuple[RegisteredGesture, ...]


class ShortcutRegistry:
    """
    In-memory registry of shortcut pages + commands contributed by core/plugins.

    This registry is Qt-free and is safe to call from background threads.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pages: dict[tuple[str, str], RegisteredPage] = {}
        self._commands_by_plugin: dict[str, dict[str, RegisteredCommand]] = defaultdict(dict)
        self._gestures_by_plugin: dict[str, dict[str, RegisteredGesture]] = defaultdict(dict)

    def register_page(
        self,
        *,
        plugin_id: PluginId,
        plugin_name: str,
        page: ShortcutPageSpec,
        callbacks: Mapping[str, ShortcutCallback],
    ) -> None:
        """
        Register a page and its commands for `plugin_id`.

        `callbacks` are keyed by the command id string (local within the plugin).

        Gesture bindings (if provided on the page sections) are registered for
        persistence/UI discovery but are not dispatched globally (widgets use
        `GestureRouter` to drive press/drag/release semantics).
        """
        def _noop() -> None:
            return None

        plugin_id_s = str(plugin_id)
        plugin_name = str(plugin_name or "").strip() or plugin_id_s
        debug = log.isEnabledFor(10)  # logging.DEBUG, avoid importing logging in hot path
        if debug:
            log.debug(
                "Registering shortcut page",
                extra={
                    "operation": "shortcuts",
                    "phase": "register_page",
                    "plugin_id": plugin_id_s,
                    "page_id": str(page.page_id),
                },
            )

        commands: list[RegisteredCommand] = []
        gestures: list[RegisteredGesture] = []
        for section in page.sections:
            for cmd in section.commands:
                cmd_id_s = str(cmd.command_id)
                cb = callbacks.get(cmd_id_s)
                if cb is None:
                    if not bool(getattr(cmd, "dispatch_globally", True)):
                        cb = _noop
                    else:
                        raise KeyError(f"Missing callback for command_id={cmd_id_s!r} (plugin_id={plugin_id_s})")
                if not callable(cb):
                    raise TypeError(f"Callback for command_id={cmd_id_s!r} is not callable (plugin_id={plugin_id_s})")
                commands.append(
                    RegisteredCommand(
                        plugin_id=plugin_id,
                        plugin_name=plugin_name,
                        page_id=page.page_id,
                        page_title=page.title,
                        section_id=section.section_id,
                        section_title=section.title,
                        spec=cmd,
                        callback=cb,
                    )
                )
            for g in getattr(section, "gestures", ()):
                gestures.append(
                    RegisteredGesture(
                        plugin_id=plugin_id,
                        plugin_name=plugin_name,
                        page_id=page.page_id,
                        page_title=page.title,
                        section_id=section.section_id,
                        section_title=section.title,
                        spec=g,
                    )
                )

        with self._lock:
            by_cmd = self._commands_by_plugin[plugin_id_s]
            by_gesture = self._gestures_by_plugin[plugin_id_s]
            for item in commands:
                cmd_id_s = str(item.command_id)
                if cmd_id_s in by_cmd:
                    raise ValueError(f"Duplicate command_id={cmd_id_s!r} within plugin_id={plugin_id_s}")
            for item in gestures:
                gid = str(item.gesture_id)
                if gid in by_gesture:
                    raise ValueError(f"Duplicate gesture_id={gid!r} within plugin_id={plugin_id_s}")
            for item in commands:
                by_cmd[str(item.command_id)] = item
            for item in gestures:
                by_gesture[str(item.gesture_id)] = item
            self._pages[(plugin_id_s, page.page_id)] = RegisteredPage(
                plugin_id=plugin_id,
                plugin_name=plugin_name,
                page=page,
                commands=tuple(commands),
                gestures=tuple(gestures),
            )
        if debug:
            log.debug(
                "Registered shortcut page",
                extra={
                    "operation": "shortcuts",
                    "phase": "register_page_done",
                    "plugin_id": plugin_id_s,
                    "page_id": str(page.page_id),
                    "commands": len(commands),
                    "gestures": len(gestures),
                },
            )

    def unregister_plugin(self, plugin_id: PluginId) -> None:
        plugin_id_s = str(plugin_id)
        if log.isEnabledFor(10):
            log.debug(
                "Unregistering plugin shortcuts",
                extra={"operation": "shortcuts", "phase": "unregister_plugin", "plugin_id": plugin_id_s},
            )
        with self._lock:
            self._commands_by_plugin.pop(plugin_id_s, None)
            self._gestures_by_plugin.pop(plugin_id_s, None)
            for key in list(self._pages.keys()):
                if key[0] == plugin_id_s:
                    self._pages.pop(key, None)

    def pages_snapshot(self) -> tuple[RegisteredPage, ...]:
        with self._lock:
            return tuple(self._pages.values())

    def commands_snapshot(self) -> tuple[RegisteredCommand, ...]:
        with self._lock:
            out: list[RegisteredCommand] = []
            for by_cmd in self._commands_by_plugin.values():
                out.extend(by_cmd.values())
            return tuple(out)

    def gestures_snapshot(self) -> tuple[RegisteredGesture, ...]:
        with self._lock:
            out: list[RegisteredGesture] = []
            for by_g in self._gestures_by_plugin.values():
                out.extend(by_g.values())
            return tuple(out)

    def plugin_commands_snapshot(self, plugin_id: PluginId) -> tuple[RegisteredCommand, ...]:
        plugin_id_s = str(plugin_id)
        with self._lock:
            by_cmd = self._commands_by_plugin.get(plugin_id_s, {})
            return tuple(by_cmd.values())

    def plugin_gestures_snapshot(self, plugin_id: PluginId) -> tuple[RegisteredGesture, ...]:
        plugin_id_s = str(plugin_id)
        with self._lock:
            by_g = self._gestures_by_plugin.get(plugin_id_s, {})
            return tuple(by_g.values())
