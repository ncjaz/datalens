from __future__ import annotations

import os
import time
from dataclasses import replace

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QGridLayout, QLabel, QMessageBox, QWidget

from datalens.domain.plugin import PluginId
from datalens.core.logging import bind_log_context, current_log_context
from datalens.domain.system.settings import AppSettings
from datalens.infra.background.loader_context import LoaderContext
from datalens.infra.background.loader_runner import LoaderStage, run_with_loader, run_with_loader_sequence
from datalens.services.settings_store import default_debounced_settings_writer, default_settings_store
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton
from datalens.api.ui_commands import ShortcutButtonBinding

from .common import make_section_box


def build_loader_test_section(
    parent: QWidget,
    *,
    theme: AppTheme,
    log,
    run_count_10_binding: ShortcutButtonBinding | None = None,
) -> QWidget:
    in_automated_tests = bool(os.environ.get("PYTEST_CURRENT_TEST")) or os.environ.get("DATALENS_TESTING") == "1"

    box = make_section_box(parent, "Loader (Test)")
    layout = QGridLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setHorizontalSpacing(10)
    layout.setVerticalSpacing(10)

    info = QLabel(
        "These buttons run background tasks via the loader runner to exercise progress, cancellation, sequencing, and error UX.\n"
        "Note: log.progress(...) lines can be mirrored into the loader dialog (Preferences -> User Interface -> Loader).",
        box,
    )
    info.setWordWrap(True)
    info.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
    layout.addWidget(info, 0, 0, 1, 2)

    if run_count_10_binding is not None:
        run_basic = run_count_10_binding.create_button(
            theme=theme,
            parent=box,
            plugin_id=PluginId("widget_test"),
            variant=ButtonVariant.PRIMARY,
        )
    else:
        run_basic = DatalensButton("Run: Count to 10", theme, ButtonVariant.PRIMARY, box)
    run_cancel = DatalensButton("Run: Count to 10 (Cancelable)", theme, ButtonVariant.SECONDARY, box)
    run_sequence = DatalensButton("Run: 3-stage Sequence", theme, ButtonVariant.SECONDARY, box)
    run_error = DatalensButton("Run: Intentional Error", theme, ButtonVariant.CANCEL, box)
    run_cancel_fast = DatalensButton("Run: Cancel (Fast)", theme, ButtonVariant.SECONDARY, box)
    run_cancel_slow = DatalensButton("Run: Cancel (Slow)", theme, ButtonVariant.SECONDARY, box)
    run_spam_unthrottled = DatalensButton("Run: Log spam (Unthrottled)", theme, ButtonVariant.WARNING, box)
    run_spam_throttled = DatalensButton("Run: Log spam (Throttled)", theme, ButtonVariant.SECONDARY, box)
    run_flush_ok = DatalensButton("Run: Flush sim (OK)", theme, ButtonVariant.CONFIRM, box)
    run_flush_timeout = DatalensButton("Run: Flush sim (Timeout)", theme, ButtonVariant.WARNING, box)
    run_ui_safety = DatalensButton("Run: UI thread safety (Error)", theme, ButtonVariant.CANCEL, box)
    run_ctx_prop = DatalensButton("Run: Log context propagation", theme, ButtonVariant.SECONDARY, box)
    run_settings_spam = DatalensButton("Run: Settings spam (Debounced)", theme, ButtonVariant.SECONDARY, box)
    run_log_progress = DatalensButton("Run: log.progress (Count)", theme, ButtonVariant.PRIMARY, box)
    run_log_mirroring = DatalensButton("Run: log->loader mirroring (Demo)", theme, ButtonVariant.SECONDARY, box)

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
            QMessageBox.information(parent, "Loader Test", "Completed.")

        def on_cancelled() -> None:
            QMessageBox.information(parent, "Loader Test", "Cancelled.")

        run_with_loader(
            parent=parent,
            title="Counting...",
            task=task,
            on_result=on_done,
            on_error=lambda exc: QMessageBox.critical(parent, "Loader Test", str(exc)),
            on_cancelled=on_cancelled if cancelable else None,
            dialog_options={
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
            parent=parent,
            title="Sequence...",
            stages=(
                LoaderStage("Stage 1: quick step", stage1, weight=0.2),
                LoaderStage("Stage 2: counting", stage2, weight=0.6),
                LoaderStage("Stage 3: finalize", stage3, weight=0.2),
            ),
            on_result=lambda _: QMessageBox.information(parent, "Loader Test", "Sequence completed."),
            on_error=lambda exc: QMessageBox.critical(parent, "Loader Test", str(exc)),
            on_cancelled=lambda: QMessageBox.information(parent, "Loader Test", "Sequence cancelled."),
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
            ctx.log("Preparing...")
            time.sleep(0.4)
            ctx.log("About to raise an error (intentional).")
            time.sleep(0.2)
            if in_automated_tests:
                ctx.log("Suppressed intentional error during automated tests.")
                ctx.set_progress(1.0)
                return {"suppressed": True, "reason": "automated_tests"}
            raise RuntimeError("Intentional loader test error.")

        def on_done(result: object) -> None:
            if isinstance(result, dict) and result.get("suppressed"):
                QMessageBox.information(parent, "Loader Test", "Intentional error suppressed during automated tests.")
                return
            QMessageBox.information(parent, "Loader Test", "Unexpected success.")

        run_with_loader(
            parent=parent,
            title="Error Test...",
            task=task,
            on_result=on_done,
            on_error=lambda exc: QMessageBox.critical(parent, "Loader Test", str(exc)),
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
            ctx.log(f"Running {'slow' if slow else 'fast'} cancel loop...")
            for i in range(1, total + 1):
                if i % check_every == 0:
                    ctx.raise_if_cancelled()
                if i % 10 == 0:
                    ctx.log(f"Step {i}/{total}")
                ctx.set_progress(i / total)
                time.sleep(0.05)
            return None

        run_with_loader(
            parent=parent,
            title="Cancel Test...",
            task=task,
            on_result=lambda _: QMessageBox.information(parent, "Loader Test", "Completed."),
            on_error=lambda exc: QMessageBox.critical(parent, "Loader Test", str(exc)),
            on_cancelled=lambda: QMessageBox.information(parent, "Loader Test", "Cancelled."),
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
                parent,
                "Loader Test",
                f"Spam task finished.\n\nattempted={stats.get('total')}\n"
                f"logged_every={stats.get('every')}\nelapsed={stats.get('elapsed_s'):0.2f}s",
            )

        run_with_loader(
            parent=parent,
            title="Log spam...",
            task=task,
            on_result=on_done,
            on_error=lambda exc: QMessageBox.critical(parent, "Loader Test", str(exc)),
            on_cancelled=lambda: QMessageBox.information(parent, "Loader Test", "Cancelled."),
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
            ctx.log("Flushing...")
            start = time.monotonic()
            while True:
                ctx.raise_if_cancelled()
                elapsed = time.monotonic() - start
                ctx.set_progress(min(1.0, elapsed / duration_s))
                ctx.log(f"Flush progress: {elapsed:0.1f}s/{duration_s:0.1f}s")
                if elapsed >= duration_s:
                    break
                if elapsed >= timeout_s:
                    if in_automated_tests:
                        ctx.log(f"Flush timed out after {timeout_s:0.1f}s (suppressed in automated tests).")
                        ctx.set_progress(1.0)
                        return {"timed_out": True, "timeout_s": float(timeout_s)}
                    raise TimeoutError(f"Flush timed out after {timeout_s:0.1f}s")
                time.sleep(0.25)
            return None

        def on_done(result: object) -> None:
            if isinstance(result, dict) and result.get("timed_out"):
                QMessageBox.information(
                    parent,
                    "Flush simulation",
                    f"Timed out (simulated).\n\ntimeout_s={float(result.get('timeout_s') or 0):0.1f}s",
                )
                return
            QMessageBox.information(parent, "Flush simulation", "Flush completed.")

        def on_error(exc: Exception) -> None:
            retry = QMessageBox.StandardButton.Retry
            cancel = QMessageBox.StandardButton.Cancel
            force_btn = QMessageBox.StandardButton.Ignore
            box_msg = QMessageBox(parent)
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
                    ctx.log("Force close (simulated)...")
                    ctx.set_progress(1.0)
                    return None

                run_with_loader(
                    parent=parent,
                    title="Force closing...",
                    task=force_task,
                    on_result=lambda _: QMessageBox.information(parent, "Flush simulation", "Force close completed."),
                    on_error=lambda e: QMessageBox.critical(parent, "Flush simulation", str(e)),
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
            parent=parent,
            title="Flush simulation...",
            task=task,
            on_result=on_done,
            on_error=on_error,
            on_cancelled=lambda: QMessageBox.information(parent, "Flush simulation", "Cancelled."),
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
        ui_obj = parent

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
                if in_automated_tests:
                    return {"violation": True, "suppressed": True, "target": type(ui_obj).__name__}
                raise RuntimeError(
                    f"UI thread affinity violation: tried to access {type(ui_obj).__name__} from a worker thread."
                )
            return {"violation": False, "suppressed": False, "target": type(ui_obj).__name__}

        def on_done(result: object) -> None:
            payload = result if isinstance(result, dict) else {}
            if payload.get("violation"):
                QMessageBox.information(
                    parent,
                    "UI safety test",
                    f"Violation detected (suppressed in automated tests).\n\ntarget={payload.get('target')}",
                )
                return
            QMessageBox.information(parent, "UI safety test", "No violation detected.")

        run_with_loader(
            parent=parent,
            title="UI safety test...",
            task=task,
            on_result=on_done,
            on_error=lambda exc: QMessageBox.information(parent, "UI safety test", f"Caught as expected:\n\n{exc}"),
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
                ctx.log("Reading bound log context from worker...")
                return current_log_context()

            def on_done(result: object) -> None:
                ctx_ = result if isinstance(result, dict) else {}
                QMessageBox.information(
                    parent,
                    "Log context propagation",
                    f"Worker saw:\n\nplugin_id={ctx_.get('plugin_id')}\noperation={ctx_.get('operation')}\nop_id={ctx_.get('op_id')}",
                )

            run_with_loader(
                parent=parent,
                title="Context propagation...",
                task=task,
                on_result=on_done,
                on_error=lambda exc: QMessageBox.critical(parent, "Log context propagation", str(exc)),
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
            ctx.log("Queuing 250 debounced updates...")
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

            ctx.log("Flushing writer...")
            writer.flush()
            ctx.log("Done.")
            return None

        run_with_loader(
            parent=parent,
            title="Settings spam...",
            task=task,
            on_result=lambda _: QMessageBox.information(parent, "Settings spam", f"Completed.\n\n{path}"),
            on_error=lambda exc: QMessageBox.critical(parent, "Settings spam", str(exc)),
            on_cancelled=lambda: QMessageBox.information(parent, "Settings spam", "Cancelled."),
            dialog_options={
                "spinner_size": 80,
                "title_point_size": 18,
                "subtitle_point_size": 12,
                "max_messages": 6,
                "cancelable": True,
                "log_context": {"plugin_id": "widget_test", "operation": "settings_spam", "phase": "debounced"},
            },
        )

    def _run_log_progress_count() -> None:
        def task(ctx: LoaderContext) -> object:
            for i in range(1, 11):
                ctx.raise_if_cancelled()
                log.progress(f"log.progress count {i}/10", value=i / 10.0)
                time.sleep(0.25)
            log.progress("Done.", value=1.0)
            return None

        run_with_loader(
            parent=parent,
            title="log.progress count...",
            task=task,
            on_result=lambda _: QMessageBox.information(parent, "Loader Test", "Completed."),
            on_error=lambda exc: QMessageBox.critical(parent, "Loader Test", str(exc)),
            on_cancelled=lambda: QMessageBox.information(parent, "Loader Test", "Cancelled."),
            dialog_options={
                "spinner_size": 80,
                "title_point_size": 18,
                "subtitle_point_size": 12,
                "max_messages": 6,
                "cancelable": True,
                "log_context": {"plugin_id": "widget_test", "operation": "loader_test", "phase": "log_progress"},
            },
        )

    def _run_log_mirroring_demo() -> None:
        def task(ctx: LoaderContext) -> object:
            ctx.log("ctx: Starting mixed ctx + log demo.")
            log.progress("log.progress: This progress line should appear in the loader dialog.")
            log.info("INFO (hidden by default; enable in Preferences -> Loader).")
            log.warning("WARNING (hidden by default; enable in Preferences -> Loader).")
            log.info("INFO with progress=True (should appear).", extra={"progress": True})
            log.warning("WARNING with progress=True (should appear).", extra={"progress": True})

            for i in range(1, 6):
                ctx.raise_if_cancelled()
                ctx.log(f"ctx: Step {i}/5")
                log.progress(f"log.progress: Step {i}/5 (text only)")
                ctx.set_progress(i / 5.0)
                time.sleep(0.25)

            ctx.log("ctx: Done.")
            return None

        run_with_loader(
            parent=parent,
            title="Log mirroring demo...",
            task=task,
            on_result=lambda _: QMessageBox.information(parent, "Loader Test", "Completed."),
            on_error=lambda exc: QMessageBox.critical(parent, "Loader Test", str(exc)),
            dialog_options={
                "spinner_size": 80,
                "title_point_size": 18,
                "subtitle_point_size": 12,
                "max_messages": 6,
                "log_context": {"plugin_id": "widget_test", "operation": "loader_test", "phase": "mirror_demo"},
            },
        )

    if run_count_10_binding is None:
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
    run_log_progress.clicked.connect(lambda *_: _run_log_progress_count())
    run_log_mirroring.clicked.connect(lambda *_: _run_log_mirroring_demo())

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
    layout.addWidget(run_log_progress, 8, 0)
    layout.addWidget(run_log_mirroring, 8, 1)
    layout.setColumnStretch(0, 1)
    layout.setColumnStretch(1, 1)
    return box


__all__ = ["build_loader_test_section"]
