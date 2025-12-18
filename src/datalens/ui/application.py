from __future__ import annotations

import os
import time

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QApplication

from datalens.core.context import AppContext, create_app_context
from datalens.core.logging import get_logger
from datalens.ui.shortcuts import ShortcutsEventFilter
from datalens.ui.theme import AppTheme


class DatalensApplication(QApplication):
    """
    Minimal QApplication wrapper for V2.

    Stores the shared :class:`~datalens.ui.theme.app_theme.AppTheme` instance so
    dialogs/widgets can resolve it via ``QApplication.instance().app_theme``.
    """

    _DEFAULT_SLOW_EVENT_THRESHOLD_MS = 75.0
    _SLOW_EVENT_IGNORE_TYPES = {
        QEvent.Type.Timer,
    }

    def __init__(
        self,
        argv: list[str],
        *,
        theme: AppTheme | None = None,
        slow_event_threshold_ms: float | None = None,
    ) -> None:
        super().__init__(argv)
        self._sigint_requested = False

        self._slow_event_log = get_logger("datalens.ui.events")
        self._slow_event_threshold_ms = (
            float(slow_event_threshold_ms)
            if slow_event_threshold_ms is not None
            else self._resolve_slow_event_threshold()
        )
        if self._slow_event_threshold_ms > 0:
            self._slow_event_log.info(
                "Slow event logging enabled (threshold=%.1f ms)",
                self._slow_event_threshold_ms,
                extra={"operation": "qt_events", "phase": "init"},
            )

        self.app_theme: AppTheme = theme or AppTheme()
        self.app_theme.apply_to(self)
        self.app_theme.theme_changed.connect(lambda: self.app_theme.apply_to(self))
        self.app_context: AppContext = create_app_context(self.app_theme)
        self.app_context.events.attach_ui_scheduler(lambda fn: QTimer.singleShot(0, fn))

        # Install the global shortcuts event filter (keyboard + mouse chords).
        # This is app-wide, but dispatch only targets the focused top-level window.
        self._shortcuts_filter = ShortcutsEventFilter(self.app_context.shortcuts)
        self.installEventFilter(self._shortcuts_filter)

    def _resolve_slow_event_threshold(self) -> float:
        candidate = os.getenv("DATALENS_SLOW_EVENT_THRESHOLD_MS")
        if candidate:
            try:
                parsed = float(candidate)
            except ValueError:
                self._slow_event_log.warning(
                    "Invalid DATALENS_SLOW_EVENT_THRESHOLD_MS=%s; using default %.1f",
                    candidate,
                    self._DEFAULT_SLOW_EVENT_THRESHOLD_MS,
                    extra={"operation": "qt_events", "phase": "warning"},
                )
                return self._DEFAULT_SLOW_EVENT_THRESHOLD_MS
            if parsed <= 0:
                return 0.0
            return parsed
        return self._DEFAULT_SLOW_EVENT_THRESHOLD_MS

    def _should_profile_event(self, event: object | None) -> bool:
        if event is None:
            return False
        if self._slow_event_threshold_ms <= 0:
            return False
        if not isinstance(event, QEvent):
            return False
        try:
            event_enum = QEvent.Type(event.type())
        except Exception:
            return True
        return event_enum not in self._SLOW_EVENT_IGNORE_TYPES

    def notify(self, receiver, event):  # type: ignore[override]
        profile_event = self._should_profile_event(event)
        start = time.perf_counter() if profile_event else 0.0
        try:
            return super().notify(receiver, event)
        except KeyboardInterrupt:
            # Ctrl+C / SIGINT should behave like an emergency stop when running from a terminal.
            # Do not let the exception escape into Qt (it logs "Error calling Python override...").
            if self._sigint_requested:
                os._exit(130)
            self._sigint_requested = True
            get_logger("datalens.ui").warning(
                "SIGINT received (Ctrl+C); shutting down...",
                extra={"operation": "sigint", "phase": "request"},
            )
            QTimer.singleShot(0, lambda: self.exit(130))
            return True
        except BaseException:
            get_logger("datalens.crash").exception(
                "Unhandled Qt event",
                extra={
                    "operation": "qt_event",
                    "phase": "error",
                    "receiver": type(receiver).__name__ if receiver is not None else "<none>",
                    "event_type": int(event.type()) if isinstance(event, QEvent) else "<unknown>",
                },
            )
            raise
        finally:
            if profile_event:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                if elapsed_ms >= self._slow_event_threshold_ms:
                    receiver_name = type(receiver).__name__ if receiver is not None else "<none>"
                    event_name = str(int(event.type())) if isinstance(event, QEvent) else "<unknown>"
                    self._slow_event_log.warning(
                        "Slow Qt event %s handled by %s: %.1f ms",
                        event_name,
                        receiver_name,
                        elapsed_ms,
                        extra={"operation": "qt_event", "phase": "slow"},
                    )
