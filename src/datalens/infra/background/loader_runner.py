"""
Loader Runner
=============

This module provides the high-level convenience API
:func:`run_with_loader`, which is the primary interface used throughout
the application and by plugins to execute long-running operations in a
non-blocking manner.

``run_with_loader``:

- Constructs a loader dialog (spinner + message area)
- Creates and starts a :class:`LoaderWorker`
- Connects worker signals to the dialog
- Handles task completion and failure
- Ensures UI responsiveness

This isolates all threading and synchronization logic from UI components and
plugin authors, who only need to supply a task function and optional callbacks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import inspect
from typing import Any, Callable, Optional
from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtWidgets import QWidget

from datalens.core.logging import get_logger
from datalens.infra.background.loader_context import LoaderCancelled, LoaderContext
from datalens.infra.background.loader_worker import LoaderWorker


@dataclass(frozen=True, slots=True)
class LoaderStage:
    """
    A single stage in a loader sequence.

    `task` runs in a background thread and receives a `LoaderContext`.
    """

    name: str
    task: Callable[[LoaderContext], Any]
    weight: float = 1.0


def _callable_debug_name(func: object) -> str:
    try:
        unwrapped = inspect.unwrap(func)  # type: ignore[arg-type]
    except Exception:
        unwrapped = func
    module = getattr(unwrapped, "__module__", None)
    qualname = getattr(unwrapped, "__qualname__", None) or getattr(unwrapped, "__name__", None)
    if module and qualname:
        return f"{module}.{qualname}"
    if qualname:
        return str(qualname)
    return repr(func)


def _merge_log_extra(base: dict[str, Any], ctx: dict[str, Any] | None) -> dict[str, Any]:
    """
    Merge `ctx` into `base` without overwriting keys already present in `base`.

    This keeps structured loader fields (operation/phase/title/task) stable while
    allowing caller attribution such as `plugin_id` or `op_id`.
    """
    if not ctx:
        return base
    merged = dict(base)
    for k, v in ctx.items():
        if k in merged:
            continue
        merged[k] = v
    return merged


class _ResultRouter(QObject):
    """
    Ensure loader completion handlers run on the UI thread.

    Qt signals emitted from `LoaderWorker` come from a background thread. If we
    connect them directly to a plain Python callable, PySide may invoke the
    callable on the emitter thread, which is unsafe for UI work. By routing via
    a QObject living on the UI thread, AutoConnection becomes a queued
    connection.
    """

    def __init__(
        self,
        *,
        dialog: "QObject",
        cleanup: Callable[[], None],
        dialog_title: str,
        on_result: Callable[[Any], None] | None,
        on_error: Callable[[Exception], None] | None,
        on_cancelled: Callable[[], None] | None,
        keep_open_on_error: bool,
        log_context: dict[str, Any] | None,
    ) -> None:
        super().__init__(dialog)
        self._dialog = dialog
        self._cleanup = cleanup
        self._dialog_title = str(dialog_title)
        self._on_result = on_result
        self._on_error = on_error
        self._on_cancelled = on_cancelled
        self._keep_open_on_error = keep_open_on_error
        self._log_context = log_context or None
        self._log = get_logger("datalens.ui.loader")

    @Slot(str)
    def on_message(self, text: str) -> None:
        message = (text or "").strip()
        if not message:
            return
        try:
            self._log.info(
                message,
                extra=_merge_log_extra(
                    {"operation": "loader_dialog", "phase": "message", "title": self._dialog_title},
                    self._log_context,
                ),
            )
        except Exception:
            pass
        try:
            append = getattr(self._dialog, "append_message", None)
            if callable(append):
                append(message)
        except Exception:
            return

    @Slot(float)
    def on_progress(self, value: float) -> None:
        try:
            set_progress = getattr(self._dialog, "set_progress", None)
            if callable(set_progress):
                set_progress(value)
        except Exception:
            return

    @Slot(object)
    def on_finished(self, result: object) -> None:
        # Close the loader *before* invoking `on_result`. Many callers show a
        # modal dialog (e.g. WelcomeWindow.exec()), which would otherwise block
        # and prevent the loader from closing.
        try:
            try:
                hide = getattr(self._dialog, "hide", None)
                if callable(hide):
                    hide()
            except Exception:
                pass
            self._dialog.close()
        finally:
            self._cleanup()
        try:
            self._log.info(
                "Loader completed",
                extra=_merge_log_extra(
                    {"operation": "loader_dialog", "phase": "completed", "title": self._dialog_title},
                    self._log_context,
                ),
            )
        except Exception:
            pass
        if callable(self._on_result):
            QTimer.singleShot(0, lambda: self._on_result(result))

    @Slot(Exception)
    def on_failed(self, exc: Exception) -> None:
        if self._keep_open_on_error:
            try:
                show_error = getattr(self._dialog, "show_error", None)
                if callable(show_error):
                    show_error(str(exc))
            except Exception:
                pass
        else:
            # Close the loader before invoking `on_error`. Many handlers show a
            # modal dialog (QMessageBox/WelcomeWindow.exec) which would
            # otherwise block and prevent the loader from closing.
            try:
                try:
                    hide = getattr(self._dialog, "hide", None)
                    if callable(hide):
                        hide()
                except Exception:
                    pass
                self._dialog.close()
            finally:
                self._cleanup()

        try:
            self._log.error(
                "Loader failed: %s",
                exc,
                extra=_merge_log_extra(
                    {"operation": "loader_dialog", "phase": "error", "title": self._dialog_title},
                    self._log_context,
                ),
            )
        except Exception:
            pass

        if callable(self._on_error):
            QTimer.singleShot(0, lambda: self._on_error(exc))

    @Slot()
    def on_cancelled(self) -> None:
        try:
            try:
                hide = getattr(self._dialog, "hide", None)
                if callable(hide):
                    hide()
            except Exception:
                pass
            self._dialog.close()
        finally:
            self._cleanup()
        try:
            self._log.info(
                "Loader cancelled",
                extra=_merge_log_extra(
                    {"operation": "loader_dialog", "phase": "cancelled", "title": self._dialog_title},
                    self._log_context,
                ),
            )
        except Exception:
            pass
        if callable(self._on_cancelled):
            QTimer.singleShot(0, lambda: self._on_cancelled())


def run_with_loader(
    parent: QWidget | None,
    title: str,
    task: Callable[[Any], Any],
    on_result: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    on_cancelled: Optional[Callable[[], None]] = None,
    dialog_options: dict[str, Any] | None = None,
) -> None:
    """
    Execute a long-running task in a background thread while displaying a
    loader dialog with real-time status messages.

    Parameters
    ----------
    parent:
        Parent widget for the loader dialog.
    title:
        Title or descriptive text displayed in the loader dialog.
    task:
        A callable of the form ``task(ctx) -> result``. It is executed in a
        dedicated background thread. The task receives a
        :class:`LoaderContext` instance and may call ``ctx.log(...)`` to
        send output to the UI.
    on_result:
        Optional callback invoked with ``result`` when the task completes.
    on_error:
        Optional callback invoked with the raised ``Exception`` if the task
        fails.
    on_cancelled:
        Optional callback invoked if the user requested cancellation and the
        task cooperatively exited (raised ``LoaderCancelled``).

    Notes
    -----
    This function is UI-safe. All UI updates occur on the main thread.

    The loader dialog is imported lazily at runtime in order to avoid
    circular dependencies between UI and infrastructure modules.

    Cancellation
    ------------
    Cancellation is cooperative. To enable it, pass:

    - ``dialog_options={"cancelable": True}``
    - and ensure your task checks ``ctx.is_cancel_requested()`` (or calls
      ``ctx.raise_if_cancelled()``) and then exits.

    Logging attribution
    -------------------
    The loader logs include the callable debug name, but you can attach explicit
    attribution (e.g. plugin id, operation id) by passing:

    - ``dialog_options={"log_context": {...}}``
    """
    # Avoid circular imports until LoaderDialog exists
    from datalens.ui.widgets.dialogs.loader_dialog import LoaderDialog
    from datalens.ui.theme import AppTheme

    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        candidate = getattr(app, "app_theme", None) if app is not None else None
        theme = candidate if isinstance(candidate, AppTheme) else AppTheme()
    except Exception:
        theme = AppTheme()

    keep_open_on_error = False
    cancelable = False
    log_context: dict[str, Any] | None = None
    dialog_kwargs: dict[str, Any] = {"title": title, "parent": parent, "theme": theme}
    if dialog_options:
        keep_open_on_error = bool(dialog_options.get("keep_open_on_error", False))
        cancelable = bool(dialog_options.get("cancelable", False))
        candidate_log_context = dialog_options.get("log_context")
        if isinstance(candidate_log_context, dict):
            log_context = dict(candidate_log_context)
        dialog_kwargs.update(
            {
                k: v
                for k, v in dialog_options.items()
                if k not in ("keep_open_on_error", "cancelable", "log_context")
            }
        )

    dialog = LoaderDialog(**dialog_kwargs)
    worker = LoaderWorker(task)
    worker.capture_context()
    # Keep Python references alive for the lifetime of the dialog.
    # (Especially important when parent is None.)
    dialog._loader_worker = worker  # type: ignore[attr-defined]

    cleaned_up = False

    def _cleanup() -> None:
        nonlocal cleaned_up
        if cleaned_up:
            return
        cleaned_up = True
        try:
            worker.deleteLater()
        except RuntimeError:
            # LoaderWorker may already be deleted (e.g. dialog destroyed first).
            pass
        try:
            dialog._loader_worker = None  # type: ignore[attr-defined]
        except Exception:
            pass
        if parent is None:
            try:
                from PySide6.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None:
                    dialogs = getattr(app, "_datalens_loader_dialogs", None)
                    if isinstance(dialogs, list) and dialog in dialogs:
                        dialogs.remove(dialog)
            except Exception:
                pass

    if parent is None:
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                dialogs = getattr(app, "_datalens_loader_dialogs", None)
                if dialogs is None:
                    dialogs = []
                    setattr(app, "_datalens_loader_dialogs", dialogs)
                dialogs.append(dialog)
        except Exception:
            pass

    # -------------------------------------------------------------- #
    # Worker → Dialog connections
    # -------------------------------------------------------------- #

    # Worker -> dialog updates (via router for logging + ordering).

    # -------------------------------------------------------------- #
    # Success handler
    # -------------------------------------------------------------- #

    dialog.destroyed.connect(lambda *_: _cleanup())

    router = _ResultRouter(
        dialog=dialog,
        cleanup=_cleanup,
        dialog_title=title,
        on_result=on_result,
        on_error=on_error,
        on_cancelled=on_cancelled,
        keep_open_on_error=keep_open_on_error,
        log_context=log_context,
    )
    dialog._loader_router = router  # type: ignore[attr-defined]

    worker.message.connect(router.on_message)
    worker.progress.connect(router.on_progress)
    worker.finished.connect(router.on_finished)
    worker.cancelled.connect(router.on_cancelled)
    worker.failed.connect(router.on_failed)

    # -------------------------------------------------------------- #
    # Begin execution
    # -------------------------------------------------------------- #

    dialog.show()
    try:
        task_name = _callable_debug_name(task)
        get_logger("datalens.ui.loader").info(
            "Loader shown",
            extra=_merge_log_extra(
                {"operation": "loader_dialog", "phase": "show", "title": str(title), "task": task_name},
                log_context,
            ),
        )
        get_logger("datalens.ui.loader").info(
            "Loader task started: %s",
            task_name,
            extra=_merge_log_extra(
                {"operation": "loader_dialog", "phase": "task_start", "title": str(title), "task": task_name},
                log_context,
            ),
        )
    except Exception:
        pass
    if cancelable:
        try:
            set_cancel = getattr(dialog, "set_cancel_callback", None)
            if callable(set_cancel):
                def _cancel() -> None:
                    try:
                        get_logger("datalens.ui.loader").info(
                            "Loader cancel requested",
                            extra=_merge_log_extra(
                                {"operation": "loader_dialog", "phase": "cancel_request", "title": str(title)},
                                log_context,
                            ),
                        )
                    except Exception:
                        pass
                    worker.cancel()

                set_cancel(_cancel)
            get_logger("datalens.ui.loader").info(
                "Loader cancel enabled",
                extra=_merge_log_extra(
                    {"operation": "loader_dialog", "phase": "cancel_enabled", "title": str(title)},
                    log_context,
                ),
            )
        except Exception:
            pass
    # Ensure the dialog has a chance to paint before the background task begins.
    QTimer.singleShot(0, worker.start)


def run_with_loader_sequence(
    parent: QWidget | None,
    *,
    title: str,
    stages: Sequence[LoaderStage],
    on_result: Optional[Callable[[list[object]], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    on_cancelled: Optional[Callable[[], None]] = None,
    dialog_options: dict[str, Any] | None = None,
) -> None:
    """
    Execute multiple loader stages sequentially under a single loader dialog.

    This is useful for startup flows where we would otherwise show multiple
    loader dialogs back-to-back (e.g. enable plugins -> open project).

    `on_result` receives the list of per-stage results (in order).

    Cancellation is cooperative (same as :func:`run_with_loader`). Stage tasks
    receive a LoaderContext that propagates the cancellation token.
    """
    stage_list = list(stages)

    def task(ctx: LoaderContext) -> list[object]:
        if not stage_list:
            return []

        log = get_logger("datalens.ui.loader")
        weights: list[float] = [max(0.0, float(s.weight)) for s in stage_list]
        total = sum(weights) or 1.0
        completed = 0.0
        results: list[object] = []

        for index, (stage, weight) in enumerate(zip(stage_list, weights, strict=False), start=1):
            stage_name = str(stage.name).strip() or "Stage"
            stage_task_name = _callable_debug_name(stage.task)
            try:
                log.info(
                    "Loader stage %d/%d started: %s (%s)",
                    index,
                    len(stage_list),
                    stage_name,
                    stage_task_name,
                    extra={
                        "operation": "loader_dialog",
                        "phase": "stage_start",
                        "title": str(title),
                        "stage": stage_name,
                        "task": stage_task_name,
                        "stage_index": index,
                        "stage_count": len(stage_list),
                    },
                )
            except Exception:
                pass
            ctx.log(stage_name)

            def send_progress(value: float) -> None:
                try:
                    v = float(value)
                except Exception:
                    return
                if v < 0.0:
                    v = 0.0
                if v > 1.0:
                    v = 1.0
                overall = (completed + (weight * v)) / total
                ctx.set_progress(overall)

            stage_ctx = LoaderContext(
                send_message=ctx.log,
                send_progress=send_progress,
                is_cancel_requested=ctx.is_cancel_requested,
            )

            try:
                result = stage.task(stage_ctx)
            except LoaderCancelled:
                raise
            except Exception as exc:
                raise RuntimeError(f"Loader stage failed: {stage_name}") from exc

            results.append(result)
            completed += weight
            ctx.set_progress(completed / total)
            try:
                log.info(
                    "Loader stage %d/%d completed: %s",
                    index,
                    len(stage_list),
                    stage_name,
                    extra={
                        "operation": "loader_dialog",
                        "phase": "stage_completed",
                        "title": str(title),
                        "stage": stage_name,
                        "task": stage_task_name,
                        "stage_index": index,
                        "stage_count": len(stage_list),
                    },
                )
            except Exception:
                pass

        return results

    run_with_loader(
        parent=parent,
        title=title,
        task=task,
        on_result=on_result,
        on_error=on_error,
        on_cancelled=on_cancelled,
        dialog_options=dialog_options,
    )
