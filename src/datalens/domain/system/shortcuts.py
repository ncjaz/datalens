from __future__ import annotations

"""
Shortcut domain contracts (V2).

These are *pure* domain dataclasses used by the runtime registry, persistence,
and UI preferences pages. They deliberately avoid Qt types so they can be
serialized and tested without a GUI.

See `datalens/src/review_and_plan/shortcuts_system.md` for the full design.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, NewType

from datalens.domain.plugin import PluginId


ShortcutCommandId = NewType("ShortcutCommandId", str)
ShortcutChord = NewType("ShortcutChord", str)
GestureId = NewType("GestureId", str)


class ShortcutScope(str, Enum):
    """
    Where a shortcut binding is eligible to fire.

    Routing is determined by the currently focused top-level window and the
    active workspace within that window (if any).
    """

    GLOBAL = "global"
    WINDOW = "window"
    WORKSPACE = "workspace"


class GesturePhase(str, Enum):
    """Lifecycle phase for stateful input gestures (press/hold/drag/release)."""

    BEGIN = "begin"
    UPDATE = "update"
    END = "end"
    CANCEL = "cancel"


@dataclass(frozen=True)
class ShortcutCommandSpec:
    """
    A single user-facing command that can be bound to an input chord.

    `command_id` must be unique within a plugin.

    `default_chord` is a canonical chord string (e.g. ``Ctrl+M``,
    ``Ctrl+LeftClick``). Parsing/normalization is owned by the runtime layer.

    `dispatch_globally` controls whether the application-level shortcuts event filter
    should dispatch this command via `ShortcutsService.dispatch(...)`.

    `mode_toggle_default` enables the V1-style Hold/Toggle mode selector in Preferences.
    - `None`: no mode toggle UI (stateless command)
    - `False`: default is Hold
    - `True`: default is Toggle
    """

    command_id: ShortcutCommandId
    title: str
    description: str | None = None
    default_chord: ShortcutChord | None = None
    scope: ShortcutScope = ShortcutScope.WORKSPACE
    allow_in_text_inputs: bool = False
    consume_event: bool = False
    dispatch_globally: bool = True
    mode_toggle_default: bool | None = None


@dataclass(frozen=True)
class GestureBindingSpec:
    """
    A stateful input binding (press/hold/move/release) for widget-level tools.

    These are *not* dispatched by the global shortcuts event filter. Widgets
    opt-in by using a `GestureRouter` (runtime/UI layer) to drive the phases.

    `begin_chord` uses the same canonical chord string format as shortcuts
    (e.g. ``Shift+LeftClick``). The chord is matched on `MouseButtonPress`.
    """

    gesture_id: GestureId
    title: str
    description: str | None = None
    begin_chord: ShortcutChord | None = None
    scope: ShortcutScope = ShortcutScope.WORKSPACE
    consume_event: bool = True


@dataclass(frozen=True)
class ShortcutSectionSpec:
    """A logical grouping of commands within a shortcuts page."""

    section_id: str
    title: str
    commands: tuple[ShortcutCommandSpec, ...] = field(default_factory=tuple)
    gestures: tuple[GestureBindingSpec, ...] = field(default_factory=tuple)
    description: str | None = None


@dataclass(frozen=True)
class ShortcutPageSpec:
    """
    A page contributed by core or a plugin to the shortcuts UI.

    A plugin may contribute multiple pages, but most will only need one.
    """

    page_id: str
    title: str
    sections: tuple[ShortcutSectionSpec, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ShortcutOverrides:
    """
    Persisted user overrides for shortcuts.

    Storage is keyed by plugin_id -> command_id -> chord (or None to unbind).

    This is stored inside `AppSettings` (semantic user preferences), not in
    QSettings (UI geometry/state).
    """

    bindings: Mapping[str, Mapping[str, str | None]] = field(default_factory=dict)
    gesture_bindings: Mapping[str, Mapping[str, str | None]] = field(default_factory=dict)
    consume_event_overrides: Mapping[str, Mapping[str, bool]] = field(default_factory=dict)
    mode_toggle_overrides: Mapping[str, Mapping[str, bool]] = field(default_factory=dict)
    # Global defaults used by "modifier-click" style gesture bindings. These are
    # stored here (not QSettings) so plugins can rely on a single semantic source
    # of truth and so the Preferences -> Keyboard Shortcuts page can edit them.
    #
    # Keys are "primary" and "secondary"; values are one of:
    # "Shift", "Ctrl", "Alt", "Meta".
    modifier_defaults: Mapping[str, str] = field(default_factory=dict)

    def for_plugin(self, plugin_id: PluginId) -> Mapping[str, str | None]:
        return self.bindings.get(str(plugin_id), {})

    def gestures_for_plugin(self, plugin_id: PluginId) -> Mapping[str, str | None]:
        return self.gesture_bindings.get(str(plugin_id), {})

    def consume_overrides_for_plugin(self, plugin_id: PluginId) -> Mapping[str, bool]:
        return self.consume_event_overrides.get(str(plugin_id), {})

    def mode_toggle_overrides_for_plugin(self, plugin_id: PluginId) -> Mapping[str, bool]:
        return self.mode_toggle_overrides.get(str(plugin_id), {})


__all__ = [
    "GestureBindingSpec",
    "GestureId",
    "GesturePhase",
    "PluginId",
    "ShortcutChord",
    "ShortcutCommandId",
    "ShortcutCommandSpec",
    "ShortcutOverrides",
    "ShortcutPageSpec",
    "ShortcutScope",
    "ShortcutSectionSpec",
]
