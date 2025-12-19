from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from datalens.core.context import get_app_context
from datalens.domain.plugin import PluginId
from datalens.ui.theme.app_theme import AppTheme


def build_project_close_policy_section(parent: QWidget, *, theme: AppTheme) -> QWidget:
    """
    Widget Test section: simulate project close/flush failure modes.

    This configures widget_test's `on_project_closing` hook via the in-memory
    PluginStateRegistry so you can validate:
    - safe close success (optional delay)
    - hook failure (raises)
    - timeout behavior (hang)

    Use File -> Close Project or switch projects to trigger the close pipeline.
    """
    box = QWidget(parent)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    title = QLabel("Project Close Policy (simulation)", box)
    title.setStyleSheet("font-size: 13px; font-weight: 700;")
    layout.addWidget(title)

    hint = QLabel(
        "Configure the Widget Test plugin's on_project_closing hook. Then close/switch a project to see the app's "
        "warn/retry/force-close UX.",
        box,
    )
    hint.setWordWrap(True)
    hint.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 12px;")
    layout.addWidget(hint)

    enabled = QCheckBox("Enable simulation", box)
    layout.addWidget(enabled)

    row = QWidget(box)
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(8)

    mode = QComboBox(row)
    mode.addItem("Delay (success)", "delay")
    mode.addItem("Fail (raise)", "fail")
    mode.addItem("Hang (timeout)", "hang")
    row_layout.addWidget(QLabel("Mode:", row))
    row_layout.addWidget(mode, 1)

    delay = QDoubleSpinBox(row)
    delay.setDecimals(1)
    delay.setRange(0.0, 120.0)
    delay.setSingleStep(0.5)
    delay.setSuffix(" s")
    delay.setValue(2.0)
    row_layout.addWidget(QLabel("Delay:", row))
    row_layout.addWidget(delay, 0)

    layout.addWidget(row)

    phases = QWidget(box)
    phases_layout = QHBoxLayout(phases)
    phases_layout.setContentsMargins(0, 0, 0, 0)
    phases_layout.setSpacing(8)

    db_mode = QComboBox(phases)
    db_mode.addItem("DB flush: normal", "off")
    db_mode.addItem("DB flush: fail", "fail")
    db_mode.addItem("DB flush: timeout", "timeout")
    phases_layout.addWidget(db_mode, 1)

    io_mode = QComboBox(phases)
    io_mode.addItem("IO flush: normal", "off")
    io_mode.addItem("IO flush: fail", "fail")
    io_mode.addItem("IO flush: timeout", "timeout")
    phases_layout.addWidget(io_mode, 1)

    layout.addWidget(phases)

    def write_state() -> None:
        app_ctx = get_app_context()
        st = app_ctx.plugin_state.handle_for(PluginId("widget_test"))
        st.set("test.project_close.enabled", bool(enabled.isChecked()))
        st.set("test.project_close.mode", str(mode.currentData()))
        st.set("test.project_close.delay_seconds", float(delay.value()))
        st.set("test.project_close.db_mode", str(db_mode.currentData()))
        st.set("test.project_close.io_mode", str(io_mode.currentData()))

    def refresh_enabled_state() -> None:
        row.setEnabled(bool(enabled.isChecked()))
        phases.setEnabled(bool(enabled.isChecked()))

    enabled.toggled.connect(lambda *_: (refresh_enabled_state(), write_state()))
    mode.currentIndexChanged.connect(lambda *_: write_state())
    delay.valueChanged.connect(lambda *_: write_state())
    db_mode.currentIndexChanged.connect(lambda *_: write_state())
    io_mode.currentIndexChanged.connect(lambda *_: write_state())

    # Default to disabled so normal closes aren't affected unless you opt in.
    enabled.setChecked(False)
    refresh_enabled_state()
    try:
        write_state()
    except Exception:
        pass

    return box


__all__ = ["build_project_close_policy_section"]
