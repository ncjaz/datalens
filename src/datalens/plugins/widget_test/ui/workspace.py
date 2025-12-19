from __future__ import annotations

import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from datalens.core.context import get_app_context
from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.plugins.widget_test.ui.file_watcher_panel import FileWatcherPanel
from datalens.plugins.widget_test.ui.gesture_panel import GesturePanel
from datalens.ui.shortcuts.helpers import attach_shortcut_integration
from datalens.ui.shortcuts.tooltips import tooltip_with_shortcut
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.buttons import DatalensButton
from datalens.ui.widgets.icons.animated.autodiscovery import AutoDiscoveryAnimator

from .sections import (
    build_buttons_section,
    build_checkboxes_section,
    build_icons_section,
    build_loader_test_section,
    build_project_close_policy_section,
    build_sharing_section,
    build_shortcuts_advanced_section,
    build_shortcuts_section,
    build_toggles_section,
)


class WorkspaceWidget(QWidget):
    """Developer harness: preview core widgets and systems."""

    def __init__(self, *, theme: AppTheme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._icon_animators: list[AutoDiscoveryAnimator] = []
        self._log = get_logger("datalens.plugins.widget_test.ui")
        self._tooltip_unsub: object | None = None
        self._shortcut_labels: dict[str, QLabel] = {}
        self._hold_toggle_hint_labels: dict[str, QLabel] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("Widget Gallery", self)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        root.addWidget(title)

        subtitle = QLabel(
            "Preview of core widgets/systems. This workspace is intentionally small so we can add more sections later.",
            self,
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 12px;")
        root.addWidget(subtitle)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll, 1)

        content = QWidget(scroll)
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        def add_section(title_: str, factory) -> None:
            try:
                widget = factory()
            except Exception as exc:
                self._log.error(
                    "Widget test section failed",
                    exc_info=True,
                    extra={
                        "plugin_id": "widget_test",
                        "operation": "widget_test",
                        "phase": "section_error",
                        "section": title_,
                    },
                )
                content_layout.addWidget(self._error_section(title_, exc), 0)
                return

            if isinstance(widget, QWidget):
                content_layout.addWidget(widget, 0)
            else:
                content_layout.addWidget(
                    self._error_section(title_, TypeError(f"Factory returned {type(widget)!r}")),
                    0,
                )

        add_section("Buttons", self._buttons_section)
        add_section("Toggles", self._toggles_section)
        add_section("Checkboxes", self._checkboxes_section)
        add_section("Icons", self._icons_section)
        add_section("Shortcuts", self._shortcuts_section)
        add_section("Shortcuts Advanced", self._shortcuts_advanced_section)
        add_section("Loader", self._loader_test_section)
        add_section("Sharing", self._sharing_section)
        add_section("Project Close Policy", self._project_close_policy_section)
        add_section("Gesture Router", self._gesture_section)
        add_section("File Watcher", lambda: FileWatcherPanel(theme=self._theme, parent=content))
        content_layout.addStretch(1)

        # Keep the tooltip demo in sync with user overrides while this workspace is alive.
        try:
            self._tooltip_unsub = attach_shortcut_integration(
                self,
                on_shortcuts_changed=self._refresh_tooltip_demo,
            )
        except Exception:
            self._tooltip_unsub = None

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._unsubscribe_tooltip_refresh()
        for animator in self._icon_animators:
            try:
                animator.stop()
            except Exception:
                continue
        super().closeEvent(event)

    def _error_section(self, title: str, exc: BaseException) -> QGroupBox:
        box = self._section_box(f"{title} (failed)")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        msg = QLabel(
            "This widget-test section failed to build.\n"
            "This should not block the rest of the workspace.\n\n"
            f"{type(exc).__name__}: {exc}",
            box,
        )
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {self._theme.accent_cancel}; font-size: 11px;")
        layout.addWidget(msg)

        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        tb = QLabel("".join(tb_lines).strip(), box)
        tb.setWordWrap(True)
        tb.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.7)}; font-size: 10px;")
        layout.addWidget(tb)
        return box

    def _unsubscribe_tooltip_refresh(self) -> None:
        unsub = self._tooltip_unsub
        self._tooltip_unsub = None
        if callable(unsub):
            try:
                unsub()
            except Exception:
                pass

    def _section_box(self, title: str) -> QGroupBox:
        box = QGroupBox(title, self)
        box.setStyleSheet("QGroupBox { font-weight: 700; }")
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        return box

    def _buttons_section(self) -> QWidget:
        return build_buttons_section(
            self,
            theme=self._theme,
            on_refresh_tooltip_demo=self._refresh_tooltip_demo,
            on_log_clicked=lambda: self._log.info("Clicked tooltip demo button"),
        )

    def _sharing_section(self) -> QWidget:
        return build_sharing_section(self, theme=self._theme)

    def _refresh_tooltip_demo(self, button: DatalensButton | None = None) -> None:
        try:
            btn = button
            if btn is None:
                btn = self.findChild(DatalensButton, "WidgetTest:ShortcutTooltipDemo")
            if btn is None:
                return
            app_ctx = get_app_context()
            chord = app_ctx.shortcuts.get_effective_command_chord(
                plugin_id=PluginId("widget_test"),
                command_id="log_hello",
            )
            hold_chord = app_ctx.shortcuts.get_effective_command_chord(
                plugin_id=PluginId("widget_test"),
                command_id="hold_toggle_demo",
            )
            mode = app_ctx.shortcuts.get_effective_command_mode_toggle(
                plugin_id=PluginId("widget_test"),
                command_id="hold_toggle_demo",
            )
            mode_label = None
            if mode is not None:
                mode_label = "Toggle" if bool(mode) else "Hold"

            tooltip = tooltip_with_shortcut(
                title="Shortcut tooltip demo",
                description="Live-updates when Preferences overrides change.",
                shortcut=chord,
            )
            extra_lines: list[str] = []
            if hold_chord or mode_label:
                extra_lines.append("")
                extra_lines.append("Hold/Toggle demo:")
                if hold_chord:
                    extra_lines.append(f"- Chord: {hold_chord}")
                if mode_label:
                    extra_lines.append(f"- Mode: {mode_label}")
            btn.setToolTip((tooltip + "\n" + "\n".join(extra_lines)).strip() if extra_lines else tooltip)

            self._update_shortcut_labels()
            self._update_hold_toggle_hints()
        except Exception:
            pass

    def _update_shortcut_labels(self) -> None:
        if not self._shortcut_labels:
            return
        app_ctx = get_app_context()
        for command_id, label in self._shortcut_labels.items():
            try:
                chord = app_ctx.shortcuts.get_effective_command_chord(
                    plugin_id=PluginId("widget_test"),
                    command_id=command_id,
                )
                label.setText(chord or "Unbound")
            except Exception:
                continue

    def _update_hold_toggle_hints(self) -> None:
        if not self._hold_toggle_hint_labels:
            return
        app_ctx = get_app_context()
        for command_id, label in self._hold_toggle_hint_labels.items():
            try:
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
                parts: list[str] = []
                parts.append(f"Shortcut: {chord or 'Unbound'}")
                if mode_label is not None:
                    parts.append(f"Mode: {mode_label}")
                label.setText(" | ".join(parts))
            except Exception:
                continue

    def _shortcuts_section(self) -> QWidget:
        return build_shortcuts_section(
            self,
            theme=self._theme,
            shortcut_labels=self._shortcut_labels,
            hold_toggle_hint_labels=self._hold_toggle_hint_labels,
            on_update_shortcut_labels=self._update_shortcut_labels,
            on_update_hold_toggle_hints=self._update_hold_toggle_hints,
        )

    def _shortcuts_advanced_section(self) -> QWidget:
        return build_shortcuts_advanced_section(
            self,
            theme=self._theme,
            hold_toggle_hint_labels=self._hold_toggle_hint_labels,
            on_update_hold_toggle_hints=self._update_hold_toggle_hints,
        )

    def _gesture_section(self) -> QWidget:
        box = self._section_box("Gesture Router (press/drag/release)")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(GesturePanel(theme=self._theme, parent=box))
        return box

    def _toggles_section(self) -> QWidget:
        return build_toggles_section(self, theme=self._theme)

    def _checkboxes_section(self) -> QWidget:
        return build_checkboxes_section(self, theme=self._theme)

    def _icons_section(self) -> QWidget:
        return build_icons_section(
            self,
            theme=self._theme,
            animators_out=self._icon_animators,
        )

    def _loader_test_section(self) -> QWidget:
        return build_loader_test_section(
            self,
            theme=self._theme,
            log=self._log,
        )

    def _project_close_policy_section(self) -> QWidget:
        return build_project_close_policy_section(self, theme=self._theme)
