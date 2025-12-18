from __future__ import annotations

from dataclasses import dataclass


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


__all__ = ["LoaderUiSettings"]

