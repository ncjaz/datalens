from __future__ import annotations

"""
Convenience API for toast notifications.

Provides simple functions for common toast patterns:
- show_success()
- show_warning()
- show_error()
- show_info()

These are thread-safe, non-blocking wrappers around ToastManager.
"""

import logging

from datalens.ui.widgets.notifications.toast_manager import ToastManager
from datalens.ui.widgets.notifications.toast_types import ToastIconType, ToastPosition

log = logging.getLogger(__name__)


def show_success(
    title: str,
    message: str = "",
    *,
    duration: int = 5000,
    position: ToastPosition | None = None,
) -> None:
    """
    Show a success toast notification.

    Args:
        title: Toast title
        message: Optional message text
        duration: Auto-dismiss time in ms (0 = manual close only)
        position: Position override (None = use default)

    Example:
        ```python
        show_success("Export Complete", "File saved to Desktop")
        ```
    """
    try:
        manager = ToastManager.get_instance()
        manager.show_toast(
            title=title,
            message=message,
            icon_type=ToastIconType.SUCCESS,
            duration=duration,
            position=position,
            trigger="direct_call",
        )
    except Exception as e:
        log.error(f"Failed to show success toast: {e}", exc_info=True)


def show_warning(
    title: str,
    message: str = "",
    *,
    duration: int = 7000,
    position: ToastPosition | None = None,
) -> None:
    """
    Show a warning toast notification.

    Args:
        title: Toast title
        message: Optional message text
        duration: Auto-dismiss time in ms (0 = manual close only, default 7s)
        position: Position override (None = use default)

    Example:
        ```python
        show_warning("Memory Low", "Consider closing unused projects")
        ```
    """
    try:
        manager = ToastManager.get_instance()
        manager.show_toast(
            title=title,
            message=message,
            icon_type=ToastIconType.WARNING,
            duration=duration,
            position=position,
            trigger="direct_call",
        )
    except Exception as e:
        log.error(f"Failed to show warning toast: {e}", exc_info=True)


def show_error(
    title: str,
    message: str = "",
    *,
    duration: int = 10000,
    position: ToastPosition | None = None,
) -> None:
    """
    Show an error toast notification.

    Args:
        title: Toast title
        message: Optional message text
        duration: Auto-dismiss time in ms (0 = manual close only, default 10s)
        position: Position override (None = use default)

    Example:
        ```python
        show_error("Export Failed", "Disk full or permission denied")
        ```
    """
    try:
        manager = ToastManager.get_instance()
        manager.show_toast(
            title=title,
            message=message,
            icon_type=ToastIconType.ERROR,
            duration=duration,
            position=position,
            trigger="direct_call",
        )
    except Exception as e:
        log.error(f"Failed to show error toast: {e}", exc_info=True)


def show_info(
    title: str,
    message: str = "",
    *,
    duration: int = 5000,
    position: ToastPosition | None = None,
) -> None:
    """
    Show an info toast notification.

    Args:
        title: Toast title
        message: Optional message text
        duration: Auto-dismiss time in ms (0 = manual close only)
        position: Position override (None = use default)

    Example:
        ```python
        show_info("Processing Started", "This may take a few minutes")
        ```
    """
    try:
        manager = ToastManager.get_instance()
        manager.show_toast(
            title=title,
            message=message,
            icon_type=ToastIconType.INFO,
            duration=duration,
            position=position,
            trigger="direct_call",
        )
    except Exception as e:
        log.error(f"Failed to show info toast: {e}", exc_info=True)


__all__ = [
    "show_success",
    "show_warning",
    "show_error",
    "show_info",
]
