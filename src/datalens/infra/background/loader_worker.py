"""
Loader Worker
=============

This module implements :class:`LoaderWorker`, a QObject-based background worker
responsible for executing long-running tasks in a dedicated ``QThread``.

``LoaderWorker`` provides:

- A clean separation between UI and background execution
- Thread-safe message passing via Qt signals
- Safe exception propagation back to the UI
- Integration with :class:`LoaderContext`
- Callbacks for completion or failure

The worker never interacts directly with UI widgets. Instead, it emits signals
that the loader dialog (or any other UI component) can consume on the main
thread.
"""

from __future__ import annotations

import contextvars
import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, QThread

from datalens.core.logging import get_logger
from datalens.infra.background.loader_context import LoaderCancelled, LoaderContext


class LoaderWorker(QObject):
    """
    Execute a loader task in a background thread.

    A loader task is a function of the form::

        def task(ctx: LoaderContext) -> Any:
            ctx.log("Doing work…")
            ...
            return result

    ``LoaderWorker`` handles the lifecycle of the worker thread, the creation
    of :class:`LoaderContext`, and the emission of Qt signals that communicate
    task messages, progress, success, or failure back to the UI.

    Signals
    -------
    message: str
        Emitted whenever the task calls ``ctx.log(...)``.
    progress: float
        Emitted when the task reports progress via ``ctx.set_progress(...)``.
    finished: object
        Emitted with the return value of the task once it completes.
    cancelled:
        Emitted if the task cooperatively cancels (raises ``LoaderCancelled``).
    failed: Exception
        Emitted if the task raises an exception.
    """

    message = Signal(str)
    progress = Signal(float)
    finished = Signal(object)
    cancelled = Signal()
    failed = Signal(Exception)

    def __init__(self, task: Callable[[LoaderContext], Any]) -> None:
        """
        Parameters
        ----------
        task:
            A callable accepting a :class:`LoaderContext`. It is executed in a
            dedicated worker thread.
        """
        super().__init__()
        self._task = task
        self._thread: QThread | None = None
        self._context: contextvars.Context | None = None
        self._cancel_requested = threading.Event()

    def capture_context(self) -> None:
        """
        Capture the current contextvars context for propagation into the worker thread.

        This should be called on the submission thread (typically the UI thread)
        *before* the worker is started, so bound logging context (plugin_id, op_id,
        etc.) is preserved even if startup is deferred via QTimer.
        """
        try:
            self._context = contextvars.copy_context()
        except Exception:
            self._context = None

    # ------------------------------------------------------------------ #
    # Thread management
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """
        Start executing the task in a dedicated ``QThread``.

        The worker object is moved to the new thread, and the thread is cleaned
        up automatically when the task finishes or fails.
        """
        thread = QThread()
        self._thread = thread
        self.moveToThread(thread)

        thread.started.connect(self._run_task)

        # Ensure proper cleanup
        self.finished.connect(thread.quit)
        self.cancelled.connect(thread.quit)
        self.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        thread.start()

    def cancel(self) -> None:
        """
        Request cooperative cancellation.

        Notes:

        - This does not "kill" the thread. The task must periodically check
          ``ctx.is_cancel_requested()`` (or call ``ctx.raise_if_cancelled()``)
          and then exit.
        """
        self._cancel_requested.set()
        try:
            if self._thread is not None:
                self._thread.requestInterruption()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Task execution
    # ------------------------------------------------------------------ #

    def _run_task(self) -> None:
        """
        Execute the task and emit signals based on the outcome.

        This method is invoked inside the worker thread. It constructs a
        :class:`LoaderContext`, executes the task, and emits ``finished`` or
        ``failed`` accordingly.
        """
        ctx = LoaderContext(
            send_message=lambda msg: self.message.emit(msg),
            send_progress=lambda val: self.progress.emit(val),
            is_cancel_requested=lambda: bool(self._cancel_requested.is_set())
            or bool(QThread.currentThread().isInterruptionRequested()),
        )

        try:
            if self._context is None:
                result = self._task(ctx)
            else:
                result = self._context.run(self._task, ctx)
        except LoaderCancelled:
            get_logger(__name__).info(
                "Loader task cancelled",
                extra={"operation": "loader_task", "phase": "cancelled"},
            )
            self.cancelled.emit()
            return
        except Exception as exc:
            get_logger(__name__).exception(
                "Loader task failed",
                extra={"operation": "loader_task", "phase": "error"},
            )
            self.failed.emit(exc)
            return

        self.finished.emit(result)
