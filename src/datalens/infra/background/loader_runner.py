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

from typing import Any, Callable, Optional
from PySide6.QtWidgets import QWidget

from datalens.infra.background.loader_worker import LoaderWorker


def run_with_loader(
    parent: QWidget,
    title: str,
    task: Callable[[Any], Any],
    on_result: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
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

    Notes
    -----
    This function is UI-safe. All UI updates occur on the main thread.

    The loader dialog is imported lazily at runtime in order to avoid
    circular dependencies between UI and infrastructure modules.
    """
    # Avoid circular imports until LoaderDialog exists
    from datalens.ui.widgets.dialogs.loader_dialog import LoaderDialog

    dialog = LoaderDialog(title=title, parent=parent)
    worker = LoaderWorker(task)

    # -------------------------------------------------------------- #
    # Worker → Dialog connections
    # -------------------------------------------------------------- #

    worker.message.connect(dialog.append_message)

    # Optional progress support
    try:
        worker.progress.connect(dialog.set_progress)
    except Exception:
        pass

    # -------------------------------------------------------------- #
    # Success handler
    # -------------------------------------------------------------- #

    def _handle_result(result: Any) -> None:
        dialog.close()
        if on_result:
            on_result(result)
        worker.deleteLater()

    worker.finished.connect(_handle_result)

    # -------------------------------------------------------------- #
    # Failure handler
    # -------------------------------------------------------------- #

    def _handle_error(exc: Exception) -> None:
        dialog.close()
        if on_error:
            on_error(exc)
        worker.deleteLater()

    worker.failed.connect(_handle_error)

    # -------------------------------------------------------------- #
    # Begin execution
    # -------------------------------------------------------------- #

    worker.start()
    dialog.show()
