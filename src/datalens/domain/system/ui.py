from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class LoaderUiSettings:
    """
    User preferences for loader dialog messaging.

    These settings only affect what is mirrored into the loader dialog. They do
    not change what is written to the log file.
    """

    # Show messages emitted explicitly via `LoaderContext.log(...)`.
    show_ctx_messages: bool = True

    # Show messages logged with `extra={'progress': True}` (or `log.progress(...)`).
    show_log_progress: bool = True

    # Optional: also mirror normal logs by level (defaults off to avoid spam).
    show_log_info: bool = False
    show_log_warning: bool = False
    show_log_error: bool = False
    show_log_critical: bool = False


@dataclass(frozen=True)
class ToastTypeUiVisibility:
    """
    Per-toast-type visibility policy.

    Notes:
    - "inactive" approximates "window is behind another app" by checking
      `QWidget.isActiveWindow()` on the toast anchor window.
    - When disabled, toasts are not shown and are queued until visible again.
    """

    show_when_minimized: bool = True
    show_when_inactive: bool = True


class ToastKind(str, Enum):
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"


@dataclass(frozen=True)
class ToastUiSettings:
    """
    User Interface preferences for toast notifications.

    Defaults match current behavior: toasts can show even when the app is
    minimized or inactive.
    """

    success: ToastTypeUiVisibility = field(default_factory=ToastTypeUiVisibility)
    warning: ToastTypeUiVisibility = field(default_factory=ToastTypeUiVisibility)
    error: ToastTypeUiVisibility = field(default_factory=ToastTypeUiVisibility)
    info: ToastTypeUiVisibility = field(default_factory=ToastTypeUiVisibility)

    def for_kind(self, kind: ToastKind) -> ToastTypeUiVisibility:
        if kind == ToastKind.SUCCESS:
            return self.success
        if kind == ToastKind.WARNING:
            return self.warning
        if kind == ToastKind.ERROR:
            return self.error
        return self.info


__all__ = ["LoaderUiSettings", "ToastTypeUiVisibility", "ToastUiSettings", "ToastKind"]
