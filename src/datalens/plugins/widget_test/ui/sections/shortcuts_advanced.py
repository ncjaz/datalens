from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from datalens.core.context import get_app_context
from datalens.domain.plugin import PluginId
from datalens.ui.shortcuts.helpers import attach_shortcut_integration
from datalens.ui.shortcuts.hold_toggle import attach_hold_toggle_shortcut
from datalens.ui.shortcuts.chords import event_to_chord, is_text_input_widget
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton

from .common import make_section_box


def build_shortcuts_advanced_section(
    parent: QWidget,
    *,
    theme: AppTheme,
    hold_toggle_hint_labels: dict[str, QLabel],
    on_update_hold_toggle_hints: Callable[[], None],
) -> QWidget:
    box = make_section_box(parent, "Shortcuts Advanced (Test)")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)

    info = QLabel(
        "Advanced integration tests:\n"
        "- Hold/Toggle mode (widget-owned lifecycle)\n"
        "- Focus on child widgets (non-text + text gating)\n"
        "- Popout window routing (focused window only)\n"
        "- Conflict reporting in Preferences",
        box,
    )
    info.setWordWrap(True)
    info.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
    layout.addWidget(info)

    def make_hold_toggle_box(parent_: QWidget, title: str, command_id: str) -> QFrame:
        class _HoldToggleBox(QFrame):
            def __init__(self) -> None:
                super().__init__(parent_)
                self._theme = theme
                self.setFrameShape(QFrame.StyledPanel)
                self.setObjectName(f"WidgetTest:HoldToggle:{command_id}")
                self.setFocusPolicy(Qt.StrongFocus)
                self._unsubscribe_changed: object | None = None
                self._echo_filter: object | None = None

                inner = QVBoxLayout(self)
                inner.setContentsMargins(10, 10, 10, 10)
                inner.setSpacing(6)

                title_lbl = QLabel(title, self)
                title_lbl.setStyleSheet(
                    f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.9)}; font-weight: 700;"
                )
                inner.addWidget(title_lbl)

                self._status = QLabel("Status: inactive", self)
                self._status.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.75)};")
                inner.addWidget(self._status)

                self._binding = QLabel("Binding: (loading…)", self)
                self._binding.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.7)};")
                inner.addWidget(self._binding)

                self._last_seen = QLabel("Last chord seen: —", self)
                self._last_seen.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.6)};")
                inner.addWidget(self._last_seen)

                self._hint = QLabel(self)
                self._hint.setWordWrap(True)
                self._hint.setStyleSheet(
                    f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.65)}; font-size: 11px;"
                )
                inner.addWidget(self._hint)
                hold_toggle_hint_labels[command_id] = self._hint
                on_update_hold_toggle_hints()

                row = QWidget(self)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(8)

                focus_child = QPushButton("Focus demo panel (for shortcut)", row)
                focus_child.setFocusPolicy(Qt.StrongFocus)
                focus_child.setToolTip(
                    "This does not activate anything; it only moves focus back to the demo panel.\n"
                    "If this button has focus, the Hold/Toggle shortcut should still work."
                )
                row_layout.addWidget(focus_child, 0)

                text = QLineEdit(row)
                text.setPlaceholderText(
                    "Text input gating: while typing here, Hold/Toggle should NOT trigger. Click outside to test."
                )
                row_layout.addWidget(text, 1)

                inner.addWidget(row)

                attach_hold_toggle_shortcut(
                    self,
                    plugin_id=PluginId("widget_test"),
                    command_id=command_id,
                    on_active_changed=self.set_active,
                    allow_in_text_inputs=False,
                    consume_event=True,
                )

                self._install_debug_chord_echo()
                self._subscribe_shortcuts_changed()
                self._refresh_binding()

                focus_child.clicked.connect(lambda *_: self.setFocus(Qt.MouseFocusReason))
                self.destroyed.connect(lambda *_: self._cleanup())  # type: ignore[arg-type]

            def set_active(self, active: bool) -> None:
                if active:
                    self._status.setText("Status: ACTIVE")
                    self._status.setStyleSheet(f"color: {self._theme.accent_confirm}; font-weight: 700;")
                else:
                    self._status.setText("Status: inactive")
                    self._status.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.75)};")

            def mousePressEvent(self, event) -> None:  # type: ignore[override]
                try:
                    self.setFocus(Qt.MouseFocusReason)
                except Exception:
                    pass
                super().mousePressEvent(event)

            def _cleanup(self) -> None:
                unsub = self._unsubscribe_changed
                self._unsubscribe_changed = None
                if callable(unsub):
                    try:
                        unsub()
                    except Exception:
                        pass
                f = self._echo_filter
                self._echo_filter = None
                try:
                    from PySide6.QtWidgets import QApplication

                    qapp = QApplication.instance()
                    if qapp is not None and f is not None:
                        qapp.removeEventFilter(f)  # type: ignore[arg-type]
                except Exception:
                    pass

            def _subscribe_shortcuts_changed(self) -> None:
                try:
                    app_ctx = get_app_context()
                    self._unsubscribe_changed = app_ctx.shortcuts.subscribe_changed(self._refresh_binding)
                except Exception:
                    self._unsubscribe_changed = None

            def _refresh_binding(self) -> None:
                try:
                    app_ctx = get_app_context()
                    chord = app_ctx.shortcuts.get_effective_command_chord(
                        plugin_id=PluginId("widget_test"),
                        command_id=command_id,
                    )
                    mode = app_ctx.shortcuts.get_effective_command_mode_toggle(
                        plugin_id=PluginId("widget_test"),
                        command_id=command_id,
                    )
                    mode_label = None
                    if mode is not None:
                        mode_label = "Toggle" if bool(mode) else "Hold"
                    if chord:
                        text = f"Binding: {chord}"
                    else:
                        text = "Binding: Unbound"
                    if mode_label:
                        text += f"  |  Mode: {mode_label}"
                    self._binding.setText(text)
                except Exception:
                    self._binding.setText("Binding: (error; see logs)")

            def _install_debug_chord_echo(self) -> None:
                """
                Best-effort chord echo to make debugging Hold/Toggle bindings obvious.

                This does not consume events; it only shows what `event_to_chord(...)` sees
                while focus is within this demo panel.
                """

                from PySide6.QtCore import QEvent, QObject
                from PySide6.QtGui import QKeyEvent
                from PySide6.QtWidgets import QApplication

                box = self

                class _Echo(QObject):
                    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
                        et = QEvent.Type(event.type())
                        if et != QEvent.Type.KeyPress:
                            return False
                        if not isinstance(event, QKeyEvent):
                            return False
                        if event.isAutoRepeat():
                            return False
                        try:
                            app = QApplication.instance()
                            focus = app.focusWidget() if app is not None else None
                        except Exception:
                            focus = None
                        if focus is None:
                            return False
                        current = focus
                        within = False
                        while current is not None:
                            if current is box:
                                within = True
                                break
                            try:
                                current = current.parentWidget()
                            except Exception:
                                break
                        if not within:
                            return False
                        if is_text_input_widget(focus):
                            box._last_seen.setText("Last chord seen: (typing; gated)")
                            return False
                        chord = event_to_chord(event) or "—"
                        box._last_seen.setText(f"Last chord seen: {chord}")
                        return False

                try:
                    app = QApplication.instance()
                    if app is None:
                        return
                    echo = _Echo(self)
                    self._echo_filter = echo
                    app.installEventFilter(echo)
                except Exception:
                    self._echo_filter = None

        return _HoldToggleBox()

    layout.addWidget(make_hold_toggle_box(box, "Hold/Toggle demo (default Hold)", "hold_toggle_demo"))
    layout.addWidget(make_hold_toggle_box(box, "Hold/Toggle demo (default Toggle)", "hold_toggle_demo_toggle_default"))

    actions = QHBoxLayout()
    actions.setContentsMargins(0, 0, 0, 0)
    actions.setSpacing(8)

    popout_btn = DatalensButton("Open popout window", theme, ButtonVariant.SECONDARY, box)
    popout_btn.setToolTip("Opens a popout dialog to test window-focused routing for Hold/Toggle.")
    actions.addWidget(popout_btn, 0)
    actions.addStretch(1)
    layout.addLayout(actions)

    def open_popout() -> None:
        dlg = QDialog(parent)
        dlg.setWindowTitle("Widget Test: Shortcuts Popout")
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.resize(520, 240)
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        head = QLabel("Popout window (focus routing test)", dlg)
        head.setStyleSheet("font-weight: 700;")
        outer.addWidget(head)

        hint = QLabel(
            "This dialog is a separate top-level window. Hold/Toggle should only react while this window is focused.",
            dlg,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
        outer.addWidget(hint)

        outer.addWidget(make_hold_toggle_box(dlg, "Popout Hold/Toggle demo", "hold_toggle_demo"))

        attach_shortcut_integration(dlg, plugin_id=PluginId("widget_test"), tag_window=True)
        dlg.show()

    popout_btn.clicked.connect(lambda *_: open_popout())

    conflicts = QLabel(
        "Conflict test: commands 'conflict_a' and 'conflict_b' share the same default chord.\n"
        "Open Preferences -> Keyboard Shortcuts to see the conflict warning and how duplicates are rejected.",
        box,
    )
    conflicts.setWordWrap(True)
    conflicts.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
    layout.addWidget(conflicts)

    return box


__all__ = ["build_shortcuts_advanced_section"]
