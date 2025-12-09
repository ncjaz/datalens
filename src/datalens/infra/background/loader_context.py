"""
Loader Context
==============

This module defines :class:`LoaderContext`, the object passed into long-running
background loader tasks.

A loader task always receives a ``LoaderContext`` instance as its only argument.
The task uses this context to:

- Emit log messages back to the UI and logger
- Optionally report progress (for future loader dialog extensions)

The context is intentionally minimal. It provides strictly one-way communication
from the worker thread back to the UI thread, without exposing any Qt widgets,
app state, or unsafe references.
"""

from __future__ import annotations

from typing import Callable


class LoaderContext:
    """
    Context object passed to loader tasks executed by ``LoaderWorker``.

    Loader tasks should call :meth:`log` to emit status messages back to the
    loader dialog. These messages are delivered via Qt signals in a thread-safe
    manner.

    Parameters
    ----------
    send_message:
        Callable used internally by :class:`LoaderWorker` to route log messages
        back to the UI.
    send_progress:
        Optional callable for reporting progress values in the range 0–1.
    """

    def __init__(
        self,
        send_message: Callable[[str], None],
        send_progress: Callable[[float], None] | None = None,
    ) -> None:
        self._send_message = send_message
        self._send_progress = send_progress

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #

    def log(self, text: str) -> None:
        """
        Emit a log message from within a long-running task.

        This is the primary mechanism for communicating status information to
        the loader dialog and the application logger.

        Notes
        -----
        - This method is thread-safe.
        - Messages are emitted immediately to the main thread.
        """
        self._send_message(text)

    # ------------------------------------------------------------------ #
    # Progress reporting (optional)
    # ------------------------------------------------------------------ #

    def set_progress(self, value: float) -> None:
        """
        Report task progress to the UI.

        Parameters
        ----------
        value:
            A float in the range 0–1 indicating completion percentage.

        Notes
        -----
        Progress reporting is optional. If the loader dialog does not expose a
        progress bar, this call safely becomes a no-op.
        """
        if self._send_progress is not None:
            self._send_progress(value)
