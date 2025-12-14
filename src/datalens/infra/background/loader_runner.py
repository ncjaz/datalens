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
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from datalens.infra.background.loader_worker import LoaderWorker


def run_with_loader(
    parent: QWidget | None,
    title: str,
    task: Callable[[Any], Any],
    on_result: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
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

    Notes
    -----
    This function is UI-safe. All UI updates occur on the main thread.

    The loader dialog is imported lazily at runtime in order to avoid
    circular dependencies between UI and infrastructure modules.
    """
    # Avoid circular imports until LoaderDialog exists
    from datalens.ui.widgets.dialogs.loader_dialog import LoaderDialog

    dialog_kwargs: dict[str, Any] = {"title": title, "parent": parent}
    if dialog_options:
        dialog_kwargs.update(dialog_options)

    dialog = LoaderDialog(**dialog_kwargs)
    worker = LoaderWorker(task)
    # Keep Python references alive for the lifetime of the dialog.
    # (Especially important when parent is None.)
    dialog._loader_worker = worker  # type: ignore[attr-defined]
    dialog._on_result_callback = on_result  # type: ignore[attr-defined]
    dialog._on_error_callback = on_error  # type: ignore[attr-defined]

    def _cleanup() -> None:
        worker.deleteLater()
        try:
            dialog.deleteLater()
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

    dialog._cleanup_callback = _cleanup  # type: ignore[attr-defined]

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

    worker.message.connect(dialog.append_message)

    # Optional progress support
    try:
        worker.progress.connect(dialog.set_progress)
    except Exception:
        pass

    # -------------------------------------------------------------- #
    # Success handler
    # -------------------------------------------------------------- #

    # IMPORTANT: connect to QObject slots so the UI work runs on the main thread.
    worker.finished.connect(dialog._on_worker_finished)
    worker.failed.connect(dialog._on_worker_failed)

    # -------------------------------------------------------------- #
    # Begin execution
    # -------------------------------------------------------------- #

    dialog.show()
    # Ensure the dialog has a chance to paint before the background task begins.
    QTimer.singleShot(0, worker.start)
