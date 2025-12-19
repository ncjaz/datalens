from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGridLayout, QLabel, QLineEdit, QPlainTextEdit, QWidget

from datalens.core.context import get_app_context
from datalens.domain.plugin import PluginId
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton

from .common import make_section_box


def build_sharing_section(parent: QWidget, *, theme: AppTheme) -> QWidget:
    box = make_section_box(parent, "Sharing (Capabilities + Commands)")
    layout = QGridLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setHorizontalSpacing(10)
    layout.setVerticalSpacing(8)

    intro = QLabel(
        "This section demos plugin-to-plugin integration without imports:\n"
        "- Capabilities: lookup a provider object by id\n"
        "- Commands: request/response via a background threadpool (Future result)",
        box,
    )
    intro.setWordWrap(True)
    intro.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
    layout.addWidget(intro, 0, 0, 1, 4)

    output = QPlainTextEdit(box)
    output.setReadOnly(True)
    output.setMinimumHeight(120)
    layout.addWidget(output, 1, 0, 1, 4)

    def write(line: str) -> None:
        output.appendPlainText(line.rstrip())

    def show_capabilities() -> None:
        app_ctx = get_app_context()
        snap = app_ctx.capabilities.snapshot()
        write("Capabilities snapshot:")
        for cid, providers in sorted(snap.items(), key=lambda kv: kv[0]):
            write(f"- {cid}: {providers}")

    def show_commands() -> None:
        app_ctx = get_app_context()
        snap = app_ctx.commands.snapshot()
        write("Commands snapshot:")
        for item in snap:
            write(f"- {item}")

    def get_counter_via_capability() -> None:
        app_ctx = get_app_context()
        provider = app_ctx.capabilities.get("widget_test.counter")
        if provider is None:
            write("No provider for capability widget_test.counter")
            return
        try:
            value = provider.get()
        except Exception as exc:
            write(f"Capability call failed: {exc!r}")
            return
        write(f"Capability widget_test.counter.get() -> {value}")

    inc_label = QLabel("Increment amount:", box)
    layout.addWidget(inc_label, 2, 0)
    inc_edit = QLineEdit(box)
    inc_edit.setPlaceholderText("e.g. 1")
    inc_edit.setText("1")
    layout.addWidget(inc_edit, 2, 1)

    def dispatch_increment() -> None:
        app_ctx = get_app_context()
        try:
            amount = int(inc_edit.text().strip() or "1")
        except Exception:
            amount = 1
        fut = app_ctx.commands.dispatch(
            "widget_test.counter.increment",
            amount,
            caller_plugin_id=PluginId("widget_test"),
        )

        def done() -> None:
            try:
                result = fut.result()
            except Exception as exc:
                write(f"Command failed: {exc!r}")
                return
            write(f"Command widget_test.counter.increment({amount}) -> {result}")

        fut.add_done_callback(lambda *_: QTimer.singleShot(0, done))

    def dispatch_echo() -> None:
        app_ctx = get_app_context()
        fut = app_ctx.commands.dispatch(
            "widget_test.echo",
            {"hello": "world"},
            caller_plugin_id=PluginId("widget_test"),
        )

        def done() -> None:
            try:
                result = fut.result()
            except Exception as exc:
                write(f"Command failed: {exc!r}")
                return
            write(f"Command widget_test.echo(...) -> {result}")

        fut.add_done_callback(lambda *_: QTimer.singleShot(0, done))

    btn_caps = DatalensButton("Show capabilities", theme, ButtonVariant.SECONDARY, box)
    btn_caps.clicked.connect(lambda *_: show_capabilities())
    layout.addWidget(btn_caps, 3, 0)

    btn_cmds = DatalensButton("Show commands", theme, ButtonVariant.SECONDARY, box)
    btn_cmds.clicked.connect(lambda *_: show_commands())
    layout.addWidget(btn_cmds, 3, 1)

    btn_cap_get = DatalensButton("Get counter (capability)", theme, ButtonVariant.SECONDARY, box)
    btn_cap_get.clicked.connect(lambda *_: get_counter_via_capability())
    layout.addWidget(btn_cap_get, 3, 2)

    btn_inc = DatalensButton("Increment (command)", theme, ButtonVariant.PRIMARY, box)
    btn_inc.clicked.connect(lambda *_: dispatch_increment())
    layout.addWidget(btn_inc, 3, 3)

    btn_echo = DatalensButton("Echo (command)", theme, ButtonVariant.SECONDARY, box)
    btn_echo.clicked.connect(lambda *_: dispatch_echo())
    layout.addWidget(btn_echo, 4, 0)

    return box


__all__ = ["build_sharing_section"]
