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

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, QThread

from datalens.infra.background.loader_context import LoaderContext


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
    failed: Exception
        Emitted if the task raises an exception.
    """

    message = Signal(str)
    progress = Signal(float)
    finished = Signal(object)
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
        self.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        thread.start()

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
        )

        try:
            result = self._task(ctx)
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(exc)
            return

        self.finished.emit(result)
