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
from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtWidgets import QWidget

from datalens.infra.background.loader_worker import LoaderWorker


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
        on_result: Callable[[Any], None] | None,
        on_error: Callable[[Exception], None] | None,
        keep_open_on_error: bool,
    ) -> None:
        super().__init__(dialog)
        self._dialog = dialog
        self._cleanup = cleanup
        self._on_result = on_result
        self._on_error = on_error
        self._keep_open_on_error = keep_open_on_error

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
        if callable(self._on_result):
            QTimer.singleShot(0, lambda: self._on_result(result))

    @Slot(Exception)
    def on_failed(self, exc: Exception) -> None:
        try:
            if self._keep_open_on_error:
                try:
                    show_error = getattr(self._dialog, "show_error", None)
                    if callable(show_error):
                        show_error(str(exc))
                except Exception:
                    pass
            if callable(self._on_error):
                self._on_error(exc)
        finally:
            if not self._keep_open_on_error:
                try:
                    self._dialog.close()
                finally:
                    self._cleanup()


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
    from datalens.ui.theme import AppTheme

    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        candidate = getattr(app, "app_theme", None) if app is not None else None
        theme = candidate if isinstance(candidate, AppTheme) else AppTheme()
    except Exception:
        theme = AppTheme()

    keep_open_on_error = False
    dialog_kwargs: dict[str, Any] = {"title": title, "parent": parent, "theme": theme}
    if dialog_options:
        keep_open_on_error = bool(dialog_options.get("keep_open_on_error", False))
        dialog_kwargs.update({k: v for k, v in dialog_options.items() if k != "keep_open_on_error"})

    dialog = LoaderDialog(**dialog_kwargs)
    worker = LoaderWorker(task)
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

    worker.message.connect(dialog.append_message)

    worker.progress.connect(dialog.set_progress)

    # -------------------------------------------------------------- #
    # Success handler
    # -------------------------------------------------------------- #

    dialog.destroyed.connect(lambda *_: _cleanup())

    router = _ResultRouter(
        dialog=dialog,
        cleanup=_cleanup,
        on_result=on_result,
        on_error=on_error,
        keep_open_on_error=keep_open_on_error,
    )
    dialog._loader_router = router  # type: ignore[attr-defined]

    worker.finished.connect(router.on_finished)
    worker.failed.connect(router.on_failed)

    # -------------------------------------------------------------- #
    # Begin execution
    # -------------------------------------------------------------- #

    dialog.show()
    # Ensure the dialog has a chance to paint before the background task begins.
    QTimer.singleShot(0, worker.start)
