"""
Loader Context
==============

This module defines :class:`LoaderContext`, the object passed into long-running
background loader tasks.

A loader task always receives a ``LoaderContext`` instance as its only argument.
The task uses this context to:

- Emit log messages back to the UI and logger
- Optionally report progress (for future loader dialog extensions)
- Cooperatively detect cancellation (optional)

The context is intentionally minimal. It provides strictly one-way communication
from the worker thread back to the UI thread, without exposing any Qt widgets,
app state, or unsafe references.

Cancellation is cooperative: the UI may request cancel, but tasks must
periodically check the token and stop themselves.
"""

from __future__ import annotations

from typing import Callable


class LoaderCancelled(Exception):
    """
    Raised by loader tasks to indicate cooperative cancellation.

    Notes:

    - This is not a "failure" (it should not show error UX).
    - Cancellation is cooperative: tasks must check ``ctx.is_cancel_requested()``
      (or call ``ctx.raise_if_cancelled()``) and then exit.
    """


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
        is_cancel_requested: Callable[[], bool] | None = None,
    ) -> None:
        self._send_message = send_message
        self._send_progress = send_progress
        self._is_cancel_requested = is_cancel_requested

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

    # ------------------------------------------------------------------ #
    # Cooperative cancellation (optional)
    # ------------------------------------------------------------------ #

    def is_cancel_requested(self) -> bool:
        """
        Return True if the user has requested cancellation.

        Cancellation is cooperative: tasks must check this and stop themselves.
        """
        if self._is_cancel_requested is None:
            return False
        try:
            return bool(self._is_cancel_requested())
        except Exception:
            return False

    def raise_if_cancelled(self) -> None:
        """
        Convenience helper for cancellable tasks.

        Raises :class:`LoaderCancelled` if cancellation has been requested.
        """
        if self.is_cancel_requested():
            raise LoaderCancelled()
