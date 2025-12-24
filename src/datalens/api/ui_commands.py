from __future__ import annotations

"""
Plugin-facing helpers for defining a command once and reusing it for both:
- A `DatalensButton` click handler (UI)
- A managed shortcuts registration entry (Preferences -> Keyboard Shortcuts)

Design intent:
- Keep the shortcuts system as the source of truth (avoid `QAction.setShortcut(...)` / `QShortcut`)
  to prevent double-trigger behavior.
- Keep declarations mostly Qt-free so plugins can register shortcuts from background loader stages.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.domain.system.shortcuts import (
    ShortcutChord,
    ShortcutCommandId,
    ShortcutCommandSpec,
    ShortcutPageSpec,
    ShortcutScope,
    ShortcutSectionSpec,
)
from datalens.services.plugins.runtime.contracts import PluginAppContext
from datalens.ui.shortcuts.tooltips import attach_effective_shortcut_tooltip


log = get_logger(__name__)


def _attach_shortcut_tooltip(
    *,
    target: object,
    plugin_id: PluginId,
    command_id: str,
    title: str,
    description: str | None,
    include_shortcut: bool = True,
) -> Callable[[], None]:
    """
    Attach a live-updating "effective shortcut" tooltip to any Qt object that supports `setToolTip(str)`.

    This intentionally uses the managed shortcuts service as the source of truth, and it does not set
    `QAction.setShortcut` or `QShortcut`.
    """

    return attach_effective_shortcut_tooltip(
        target=target,
        plugin_id=plugin_id,
        command_id=command_id,
        title=title,
        description=description,
        include_shortcut=include_shortcut,
    )


@dataclass(frozen=True)
class ShortcutButtonCommand:
    """
    A single command definition that can be bound to both a shortcut and a button.

    This is intentionally Qt-light: creating the actual `DatalensButton` is optional
    and happens via `create_button(...)` (which imports PySide6 at runtime).
    """

    command_id: ShortcutCommandId
    title: str
    button_text: str | None = None
    description: str | None = None
    default_chord: ShortcutChord | None = None
    scope: ShortcutScope = ShortcutScope.WORKSPACE
    allow_in_text_inputs: bool = False
    consume_event: bool = True

    def to_shortcut_spec(self) -> ShortcutCommandSpec:
        return ShortcutCommandSpec(
            command_id=self.command_id,
            title=self.title,
            description=self.description,
            default_chord=self.default_chord,
            scope=self.scope,
            allow_in_text_inputs=self.allow_in_text_inputs,
            consume_event=self.consume_event,
        )


@dataclass(frozen=True)
class ShortcutButtonBinding:
    """Pair a `ShortcutButtonCommand` with the callback that implements it."""

    command: ShortcutButtonCommand
    callback: Callable[[], None]

    def create_button(
        self,
        *,
        theme,
        parent,
        plugin_id: PluginId,
        variant=None,
        outlined: bool = False,
        attach_shortcut_tooltip: bool = True,
        tooltip_title: str | None = None,
        tooltip_description: str | None = None,
    ):
        """
        Create a `DatalensButton` wired to this binding.

        Note: This imports UI modules (PySide6) at call time; call it on the Qt UI thread.
        """

        from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton

        resolved_variant = variant if variant is not None else ButtonVariant.SECONDARY
        text = self.command.button_text or self.command.title
        btn = DatalensButton(text, theme, resolved_variant, parent, outlined=outlined)
        btn.clicked.connect(lambda *_: self.callback())

        if attach_shortcut_tooltip:
            btn.attach_shortcut_tooltip(
                plugin_id=plugin_id,
                command_id=str(self.command.command_id),
                title=tooltip_title or self.command.title,
                description=tooltip_description or self.command.description,
            )
        return btn

    def create_action(
        self,
        *,
        parent,
        plugin_id: PluginId,
        text: str | None = None,
        attach_shortcut_tooltip: bool = True,
        tooltip_title: str | None = None,
        tooltip_description: str | None = None,
    ):
        """
        Create a `QAction` wired to this binding.

        This is intended for menus/toolbars. It intentionally does *not* set
        `QAction.setShortcut(...)` so the managed shortcuts system remains the
        single source of truth (prevents double-fire).
        """

        from PySide6.QtGui import QAction

        action = QAction(text or self.command.title, parent)
        action.triggered.connect(lambda *_: self.callback())  # type: ignore[arg-type]

        if attach_shortcut_tooltip:
            _attach_shortcut_tooltip(
                target=action,
                plugin_id=plugin_id,
                command_id=str(self.command.command_id),
                title=tooltip_title or self.command.title,
                description=tooltip_description or self.command.description,
            )
        return action


@dataclass(frozen=True)
class TwoStateOption:
    """Qt-free option definition for 2-state toggles (matches `ToggleOption`)."""

    id: str
    label: str


@dataclass(frozen=True)
class ShortcutCheckBoxCommand:
    """
    Command metadata for a boolean toggle presented as a checkbox in the UI.

    The keyboard shortcut for this command should toggle the underlying state.
    """

    command_id: ShortcutCommandId
    title: str
    checkbox_text: str | None = None
    description: str | None = None
    default_chord: ShortcutChord | None = None
    scope: ShortcutScope = ShortcutScope.WORKSPACE
    allow_in_text_inputs: bool = False
    consume_event: bool = True

    def to_shortcut_spec(self) -> ShortcutCommandSpec:
        return ShortcutCommandSpec(
            command_id=self.command_id,
            title=self.title,
            description=self.description,
            default_chord=self.default_chord,
            scope=self.scope,
            allow_in_text_inputs=self.allow_in_text_inputs,
            consume_event=self.consume_event,
        )


@dataclass(frozen=True)
class ShortcutCheckBoxBinding:
    """
    Bind a boolean state to both:
    - a managed shortcut command (toggle)
    - a `DatalensCheckBox` in the UI

    This does not invent a state store. Callers provide the state accessors and
    an optional subscription hook to refresh the widget when state changes from
    other triggers (e.g. keyboard shortcut vs. mouse click).
    """

    command: ShortcutCheckBoxCommand
    get_checked: Callable[[], bool]
    set_checked: Callable[[bool], None]
    subscribe_changed: Callable[[Callable[[], None]], Callable[[], None]] | None = None

    def toggle(self) -> None:
        self.set_checked(not bool(self.get_checked()))

    def create_checkbox(
        self,
        *,
        theme,
        parent,
        plugin_id: PluginId,
        attach_shortcut_tooltip: bool = True,
        tooltip_title: str | None = None,
        tooltip_description: str | None = None,
    ):
        """
        Create a `DatalensCheckBox` wired to this binding.

        This should be called on the Qt UI thread.
        """

        from datalens.ui.widgets.core.checkboxes import DatalensCheckBox

        text = self.command.checkbox_text or self.command.title
        cb = DatalensCheckBox(text, theme, parent)
        cb.setChecked(bool(self.get_checked()))
        cb.toggled.connect(lambda checked: self.set_checked(bool(checked)))  # type: ignore[arg-type]

        if attach_shortcut_tooltip:
            _attach_shortcut_tooltip(
                target=cb,
                plugin_id=plugin_id,
                command_id=str(self.command.command_id),
                title=tooltip_title or self.command.title,
                description=tooltip_description or self.command.description,
            )

        unsub: Callable[[], None] | None = None
        if self.subscribe_changed is not None:
            def refresh() -> None:
                try:
                    desired = bool(self.get_checked())
                    if cb.isChecked() == desired:
                        return
                    cb.blockSignals(True)
                    cb.setChecked(desired)
                except Exception:
                    log.debug("Failed to refresh checkbox state", exc_info=True)
                finally:
                    try:
                        cb.blockSignals(False)
                    except Exception:
                        pass

            try:
                unsub = self.subscribe_changed(refresh)
            except Exception:
                log.debug("Failed to subscribe checkbox state refresh", exc_info=True)
                unsub = None

            if unsub is not None:
                try:
                    cb.destroyed.connect(lambda *_: unsub())  # type: ignore[arg-type]
                except Exception:
                    log.debug("Failed to attach checkbox destroyed cleanup", exc_info=True)

        return cb


@dataclass(frozen=True)
class ShortcutTwoStateToggleCommand:
    """
    Command metadata for a 2-state selection toggle presented as a segmented control.

    The keyboard shortcut for this command should flip between the two options.
    """

    command_id: ShortcutCommandId
    title: str
    left: TwoStateOption
    right: TwoStateOption
    description: str | None = None
    default_chord: ShortcutChord | None = None
    scope: ShortcutScope = ShortcutScope.WORKSPACE
    allow_in_text_inputs: bool = False
    consume_event: bool = True

    def to_shortcut_spec(self) -> ShortcutCommandSpec:
        return ShortcutCommandSpec(
            command_id=self.command_id,
            title=self.title,
            description=self.description,
            default_chord=self.default_chord,
            scope=self.scope,
            allow_in_text_inputs=self.allow_in_text_inputs,
            consume_event=self.consume_event,
        )


@dataclass(frozen=True)
class ShortcutTwoStateToggleBinding:
    """
    Bind a 2-state selection to both:
    - a managed shortcut command (flip left/right)
    - a `Toggle` segmented UI control
    """

    command: ShortcutTwoStateToggleCommand
    get_current_id: Callable[[], str]
    set_current_id: Callable[[str], None]
    subscribe_changed: Callable[[Callable[[], None]], Callable[[], None]] | None = None

    def toggle(self) -> None:
        current = str(self.get_current_id() or "")
        if current == self.command.left.id:
            self.set_current_id(self.command.right.id)
            return
        self.set_current_id(self.command.left.id)

    def create_toggle(
        self,
        *,
        theme,
        parent,
        plugin_id: PluginId,
        attach_shortcut_tooltip: bool = True,
        tooltip_title: str | None = None,
        tooltip_description: str | None = None,
    ):
        """
        Create a `Toggle` (2-state segmented control) wired to this binding.

        This should be called on the Qt UI thread.
        """

        from datalens.ui.widgets.core.toggle import Toggle, ToggleOption

        widget = Toggle(
            theme,
            ToggleOption(self.command.left.id, self.command.left.label),
            ToggleOption(self.command.right.id, self.command.right.label),
            parent=parent,
        )

        def on_user_selection(selected_id: str) -> None:
            try:
                selected_id = str(selected_id)
                # Avoid feedback loops when programmatic updates trigger signals.
                if selected_id == str(self.get_current_id() or ""):
                    return
                self.set_current_id(selected_id)
            except Exception:
                log.debug("Failed to apply toggle selection", exc_info=True)

        widget.selectionChanged.connect(on_user_selection)  # type: ignore[arg-type]

        # Initialize from current state
        try:
            current = str(self.get_current_id() or "")
            if current in {self.command.left.id, self.command.right.id} and widget.current_id != current:
                widget.set_current_id(current, emit=False)
        except Exception:
            log.debug("Failed to initialize toggle selection", exc_info=True)

        if attach_shortcut_tooltip:
            _attach_shortcut_tooltip(
                target=widget,
                plugin_id=plugin_id,
                command_id=str(self.command.command_id),
                title=tooltip_title or self.command.title,
                description=tooltip_description or self.command.description,
            )

        if self.subscribe_changed is not None:
            def refresh() -> None:
                try:
                    desired = str(self.get_current_id() or "")
                    if desired not in {self.command.left.id, self.command.right.id}:
                        return
                    if widget.current_id == desired:
                        return
                    widget.set_current_id(desired, emit=False)
                except Exception:
                    log.debug("Failed to refresh toggle selection", exc_info=True)

            try:
                unsub = self.subscribe_changed(refresh)
            except Exception:
                log.debug("Failed to subscribe toggle selection refresh", exc_info=True)
                unsub = None

            if unsub is not None:
                try:
                    widget.destroyed.connect(lambda *_: unsub())  # type: ignore[arg-type]
                except Exception:
                    log.debug("Failed to attach toggle destroyed cleanup", exc_info=True)

        return widget


def register_shortcut_page_for_buttons(
    ctx: PluginAppContext,
    *,
    page_id: str,
    page_title: str,
    section_id: str,
    section_title: str,
    bindings: Iterable[ShortcutButtonBinding],
    section_description: str | None = None,
    plugin_id: PluginId | None = None,
    plugin_name: str | None = None,
) -> None:
    """
    Convenience wrapper around `ctx.app.shortcuts.register_page(...)`.

    This keeps the shortcuts page definition and the button callbacks in sync.
    """

    items = tuple(bindings)
    page = ShortcutPageSpec(
        page_id=str(page_id),
        title=str(page_title),
        sections=(
            ShortcutSectionSpec(
                section_id=str(section_id),
                title=str(section_title),
                description=section_description,
                commands=tuple(item.command.to_shortcut_spec() for item in items),
            ),
        ),
    )

    callbacks: Mapping[str, Callable[[], None]] = {str(item.command.command_id): item.callback for item in items}
    ctx.app.shortcuts.register_page(
        plugin_id=plugin_id or ctx.plugin.id,
        plugin_name=plugin_name or ctx.plugin.name,
        page=page,
        callbacks=callbacks,
    )


__all__ = [
    "ShortcutButtonBinding",
    "ShortcutButtonCommand",
    "ShortcutCheckBoxBinding",
    "ShortcutCheckBoxCommand",
    "ShortcutTwoStateToggleBinding",
    "ShortcutTwoStateToggleCommand",
    "TwoStateOption",
    "register_shortcut_page_for_buttons",
]
