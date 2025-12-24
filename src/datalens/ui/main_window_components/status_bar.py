from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QMainWindow, QStatusBar

from datalens.core.logging import get_logger
from datalens.core.events import EventHub, StatusMessageRequested
from datalens.ui.main_window_components.app_context import try_get_app_context

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StatusBarOptions:
    """
    Options for the main window status bar.

    Keep this minimal: the status bar is a lightweight UX surface meant to show
    the *latest* relevant message, not a full log viewer.
    """

    max_buffer: int = 256
    poll_ms: int = 150
    show_level_at_or_above: int = logging.INFO
    dedupe_window_s: float = 0.5
    max_text: int = 220


class _StatusBarLogHandler(logging.Handler):
    """
    A tiny, thread-safe log sink used by StatusBarController.

    Important: never touch Qt widgets here; this may run on background threads.
    """

    def __init__(self, options: StatusBarOptions) -> None:
        super().__init__(level=options.show_level_at_or_above)
        self._options = options
        self._lock = threading.Lock()
        self._buffer: deque[tuple[float, str, int]] = deque(maxlen=max(1, int(options.max_buffer)))
        self._last_text: str | None = None
        self._last_ts: float = 0.0

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            text = record.getMessage()
            if not text:
                return

            prefix = ""
            plugin = getattr(record, "plugin_id", None)
            if plugin and plugin not in ("-", ""):
                prefix = str(plugin)

            if not prefix:
                # Best-effort: infer plugin id from module name.
                name = str(getattr(record, "name", "") or "")
                if name.startswith("datalens.plugins."):
                    parts = name.split(".")
                    if len(parts) >= 3 and parts[2]:
                        prefix = parts[2]

            if prefix:
                text = f"{prefix}: {text}"

            now = time.monotonic()
            with self._lock:
                if (
                    self._last_text is not None
                    and text == self._last_text
                    and (now - self._last_ts) <= float(self._options.dedupe_window_s)
                ):
                    return
                self._last_text = text
                self._last_ts = now
                self._buffer.append((now, text, int(getattr(record, "levelno", logging.INFO))))
        except Exception:
            # Best-effort: never let UI monitoring cause logging failures.
            return

    def drain(self) -> list[tuple[float, str, int]]:
        with self._lock:
            items = list(self._buffer)
            self._buffer.clear()
            return items


class StatusBarController:
    """
    Main window status bar controller.

    Pairing:
    - UI: this module (status bar + right-side "last message" widget)
    - Logging system: `datalens.core.logging` (async pipeline)
    """

    def __init__(self, main_window: QMainWindow, *, options: StatusBarOptions | None = None) -> None:
        self._main_window = main_window
        self._options = options or StatusBarOptions()

        status = main_window.statusBar()
        if status is None:
            status = QStatusBar(main_window)
            main_window.setStatusBar(status)
        self._status_bar = status

        self._right_label = QLabel("", status)
        self._right_label.setObjectName("MainStatusBarLog")
        self._right_label.setTextInteractionFlags(self._right_label.textInteractionFlags())
        self._right_label.setMinimumWidth(260)
        self._right_label.setToolTip("Latest message (from logs)")
        status.addPermanentWidget(self._right_label, stretch=1)

        self._handler = _StatusBarLogHandler(self._options)
        self._install_logging_handler()

        self._timer = QTimer(main_window)
        self._timer.setInterval(max(25, int(self._options.poll_ms)))
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

        self._events_sub = None
        app_ctx = try_get_app_context()
        if app_ctx is not None:
            self._events_sub = app_ctx.events.subscribe(EventHub.STATUS_MESSAGE_REQUESTED, self._on_status_message)

        main_window.destroyed.connect(lambda *_: self.close())

    def close(self) -> None:
        try:
            self._timer.stop()
        except Exception:
            pass
        try:
            if self._events_sub is not None:
                self._events_sub.unsubscribe()
        except Exception:
            pass
        self._uninstall_logging_handler()

    def show_left(self, text: str, *, timeout_ms: int = 3000) -> None:
        self._status_bar.showMessage(str(text), int(timeout_ms))

    def set_right(self, text: str) -> None:
        self._right_label.setText(str(text))
        self._right_label.setToolTip(str(text))

    def _install_logging_handler(self) -> None:
        # Attach to the "datalens" logger namespace so we mirror what users see
        # in terminal, but without affecting the core async pipeline.
        root = logging.getLogger("datalens")
        root.addHandler(self._handler)
        log.debug("Status bar log handler installed", extra={"operation": "status_bar", "phase": "install"})

    def _uninstall_logging_handler(self) -> None:
        try:
            root = logging.getLogger("datalens")
            root.removeHandler(self._handler)
        except Exception:
            pass
        log.debug("Status bar log handler removed", extra={"operation": "status_bar", "phase": "uninstall"})

    def _format_for_status(self, text: str, *, levelno: int, new_count: int) -> str:
        s = text.strip()
        if levelno >= logging.ERROR:
            s = f"Error: {s}"
        elif levelno >= logging.WARNING:
            s = f"Warning: {s}"

        max_len = max(20, int(self._options.max_text))
        if len(s) > max_len:
            s = s[: max_len - 1].rstrip() + "…"
        if new_count > 1:
            s = f"{s} (+{new_count - 1})"
        return s

    def _on_tick(self) -> None:
        items = self._handler.drain()
        if not items:
            return

        # Show the most recent line, and indicate if multiple arrived.
        _, text, levelno = items[-1]
        self.set_right(self._format_for_status(text, levelno=levelno, new_count=len(items)))

    def _on_status_message(self, payload: object) -> None:
        try:
            if isinstance(payload, StatusMessageRequested):
                self.show_left(payload.text, timeout_ms=int(payload.timeout_ms))
                return
            if isinstance(payload, dict):
                text = str(payload.get("text", "")).strip()
                if not text:
                    return
                timeout_ms = int(payload.get("timeout_ms", 3000))
                self.show_left(text, timeout_ms=timeout_ms)
        except Exception:
            log.debug(
                "Failed to handle status message event (best-effort)",
                exc_info=True,
                extra={"operation": "status_bar", "phase": "event_error"},
            )
