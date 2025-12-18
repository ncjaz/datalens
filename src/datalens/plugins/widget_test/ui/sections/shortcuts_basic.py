from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from datalens.domain.plugin import PluginId
from datalens.ui.shortcuts.helpers import enable_mouse_wheel_chords
from datalens.ui.shortcuts.hold_toggle import attach_hold_toggle_shortcut
from datalens.ui.theme.app_theme import AppTheme

from .common import make_section_box


def build_shortcuts_section(
    parent: QWidget,
    *,
    theme: AppTheme,
    shortcut_labels: dict[str, QLabel],
    hold_toggle_hint_labels: dict[str, QLabel],
    on_update_shortcut_labels: Callable[[], None],
    on_update_hold_toggle_hints: Callable[[], None],
) -> QWidget:
    box = make_section_box(parent, "Shortcuts (Test)")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)

    info = QLabel(
        "This section exists to validate shortcut dispatch scenarios:\n"
        "- keyboard chords (incl. multi-modifier)\n"
        "- allow/deny while typing in text inputs\n"
        "- mouse + wheel chords (opt-in subtree)\n"
        "- consume_event behavior\n\n"
        "Use Preferences -> Keyboard Shortcuts to change bindings.",
        box,
    )
    info.setWordWrap(True)
    info.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
    layout.addWidget(info)

    grid = QGridLayout()
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(6)

    def add_row(row: int, title: str, command_id: str, hint: str) -> None:
        title_lbl = QLabel(title, box)
        title_lbl.setStyleSheet("font-weight: 700;")
        grid.addWidget(title_lbl, row, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        chord_lbl = QLabel("—", box)
        chord_lbl.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.85)};")
        grid.addWidget(chord_lbl, row, 1, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        shortcut_labels[command_id] = chord_lbl

        hint_lbl = QLabel(hint, box)
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.65)}; font-size: 11px;")
        grid.addWidget(hint_lbl, row, 2)

    add_row(0, "Run loader: count to 10", "run_count_10", "Opens a loader dialog and counts (mixes ctx.log + log.progress).")
    add_row(1, "Blocked in text inputs", "blocked_in_text", "Should not fire while the text field below is focused.")
    add_row(2, "Allowed in text inputs", "allowed_in_text", "Should fire even while the text field below is focused.")
    add_row(3, "Multi-modifier chord", "multi_modifier", "Tests Ctrl+Alt+Shift keyboard chords.")
    add_row(
        4,
        "Hold/Toggle demo",
        "hold_toggle_demo",
        "Widget-handled stateful shortcut. Click the demo box below to focus it, then press the chord. Configure Hold vs Toggle in Preferences.",
    )
    add_row(5, "Mouse chord demo", "mouse_demo", "Works only inside the opt-in mouse test box below.")
    add_row(6, "Wheel chord demo", "wheel_demo", "Works only inside the opt-in mouse test box below.")
    add_row(7, "Consume-event click", "consume_click", "Ctrl+LeftClick inside the mouse test box should NOT increment click count.")

    grid.setColumnStretch(2, 1)
    layout.addLayout(grid)

    on_update_shortcut_labels()

    typing_row = QWidget(box)
    typing_layout = QHBoxLayout(typing_row)
    typing_layout.setContentsMargins(0, 0, 0, 0)
    typing_layout.setSpacing(8)
    typing_layout.addWidget(QLabel("Text input:", box), 0)
    edit = QLineEdit(typing_row)
    edit.setPlaceholderText("Click here and type. Shortcuts that disallow text inputs should not fire.")
    typing_layout.addWidget(edit, 1)
    layout.addWidget(typing_row)

    class _HoldToggleDemo(QFrame):
        def __init__(self, theme_: AppTheme, parent_: QWidget) -> None:
            super().__init__(parent_)
            self._theme = theme_
            self._active = False
            self.setFrameShape(QFrame.StyledPanel)
            self.setObjectName("WidgetTest:HoldToggleDemo")
            self.setFocusPolicy(Qt.StrongFocus)
            self.setMinimumHeight(56)
            inner = QVBoxLayout(self)
            inner.setContentsMargins(10, 8, 10, 8)
            inner.setSpacing(4)
            self._title = QLabel("Hold/Toggle demo box (click to focus)", self)
            self._title.setStyleSheet(f"color: {theme_.with_alpha_hex(theme_.text_color, 0.85)}; font-weight: 700;")
            inner.addWidget(self._title)
            self._status = QLabel("Status: inactive", self)
            self._status.setStyleSheet(f"color: {theme_.with_alpha_hex(theme_.text_color, 0.75)};")
            inner.addWidget(self._status)

        def set_active(self, active: bool) -> None:
            self._active = bool(active)
            if self._active:
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

    demo = _HoldToggleDemo(theme, box)
    hint = QLabel(box)
    hint.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.65)}; font-size: 11px;")
    hint.setWordWrap(True)
    hint.setText(
        "Instructions:\n"
        "1) Click this demo box to focus it.\n"
        "2) Press the shortcut to activate.\n"
        "3) Click into the text field above and type: the shortcut should NOT trigger while typing."
    )
    layout.addWidget(hint)
    hold_toggle_hint_labels["hold_toggle_demo"] = hint
    on_update_hold_toggle_hints()

    attach_hold_toggle_shortcut(
        demo,
        plugin_id=PluginId("widget_test"),
        command_id="hold_toggle_demo",
        on_active_changed=demo.set_active,
        allow_in_text_inputs=False,
        consume_event=True,
    )
    layout.addWidget(demo)

    mouse_box = QFrame(box)
    mouse_box.setFrameShape(QFrame.StyledPanel)
    mouse_box.setObjectName("WidgetTest:MouseChordBox")
    enable_mouse_wheel_chords(mouse_box)

    mouse_layout = QVBoxLayout(mouse_box)
    mouse_layout.setContentsMargins(10, 10, 10, 10)
    mouse_layout.setSpacing(6)

    mouse_info = QLabel(
        "Mouse chord test area (opt-in):\n"
        "- Alt+RightClick (mouse_demo)\n"
        "- Ctrl+WheelUp (wheel_demo)\n"
        "- Ctrl+LeftClick (consume_click) should be consumed",
        mouse_box,
    )
    mouse_info.setWordWrap(True)
    mouse_info.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
    mouse_layout.addWidget(mouse_info)

    class _ClickCounter(QFrame):
        def __init__(self, theme_: AppTheme, parent_: QWidget) -> None:
            super().__init__(parent_)
            self._theme = theme_
            self._count = 0
            self.setFrameShape(QFrame.StyledPanel)
            self.setMinimumHeight(48)
            inner = QHBoxLayout(self)
            inner.setContentsMargins(10, 8, 10, 8)
            inner.setSpacing(10)
            self._label = QLabel("Click count: 0", self)
            self._label.setStyleSheet(f"color: {theme_.with_alpha_hex(theme_.text_color, 0.9)}; font-weight: 700;")
            inner.addWidget(self._label, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)
            inner.addStretch(1)

        def mousePressEvent(self, event) -> None:  # type: ignore[override]
            self._count += 1
            self._label.setText(f"Click count: {self._count}")
            try:
                event.accept()
            except Exception:
                pass
            super().mousePressEvent(event)

    counter = _ClickCounter(theme, mouse_box)
    mouse_layout.addWidget(counter)
    layout.addWidget(mouse_box)
    return box


__all__ = ["build_shortcuts_section"]
