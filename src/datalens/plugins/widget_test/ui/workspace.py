from __future__ import annotations

import time

from PySide6.QtCore import Qt, QSize, QThread
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from datalens.core.logging import bind_log_context, current_log_context, get_logger
from datalens.infra.background.loader_context import LoaderContext
from datalens.infra.background.loader_runner import LoaderStage, run_with_loader, run_with_loader_sequence
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton
from datalens.ui.widgets.core.checkboxes import DatalensCheckBox
from datalens.ui.widgets.core.toggle import Toggle, ToggleOption
from datalens.ui.widgets.icons.animated.autodiscovery import AutoDiscoveryAnimator
from datalens.ui.widgets.icons.annotation_toggle_icon import annotation_toggle_icon
from datalens.ui.widgets.icons.autodiscovery_icon import autodiscovery_icon
from datalens.ui.widgets.icons.chevron_icon import chevron_icon
from datalens.ui.widgets.icons.eye_icon import eye_icon
from datalens.ui.widgets.icons.lock_icon import lock_icon
from datalens.ui.widgets.icons.settings_icon import settings_icon
from datalens.plugins.widget_test.ui.file_watcher_panel import FileWatcherPanel


class WorkspaceWidget(QWidget):
    """Widget gallery: preview core themed widgets."""

    def __init__(self, *, theme: AppTheme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._icon_animators: list[AutoDiscoveryAnimator] = []
        self._log = get_logger("datalens.plugins.widget_test.ui")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("Widget Gallery", self)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        root.addWidget(title)

        subtitle = QLabel(
            "Preview of core widgets. This workspace is intentionally small so we can add more sections later.",
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

        content_layout.addWidget(self._buttons_section(), 0)
        content_layout.addWidget(self._toggles_section(), 0)
        content_layout.addWidget(self._checkboxes_section(), 0)
        content_layout.addWidget(self._icons_section(), 0)
        content_layout.addWidget(self._loader_test_section(), 0)
        content_layout.addWidget(FileWatcherPanel(theme=self._theme, parent=content), 0)
        content_layout.addStretch(1)

    def _section_box(self, title: str) -> QGroupBox:
        box = QGroupBox(title, self)
        box.setStyleSheet("QGroupBox { font-weight: 700; }")
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        return box

    def _buttons_section(self) -> QWidget:
        box = self._section_box("Buttons")
        layout = QGridLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)

        variants: list[tuple[str, ButtonVariant]] = [
            ("Primary", ButtonVariant.PRIMARY),
            ("Secondary", ButtonVariant.SECONDARY),
            ("Tertiary", ButtonVariant.TERTIARY),
            ("Confirm", ButtonVariant.CONFIRM),
            ("Cancel", ButtonVariant.CANCEL),
            ("Warning", ButtonVariant.WARNING),
        ]

        for row, (label, variant) in enumerate(variants):
            layout.addWidget(QLabel(label, box), row, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
            btn = DatalensButton(label, self._theme, variant, box)
            layout.addWidget(btn, row, 1)
            disabled = DatalensButton("Disabled", self._theme, variant, box)
            disabled.setEnabled(False)
            layout.addWidget(disabled, row, 2)

        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        return box

    def _toggles_section(self) -> QWidget:
        box = self._section_box("Toggles")
        layout = QGridLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)

        toggle1 = Toggle(self._theme, ToggleOption("global", "Global"), ToggleOption("project", "Project"), box)
        toggle2 = Toggle(self._theme, ToggleOption("off", "Off"), ToggleOption("on", "On"), box)
        toggle3 = Toggle(self._theme, ToggleOption("a", "Option A"), ToggleOption("b", "Option B"), box)
        toggle3.setEnabled(False)

        layout.addWidget(QLabel("Global/Project", box), 0, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(toggle1, 0, 1)
        layout.addWidget(QLabel("Off/On", box), 1, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(toggle2, 1, 1)
        layout.addWidget(QLabel("Disabled", box), 2, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(toggle3, 2, 1)
        layout.setColumnStretch(1, 1)
        return box

    def _checkboxes_section(self) -> QWidget:
        box = self._section_box("Checkboxes")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        cb1 = DatalensCheckBox("Enable autosave", self._theme, box)
        cb2 = DatalensCheckBox("Show overlays", self._theme, box)
        cb2.setChecked(True)
        cb3 = DatalensCheckBox("Disabled option", self._theme, box)
        cb3.setEnabled(False)

        layout.addWidget(cb1)
        layout.addWidget(cb2)
        layout.addWidget(cb3)
        return box

    def _icons_section(self) -> QWidget:
        box = self._section_box("Icons / Glyphs")
        layout = QGridLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(12)

        icons: list[tuple[str, object]] = [
            ("Settings (themed)", settings_icon(self._theme, size=24)),
            ("AutoDiscovery (V1)", autodiscovery_icon(self._theme, size=24)),
            ("AutoDiscovery (Animated)", autodiscovery_icon(self._theme, size=24)),
            ("Chevron Up (V1)", chevron_icon(self._theme, direction="up", size=24)),
            ("Chevron Down (V1)", chevron_icon(self._theme, direction="down", size=24)),
            ("Chevron Left (V1)", chevron_icon(self._theme, direction="left", size=24)),
            ("Chevron Right (V1)", chevron_icon(self._theme, direction="right", size=24)),
            ("Jump Start (V1)", chevron_icon(self._theme, direction="left", size=24, bar="start")),
            ("Jump End (V1)", chevron_icon(self._theme, direction="right", size=24, bar="end")),
            ("Eye Open (V1)", eye_icon(self._theme, size=24, open=True)),
            ("Eye Closed (V1)", eye_icon(self._theme, size=24, open=False)),
            ("Lock Open (V1)", lock_icon(self._theme, size=24, open=True)),
            ("Lock Locked (V1)", lock_icon(self._theme, size=24, open=False)),
            ("Annotations Off (V1)", annotation_toggle_icon(self._theme, active=False, enabled=True, size=48)),
            ("Annotations On (V1)", annotation_toggle_icon(self._theme, active=True, enabled=True, size=48)),
        ]

        def add_cell(row: int, col: int, title: str, icon_obj) -> None:
            cell = QWidget(box)
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(4)

            btn = QToolButton(cell)
            btn.setIcon(icon_obj)
            btn.setIconSize(QSize(24, 24))
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            btn.setAutoRaise(True)
            btn.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            btn.setFocusPolicy(Qt.NoFocus)
            cell_layout.addWidget(btn, alignment=Qt.AlignHCenter)

            label = QLabel(title, cell)
            label.setAlignment(Qt.AlignHCenter)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.75)}; font-size: 11px;")
            cell_layout.addWidget(label)

            layout.addWidget(cell, row, col)

        cols = 4
        for i, (name, icon_obj) in enumerate(icons):
            add_cell(i // cols, i % cols, name, icon_obj)
            if name == "AutoDiscovery (Animated)":
                cell = layout.itemAtPosition(i // cols, i % cols).widget()
                if cell is not None:
                    button = cell.findChild(QToolButton)
                    if button is not None:
                        animator = AutoDiscoveryAnimator(self._theme, size=24, parent=cell)
                        animator.start(button)
                        self._icon_animators.append(animator)

        for c in range(cols):
            layout.setColumnStretch(c, 1)
        return box

    def _loader_test_section(self) -> QWidget:
        box = self._section_box("Loader (Test)")
        layout = QGridLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)

        info = QLabel(
            "These buttons run background tasks via the loader runner to exercise progress, cancellation, sequencing, and error UX.",
            box,
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.75)}; font-size: 11px;")
        layout.addWidget(info, 0, 0, 1, 2)

        run_basic = DatalensButton("Run: Count to 10", self._theme, ButtonVariant.PRIMARY, box)
        run_cancel = DatalensButton("Run: Count to 10 (Cancelable)", self._theme, ButtonVariant.SECONDARY, box)
        run_sequence = DatalensButton("Run: 3-stage Sequence", self._theme, ButtonVariant.SECONDARY, box)
        run_error = DatalensButton("Run: Intentional Error", self._theme, ButtonVariant.CANCEL, box)
        run_cancel_fast = DatalensButton("Run: Cancel (Fast)", self._theme, ButtonVariant.SECONDARY, box)
        run_cancel_slow = DatalensButton("Run: Cancel (Slow)", self._theme, ButtonVariant.SECONDARY, box)
        run_spam_unthrottled = DatalensButton("Run: Log spam (Unthrottled)", self._theme, ButtonVariant.WARNING, box)
        run_spam_throttled = DatalensButton("Run: Log spam (Throttled)", self._theme, ButtonVariant.SECONDARY, box)
        run_flush_ok = DatalensButton("Run: Flush sim (OK)", self._theme, ButtonVariant.CONFIRM, box)
        run_flush_timeout = DatalensButton("Run: Flush sim (Timeout)", self._theme, ButtonVariant.WARNING, box)
        run_ui_safety = DatalensButton("Run: UI thread safety (Error)", self._theme, ButtonVariant.CANCEL, box)
        run_ctx_prop = DatalensButton("Run: Log context propagation", self._theme, ButtonVariant.SECONDARY, box)
        run_settings_spam = DatalensButton("Run: Settings spam (Debounced)", self._theme, ButtonVariant.SECONDARY, box)

        def _count_task(ctx: LoaderContext, *, cancelable: bool) -> int:
            for i in range(1, 11):
                if cancelable:
                    ctx.raise_if_cancelled()
                ctx.log(f"Count {i}/10")
                ctx.set_progress(i / 10.0)
                time.sleep(0.35)
            return 10

        def _run_count(cancelable: bool) -> None:
            def task(ctx: LoaderContext) -> int:
                return _count_task(ctx, cancelable=cancelable)

            def on_done(_: object) -> None:
                QMessageBox.information(self, "Loader Test", "Completed.")

            def on_cancelled() -> None:
                QMessageBox.information(self, "Loader Test", "Cancelled.")

            run_with_loader(
                parent=self,
                title="Counting…",
                task=task,
                on_result=on_done,
                on_error=lambda exc: QMessageBox.critical(self, "Loader Test", str(exc)),
                on_cancelled=on_cancelled if cancelable else None,
                dialog_options={
                    "spinner_size": 80,
                    "title_point_size": 18,
                    "subtitle_point_size": 12,
                    "max_messages": 6,
                    "cancelable": bool(cancelable),
                    "log_context": {
                        "plugin_id": "widget_test",
                        "operation": "loader_test",
                        "phase": "count_to_10",
                    },
                },
            )

        def _run_sequence() -> None:
            def stage1(ctx: LoaderContext) -> object:
                ctx.log("Stage 1: quick step")
                time.sleep(0.5)
                return "stage1"

            def stage2(ctx: LoaderContext) -> object:
                ctx.log("Stage 2: counting")
                for i in range(1, 6):
                    ctx.raise_if_cancelled()
                    ctx.log(f"Count {i}/5")
                    ctx.set_progress(i / 5.0)
                    time.sleep(0.25)
                return "stage2"

            def stage3(ctx: LoaderContext) -> object:
                ctx.log("Stage 3: finalize")
                time.sleep(0.6)
                return "stage3"

            run_with_loader_sequence(
                parent=self,
                title="Sequence…",
                stages=(
                    LoaderStage("Stage 1: quick step", stage1, weight=0.2),
                    LoaderStage("Stage 2: counting", stage2, weight=0.6),
                    LoaderStage("Stage 3: finalize", stage3, weight=0.2),
                ),
                on_result=lambda _: QMessageBox.information(self, "Loader Test", "Sequence completed."),
                on_error=lambda exc: QMessageBox.critical(self, "Loader Test", str(exc)),
                on_cancelled=lambda: QMessageBox.information(self, "Loader Test", "Sequence cancelled."),
                dialog_options={
                    "spinner_size": 80,
                    "title_point_size": 18,
                    "subtitle_point_size": 12,
                    "max_messages": 6,
                    "cancelable": True,
                    "log_context": {
                        "plugin_id": "widget_test",
                        "operation": "loader_test",
                        "phase": "sequence",
                    },
                },
            )

        def _run_error() -> None:
            def task(ctx: LoaderContext) -> object:
                ctx.log("Preparing…")
                time.sleep(0.4)
                ctx.log("About to raise an error (intentional).")
                time.sleep(0.2)
                raise RuntimeError("Intentional loader test error.")

            run_with_loader(
                parent=self,
                title="Error Test…",
                task=task,
                on_result=lambda _: QMessageBox.information(self, "Loader Test", "Unexpected success."),
                on_error=lambda exc: QMessageBox.critical(self, "Loader Test", str(exc)),
                dialog_options={
                    "spinner_size": 80,
                    "title_point_size": 18,
                    "subtitle_point_size": 12,
                    "max_messages": 6,
                    "log_context": {
                        "plugin_id": "widget_test",
                        "operation": "loader_test",
                        "phase": "intentional_error",
                    },
                },
            )

        def _run_cancel_responsiveness(*, slow: bool) -> None:
            def task(ctx: LoaderContext) -> object:
                total = 120
                check_every = 15 if slow else 1
                ctx.log(f"Running {'slow' if slow else 'fast'} cancel loop…")
                for i in range(1, total + 1):
                    if i % check_every == 0:
                        ctx.raise_if_cancelled()
                    if i % 10 == 0:
                        ctx.log(f"Step {i}/{total}")
                    ctx.set_progress(i / total)
                    time.sleep(0.05)
                return None

            run_with_loader(
                parent=self,
                title="Cancel Test…",
                task=task,
                on_result=lambda _: QMessageBox.information(self, "Loader Test", "Completed."),
                on_error=lambda exc: QMessageBox.critical(self, "Loader Test", str(exc)),
                on_cancelled=lambda: QMessageBox.information(self, "Loader Test", "Cancelled."),
                dialog_options={
                    "spinner_size": 80,
                    "title_point_size": 18,
                    "subtitle_point_size": 12,
                    "max_messages": 6,
                    "cancelable": True,
                    "log_context": {
                        "plugin_id": "widget_test",
                        "operation": "loader_test",
                        "phase": "cancel_slow" if slow else "cancel_fast",
                    },
                },
            )

        def _run_log_spam(*, throttled: bool) -> None:
            total = 2000
            every = 50 if throttled else 1

            def task(ctx: LoaderContext) -> dict[str, object]:
                start = time.perf_counter()
                ctx.log(f"Spam test starting ({total} messages, every={every}).")
                for i in range(1, total + 1):
                    ctx.raise_if_cancelled()
                    if i % every == 0 or i == 1 or i == total:
                        ctx.log(f"spam: {i}/{total}")
                    ctx.set_progress(i / total)
                elapsed = time.perf_counter() - start
                ctx.log(f"Spam test finished in {elapsed:0.2f}s.")
                return {"total": total, "every": every, "elapsed_s": elapsed}

            def on_done(result: object) -> None:
                stats = result if isinstance(result, dict) else {}
                QMessageBox.information(
                    self,
                    "Loader Test",
                    f"Spam task finished.\n\nattempted={stats.get('total')}\n"
                    f"logged_every={stats.get('every')}\nelapsed={stats.get('elapsed_s'):0.2f}s",
                )

            run_with_loader(
                parent=self,
                title="Log spam…",
                task=task,
                on_result=on_done,
                on_error=lambda exc: QMessageBox.critical(self, "Loader Test", str(exc)),
                on_cancelled=lambda: QMessageBox.information(self, "Loader Test", "Cancelled."),
                dialog_options={
                    "spinner_size": 80,
                    "title_point_size": 18,
                    "subtitle_point_size": 12,
                    "max_messages": 6,
                    "cancelable": True,
                    "log_context": {
                        "plugin_id": "widget_test",
                        "operation": "loader_test",
                        "phase": "log_spam_throttled" if throttled else "log_spam_unthrottled",
                    },
                },
            )

        def _run_flush_simulation(*, timeout: bool) -> None:
            duration_s = 4.0
            timeout_s = 1.5 if timeout else 10.0

            def task(ctx: LoaderContext) -> object:
                ctx.log("Flushing…")
                start = time.monotonic()
                while True:
                    ctx.raise_if_cancelled()
                    elapsed = time.monotonic() - start
                    ctx.set_progress(min(1.0, elapsed / duration_s))
                    ctx.log(f"Flush progress: {elapsed:0.1f}s/{duration_s:0.1f}s")
                    if elapsed >= duration_s:
                        break
                    if elapsed >= timeout_s:
                        raise TimeoutError(f"Flush timed out after {timeout_s:0.1f}s")
                    time.sleep(0.25)
                return None

            def on_error(exc: Exception) -> None:
                retry = QMessageBox.StandardButton.Retry
                cancel = QMessageBox.StandardButton.Cancel
                force_btn = QMessageBox.StandardButton.Ignore
                box_msg = QMessageBox(self)
                box_msg.setWindowTitle("Flush simulation")
                box_msg.setText(str(exc))
                box_msg.setInformativeText("Retry will run the flush again. Force will skip remaining work (simulated).")
                box_msg.setIcon(QMessageBox.Warning)
                box_msg.setStandardButtons(retry | cancel | force_btn)
                box_msg.button(force_btn).setText("Force Close")
                clicked = box_msg.exec()
                if clicked == retry:
                    _run_flush_simulation(timeout=False)
                    return
                if clicked == force_btn:
                    # Simulate a "force close": best-effort finalization without waiting.
                    def force_task(ctx: LoaderContext) -> object:
                        ctx.log("Force close (simulated)…")
                        ctx.set_progress(1.0)
                        return None

                    run_with_loader(
                        parent=self,
                        title="Force closing…",
                        task=force_task,
                        on_result=lambda _: QMessageBox.information(self, "Flush simulation", "Force close completed."),
                        on_error=lambda e: QMessageBox.critical(self, "Flush simulation", str(e)),
                        dialog_options={
                            "spinner_size": 80,
                            "title_point_size": 18,
                            "subtitle_point_size": 12,
                            "max_messages": 6,
                            "log_context": {"plugin_id": "widget_test", "operation": "flush_sim", "phase": "force"},
                        },
                    )
                    return
                return

            run_with_loader(
                parent=self,
                title="Flush simulation…",
                task=task,
                on_result=lambda _: QMessageBox.information(self, "Flush simulation", "Flush completed."),
                on_error=on_error,
                on_cancelled=lambda: QMessageBox.information(self, "Flush simulation", "Cancelled."),
                dialog_options={
                    "spinner_size": 80,
                    "title_point_size": 18,
                    "subtitle_point_size": 12,
                    "max_messages": 6,
                    "cancelable": True,
                    "log_context": {
                        "plugin_id": "widget_test",
                        "operation": "flush_sim",
                        "phase": "timeout" if timeout else "ok",
                    },
                },
            )

        def _run_ui_thread_safety_error() -> None:
            ui_obj = self

            def task(_: LoaderContext) -> object:
                # Simulate a forbidden UI touch: detect thread-affinity violation and raise.
                try:
                    from PySide6.QtWidgets import QApplication

                    app = QApplication.instance()
                    ui_thread = app.thread() if app is not None else None
                except Exception:
                    ui_thread = None
                try:
                    current = QThread.currentThread()
                except Exception:
                    current = None

                if ui_thread is not None and current is not None and current != ui_thread:
                    raise RuntimeError(
                        f"UI thread affinity violation: tried to access {type(ui_obj).__name__} from a worker thread."
                    )
                return None

            run_with_loader(
                parent=self,
                title="UI safety test…",
                task=task,
                on_result=lambda _: QMessageBox.information(self, "UI safety test", "Unexpected success."),
                on_error=lambda exc: QMessageBox.information(self, "UI safety test", f"Caught as expected:\n\n{exc}"),
                dialog_options={
                    "spinner_size": 80,
                    "title_point_size": 18,
                    "subtitle_point_size": 12,
                    "max_messages": 4,
                    "log_context": {"plugin_id": "widget_test", "operation": "ui_safety", "phase": "violation"},
                },
            )

        def _run_log_context_propagation() -> None:
            op_id = "ctxprop"
            with bind_log_context(plugin_id="widget_test", operation="loader_test", op_id=op_id):
                def task(ctx: LoaderContext) -> dict[str, object]:
                    ctx.log("Reading bound log context from worker…")
                    return current_log_context()

                def on_done(result: object) -> None:
                    ctx = result if isinstance(result, dict) else {}
                    QMessageBox.information(
                        self,
                        "Log context propagation",
                        f"Worker saw:\n\nplugin_id={ctx.get('plugin_id')}\noperation={ctx.get('operation')}\nop_id={ctx.get('op_id')}",
                    )

                run_with_loader(
                    parent=self,
                    title="Context propagation…",
                    task=task,
                    on_result=on_done,
                    on_error=lambda exc: QMessageBox.critical(self, "Log context propagation", str(exc)),
                    dialog_options={
                        "spinner_size": 80,
                        "title_point_size": 18,
                        "subtitle_point_size": 12,
                        "max_messages": 6,
                        "log_context": {"plugin_id": "widget_test", "operation": "loader_test", "phase": "ctx_prop"},
                    },
                )

        def _run_settings_spam() -> None:
            writer = default_debounced_settings_writer(debounce_seconds=0.25)
            store = default_settings_store()
            path = str(store.path)

            def task(ctx: LoaderContext) -> object:
                ctx.log(f"Settings path: {path}")
                ctx.log("Queuing 250 debounced updates…")
                for i in range(1, 251):
                    ctx.raise_if_cancelled()

                    def mutator(current: AppSettings) -> AppSettings:
                        ps = dict(current.plugin_settings or {})
                        widget = dict(ps.get("widget_test", {}) or {})
                        widget["settings_spam_counter"] = i
                        ps["widget_test"] = widget
                        return replace(current, plugin_settings=ps)

                    writer.request_update(mutator)
                    if i % 25 == 0:
                        ctx.log(f"Queued {i}/250")
                    ctx.set_progress(i / 250.0)
                    time.sleep(0.01)

                ctx.log("Flushing writer…")
                writer.flush()
                ctx.log("Done.")
                return None

            run_with_loader(
                parent=self,
                title="Settings spam…",
                task=task,
                on_result=lambda _: QMessageBox.information(self, "Settings spam", f"Completed.\n\n{path}"),
                on_error=lambda exc: QMessageBox.critical(self, "Settings spam", str(exc)),
                on_cancelled=lambda: QMessageBox.information(self, "Settings spam", "Cancelled."),
                dialog_options={
                    "spinner_size": 80,
                    "title_point_size": 18,
                    "subtitle_point_size": 12,
                    "max_messages": 6,
                    "cancelable": True,
                    "log_context": {"plugin_id": "widget_test", "operation": "settings_spam", "phase": "debounced"},
                },
            )

        run_basic.clicked.connect(lambda *_: _run_count(cancelable=False))
        run_cancel.clicked.connect(lambda *_: _run_count(cancelable=True))
        run_sequence.clicked.connect(lambda *_: _run_sequence())
        run_error.clicked.connect(lambda *_: _run_error())
        run_cancel_fast.clicked.connect(lambda *_: _run_cancel_responsiveness(slow=False))
        run_cancel_slow.clicked.connect(lambda *_: _run_cancel_responsiveness(slow=True))
        run_spam_unthrottled.clicked.connect(lambda *_: _run_log_spam(throttled=False))
        run_spam_throttled.clicked.connect(lambda *_: _run_log_spam(throttled=True))
        run_flush_ok.clicked.connect(lambda *_: _run_flush_simulation(timeout=False))
        run_flush_timeout.clicked.connect(lambda *_: _run_flush_simulation(timeout=True))
        run_ui_safety.clicked.connect(lambda *_: _run_ui_thread_safety_error())
        run_ctx_prop.clicked.connect(lambda *_: _run_log_context_propagation())
        run_settings_spam.clicked.connect(lambda *_: _run_settings_spam())

        layout.addWidget(run_basic, 1, 0)
        layout.addWidget(run_cancel, 1, 1)
        layout.addWidget(run_sequence, 2, 0)
        layout.addWidget(run_error, 2, 1)
        layout.addWidget(run_cancel_fast, 3, 0)
        layout.addWidget(run_cancel_slow, 3, 1)
        layout.addWidget(run_spam_unthrottled, 4, 0)
        layout.addWidget(run_spam_throttled, 4, 1)
        layout.addWidget(run_flush_ok, 5, 0)
        layout.addWidget(run_flush_timeout, 5, 1)
        layout.addWidget(run_ui_safety, 6, 0)
        layout.addWidget(run_ctx_prop, 6, 1)
        layout.addWidget(run_settings_spam, 7, 0, 1, 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        return box
from datalens.services.settings_store import default_debounced_settings_writer, default_settings_store
from datalens.domain.system.settings import AppSettings
from dataclasses import replace
