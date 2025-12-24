from __future__ import annotations

"""
EventHub integration for toast notifications.

Subscribes to ToastRequested events and creates toasts via ToastManager.
"""

import logging

from datalens.core.events import EventHub, ToastRequested
from datalens.ui.widgets.notifications.toast_manager import ToastManager
from datalens.ui.widgets.notifications.toast_types import ToastIconType

log = logging.getLogger(__name__)


def setup_toast_event_subscriber(event_hub: EventHub) -> None:
    """
    Subscribe to ToastRequested events and create toasts.

    This should be called during app initialization after ToastManager
    is set up.

    Args:
        event_hub: The application EventHub instance
    """

    def on_toast_requested(event: object) -> None:
        """Handle ToastRequested event."""
        if not isinstance(event, ToastRequested):
            log.warning(f"Unexpected event type in toast subscriber: {type(event)}")
            return

        try:
            # Map string icon_type to enum
            icon_type_map = {
                "success": ToastIconType.SUCCESS,
                "warning": ToastIconType.WARNING,
                "error": ToastIconType.ERROR,
                "info": ToastIconType.INFO,
            }
            icon_type = icon_type_map.get(event.icon_type.lower(), ToastIconType.INFO)

            # Get manager and show toast
            manager = ToastManager.get_instance()
            manager.show_toast(
                title=event.title,
                message=event.message,
                icon_type=icon_type,
                duration=event.duration,
                trigger="event_hub",
                caller_module=event.publisher_module,
            )
        except Exception as e:
            log.error(f"Failed to show toast from event: {e}", exc_info=True)

    # Subscribe to ToastRequested events
    subscription = event_hub.subscribe(EventHub.TOAST_REQUESTED, on_toast_requested)

    log.info(
        "Toast EventHub subscriber registered",
        extra={
            "operation": "toast",
            "phase": "event_integration_setup",
            "event_name": EventHub.TOAST_REQUESTED,
        },
    )


__all__ = ["setup_toast_event_subscriber"]
