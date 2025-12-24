from __future__ import annotations

"""
Toast notification manager (singleton).

Manages multiple toast notifications with:
- Queue management (max 3 visible, up to 10 queued)
- Positioning at 9 screen locations
- Smooth stacking and repositioning animations
- Thread-safe, non-blocking show_toast() API
- Comprehensive logging for diagnosis
"""

import inspect
import logging
import os
from collections.abc import Callable
from collections import deque
from typing import TYPE_CHECKING

import shiboken6
from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtWidgets import QWidget

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.notifications.toast_types import ToastIconType, ToastParams, ToastPosition
from datalens.ui.widgets.notifications.toast_widget import SLIDE_OFFSET, ToastWidget
from datalens.domain.system.ui import ToastKind, ToastUiSettings

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

# Queue limits
MAX_VISIBLE_TOASTS = 3
MAX_QUEUED_TOASTS = 10

# Positioning
TOAST_SPACING = 5 # pixels between stacked toasts
EDGE_MARGIN = 12  # pixels from window edge


class ToastManager:
    """
    Singleton manager for toast notifications.

    Handles:
    - Queue management (max visible, queued toasts)
    - Positioning and stacking
    - Smooth animations when toasts appear/close
    - Thread-safe, non-blocking API
    """

    _instance: ToastManager | None = None

    def __init__(self, parent: QWidget, theme: AppTheme, position: ToastPosition = ToastPosition.BOTTOM_RIGHT) -> None:
        """
        Initialize the toast manager.

        Args:
            parent: Parent widget for positioning reference
            theme: Application theme
            position: Default position for toasts
        """
        self._parent = parent
        self._theme = theme
        self._position = position

        # Active toasts (visible on screen)
        self._visible_toasts: list[ToastWidget] = []

        # Queue for overflow toasts
        self._queued_toasts: deque[ToastParams] = deque(maxlen=MAX_QUEUED_TOASTS)

        # Animation tracking
        self._reposition_animations: list[QPropertyAnimation] = []
        self._connected_parent = False
        self._anchor_watcher: _ToastAnchorWatcher | None = None
        self._anchor_window: QWidget | None = None
        self._bind_anchor_window(parent)

        self._ui_settings = ToastUiSettings()

    @classmethod
    def get_instance(cls, parent: QWidget | None = None, theme: AppTheme | None = None) -> ToastManager:
        """
        Get the singleton instance of ToastManager.

        Args:
            parent: Parent widget (required for first call)
            theme: Application theme (required for first call)

        Returns:
            The singleton ToastManager instance
        """
        if cls._instance is None:
            if parent is None or theme is None:
                raise ValueError("ToastManager requires parent and theme for first initialization")
            cls._instance = cls(parent, theme)
        elif parent is not None and theme is not None:
            cls._instance._rebind(parent=parent, theme=theme)
        return cls._instance

    @staticmethod
    def _is_valid_widget(widget: QWidget | None) -> bool:
        if widget is None:
            return False
        try:
            return bool(shiboken6.isValid(widget))
        except Exception:
            return False

    def _prune_visible_toasts(self) -> None:
        self._visible_toasts = [t for t in self._visible_toasts if self._is_valid_widget(t)]

    def _rebind(self, *, parent: QWidget, theme: AppTheme) -> None:
        """
        Rebind the singleton to a new UI parent/theme.

        This is important when the previous parent workspace was destroyed (e.g.
        plugin/widget tests) so the manager doesn't retain references to deleted
        Qt objects.
        """
        if not self._is_valid_widget(parent):
            return

        self._parent = parent
        self._theme = theme
        self._bind_anchor_window(parent)

        if not self._connected_parent:
            try:
                parent.destroyed.connect(self._on_parent_destroyed)  # type: ignore[attr-defined]
                self._connected_parent = True
            except Exception:
                self._connected_parent = False

        self._prune_visible_toasts()

    def _on_parent_destroyed(self, *_args) -> None:
        self._visible_toasts.clear()
        self._queued_toasts.clear()
        self._reposition_animations.clear()
        self._anchor_watcher = None
        self._anchor_window = None

    def _bind_anchor_window(self, parent: QWidget) -> None:
        """
        Keep toasts anchored to the top-level window that owns `parent`.

        ToastWidget uses `Qt.Tool`, so it's a top-level window; it will not
        automatically move with its parent unless we recompute positions.
        """
        try:
            anchor = parent.window()
        except Exception:
            anchor = None

        if not self._is_valid_widget(anchor):
            self._anchor_watcher = None
            self._anchor_window = None
            return

        if self._anchor_window is anchor and self._anchor_watcher is not None:
            return

        self._anchor_window = anchor
        self._anchor_watcher = _ToastAnchorWatcher(
            anchor,  # QObject parent for correct lifetime
            on_changed=self._on_anchor_changed,
        )
        try:
            anchor.installEventFilter(self._anchor_watcher)
        except Exception:
            pass

    def _on_anchor_changed(self) -> None:
        self._prune_visible_toasts()
        self._enforce_visibility_policy()
        self._prune_visible_toasts()

        if self._visible_toasts and self._is_valid_widget(self._anchor_window):
            # Move immediately (no animation) so the toasts stay visually attached to the window.
            try:
                sizes = [self._toast_effective_size(t) for t in self._visible_toasts]
                positions = self._calculate_stack_positions(position=self._position, sizes=sizes)
            except Exception:
                positions = []

            for toast, pos in zip(self._visible_toasts, positions, strict=False):
                try:
                    toast.move(pos)
                except RuntimeError:
                    continue

        self._flush_queue(max_to_show=MAX_VISIBLE_TOASTS)

    def _anchor_rect(self) -> tuple[int, int, int, int]:
        anchor = self._anchor_window if self._is_valid_widget(self._anchor_window) else None
        if anchor is None:
            try:
                anchor = self._parent.window()
            except Exception:
                anchor = None

        if anchor is not None and self._is_valid_widget(anchor):
            rect = anchor.geometry()
            return rect.x(), rect.y(), rect.width(), rect.height()

        parent_rect = self._parent.rect()
        return 0, 0, parent_rect.width(), parent_rect.height()

    @staticmethod
    def _start_offset_for(position: ToastPosition) -> QPoint:
        from_top = position in (ToastPosition.TOP_LEFT, ToastPosition.TOP_CENTER, ToastPosition.TOP_RIGHT)
        from_bottom = position in (ToastPosition.BOTTOM_LEFT, ToastPosition.BOTTOM_CENTER, ToastPosition.BOTTOM_RIGHT)
        from_left = position in (ToastPosition.TOP_LEFT, ToastPosition.CENTER_LEFT, ToastPosition.BOTTOM_LEFT)
        from_right = position in (ToastPosition.TOP_RIGHT, ToastPosition.CENTER_RIGHT, ToastPosition.BOTTOM_RIGHT)

        dx = -SLIDE_OFFSET if from_left else (SLIDE_OFFSET if from_right else 0)
        dy = -SLIDE_OFFSET if from_top else (SLIDE_OFFSET if from_bottom else 0)
        return QPoint(dx, dy)

    def _toast_effective_size(self, toast: ToastWidget) -> QSize:
        try:
            current = toast.size()
        except Exception:
            current = QSize()

        if current.width() > 0 and current.height() > 0:
            return current

        try:
            hint = toast.sizeHint()
        except Exception:
            hint = QSize()

        from datalens.ui.widgets.notifications.toast_widget import MAX_HEIGHT, MAX_WIDTH, MIN_HEIGHT, MIN_WIDTH

        width = max(MIN_WIDTH, min(MAX_WIDTH, hint.width() or MIN_WIDTH))
        height = max(MIN_HEIGHT, min(MAX_HEIGHT, hint.height() or MIN_HEIGHT))
        return QSize(width, height)

    def _calculate_stack_positions(self, *, position: ToastPosition, sizes: list[QSize]) -> list[QPoint]:
        """
        Calculate final positions for a vertical toast stack (index 0 nearest the anchor edge).

        This uses each toast's effective size. Using MAX_WIDTH/MAX_HEIGHT for all toasts makes
        short toasts appear "far" from edges and creates excessive gaps.
        """
        if not sizes:
            return []

        base_x, base_y, parent_width, parent_height = self._anchor_rect()

        widths = [max(1, int(s.width())) for s in sizes]
        heights = [max(1, int(s.height())) for s in sizes]

        total_height = sum(heights) + (len(heights) - 1) * TOAST_SPACING

        def x_for(w: int) -> int:
            if position in (ToastPosition.BOTTOM_LEFT, ToastPosition.TOP_LEFT, ToastPosition.CENTER_LEFT):
                return base_x + EDGE_MARGIN
            if position in (ToastPosition.BOTTOM_RIGHT, ToastPosition.TOP_RIGHT, ToastPosition.CENTER_RIGHT):
                return base_x + parent_width - w - EDGE_MARGIN
            return base_x + (parent_width - w) // 2

        points: list[QPoint] = []
        if position in (ToastPosition.TOP_LEFT, ToastPosition.TOP_CENTER, ToastPosition.TOP_RIGHT):
            y = base_y + EDGE_MARGIN
            for w, h in zip(widths, heights, strict=False):
                points.append(QPoint(x_for(w), y))
                y += h + TOAST_SPACING
            return points

        if position in (ToastPosition.BOTTOM_LEFT, ToastPosition.BOTTOM_CENTER, ToastPosition.BOTTOM_RIGHT):
            y = base_y + parent_height - EDGE_MARGIN
            for w, h in zip(widths, heights, strict=False):
                y -= h
                points.append(QPoint(x_for(w), y))
                y -= TOAST_SPACING
            return points

        y = base_y + (parent_height - total_height) // 2
        for w, h in zip(widths, heights, strict=False):
            points.append(QPoint(x_for(w), y))
            y += h + TOAST_SPACING
        return points

    @staticmethod
    def _kind_for_icon_type(icon_type: ToastIconType) -> ToastKind:
        if icon_type == ToastIconType.SUCCESS:
            return ToastKind.SUCCESS
        if icon_type == ToastIconType.WARNING:
            return ToastKind.WARNING
        if icon_type == ToastIconType.ERROR:
            return ToastKind.ERROR
        return ToastKind.INFO

    def _anchor_state(self) -> tuple[bool, bool]:
        """
        Returns (minimized, active) for the toast anchor window.
        """
        anchor = self._anchor_window if self._is_valid_widget(self._anchor_window) else None
        if anchor is None:
            try:
                anchor = self._parent.window()
            except Exception:
                anchor = None

        if anchor is None or not self._is_valid_widget(anchor):
            return False, True

        try:
            minimized = bool(anchor.windowState() & Qt.WindowMinimized)
        except Exception:
            minimized = False

        try:
            active = bool(anchor.isActiveWindow())
        except Exception:
            active = True

        return minimized, active

    def _can_show_now(self, icon_type: ToastIconType) -> bool:
        minimized, active = self._anchor_state()
        policy = self._ui_settings.for_kind(self._kind_for_icon_type(icon_type))
        if minimized:
            return bool(policy.show_when_minimized)
        if not active:
            return bool(policy.show_when_inactive)
        return True

    def _queue(self, params: ToastParams) -> None:
        if len(self._queued_toasts) >= MAX_QUEUED_TOASTS:
            discarded = self._queued_toasts.popleft()
            log.warning(
                "Toast queue full, discarding oldest queued toast",
                extra={
                    "operation": "toast",
                    "phase": "queue_overflow",
                    "max_queue_size": MAX_QUEUED_TOASTS,
                    "discarded_toast_title": discarded.title,
                },
            )

        self._queued_toasts.append(params)
        log.debug(
            "Toast queued",
            extra={
                "operation": "toast",
                "phase": "queued",
                "queue_size": len(self._queued_toasts),
                "toast_title": params.title,
            },
        )

    def _evict_oldest_visible(self, *, reason: str) -> None:
        """
        Remove the oldest visible toast (furthest from the anchor edge) immediately.

        This is used to keep the newest toasts visible when we're over capacity.
        """
        self._prune_visible_toasts()
        if not self._visible_toasts:
            return
        oldest = self._visible_toasts.pop(-1)
        try:
            oldest.hide()
        except Exception:
            pass
        try:
            oldest.close_toast(reason=reason)
        except Exception:
            try:
                oldest.deleteLater()
            except Exception:
                pass

    def _enforce_visibility_policy(self) -> None:
        """
        Suppress (hide/pause) visible toasts that are not allowed in the current window state.

        If the user disables "show when minimized" or "show when inactive" for a
        toast type, those toasts temporarily hide and pause their dismiss timers.
        When the window becomes eligible again, they re-appear and continue.
        """
        self._prune_visible_toasts()
        minimized, active = self._anchor_state()

        for toast in list(self._visible_toasts):
            try:
                icon_type = toast.icon_type
            except Exception:
                icon_type = ToastIconType.INFO
            policy = self._ui_settings.for_kind(self._kind_for_icon_type(icon_type))

            suppressed_reason: str | None = None
            if minimized and not policy.show_when_minimized:
                suppressed_reason = "minimized"
            elif (not active) and not policy.show_when_inactive:
                suppressed_reason = "inactive"

            try:
                if suppressed_reason is None:
                    toast.set_suppressed(False, reason="eligible")
                else:
                    toast.set_suppressed(True, reason=f"suppressed_{suppressed_reason}")
            except Exception:
                # Best-effort fallback if toast widget doesn't support suppression.
                try:
                    if suppressed_reason is None:
                        toast.show()
                    else:
                        toast.hide()
                except Exception:
                    pass

    def _flush_queue(self, *, max_to_show: int) -> None:
        if max_to_show <= 0:
            return
        shown = 0
        while self._queued_toasts and shown < max_to_show:
            next_params = self._queued_toasts[-1]  # newest
            if not self._can_show_now(next_params.icon_type):
                return
            self._queued_toasts.pop()
            if len(self._visible_toasts) >= MAX_VISIBLE_TOASTS:
                self._evict_oldest_visible(reason="evicted_for_queue")
            self._create_and_show_toast(next_params)
            shown += 1

    def show_toast(
        self,
        title: str,
        message: str = "",
        icon_type: ToastIconType = ToastIconType.INFO,
        duration: int = 5000,
        position: ToastPosition | None = None,
        trigger: str = "direct_call",
        caller_module: str | None = None,
    ) -> None:
        """
        Show a toast notification (non-blocking).

        This method returns immediately; toast creation is deferred to the UI thread.

        Args:
            title: Toast title
            message: Optional message text
            icon_type: Type of notification
            duration: Auto-dismiss time in ms (0 = manual close only)
            position: Position override (None = use default)
            trigger: How toast was triggered (direct_call, event_hub, signal)
            caller_module: Module that triggered the toast (for logging)
        """
        # Extract caller module if not provided
        if caller_module is None:
            try:
                frame = inspect.currentframe()
                if frame and frame.f_back:
                    caller_module = frame.f_back.f_globals.get("__name__", "unknown")
            except Exception:
                caller_module = "unknown"

        # In automated tests, keep toasts short-lived so they don't outlive
        # the widget/workspace lifetime and destabilize teardown.
        if (os.environ.get("DATALENS_TESTING") == "1") or os.environ.get("PYTEST_CURRENT_TEST"):
            duration = 250 if duration <= 0 else min(int(duration), 750)

        # Create toast parameters
        params = ToastParams(
            title=title,
            message=message,
            icon_type=icon_type,
            duration=duration,
            position=position or self._position,
            trigger=trigger,
            caller_module=caller_module,
        )

        # Log toast request
        log.info(
            "Toast request received",
            extra={
                "operation": "toast",
                "phase": "request",
                "toast_type": icon_type.value,
                "title": title,
                # Avoid LogRecord reserved key "message" (would raise KeyError).
                "toast_message": message[:100] if message else "",
                "duration_ms": duration,
                "position": params.position.value,
                "trigger": trigger,
                "caller_module": caller_module,
            },
        )

        # Defer to UI thread using QTimer.singleShot
        QTimer.singleShot(0, lambda: self._create_toast_on_ui_thread(params))

    def apply_ui_settings(self, settings: ToastUiSettings) -> None:
        self._ui_settings = settings
        self._on_anchor_changed()

    def _create_toast_on_ui_thread(self, params: ToastParams) -> None:
        """
        Create and show toast on UI thread.

        This is called via QTimer.singleShot to ensure non-blocking behavior.

        Args:
            params: Toast parameters
        """
        self._prune_visible_toasts()

        if not self._is_valid_widget(self._parent):
            log.warning(
                "ToastManager parent is no longer valid; dropping toast request",
                extra={"operation": "toast", "phase": "dropped", "toast_title": params.title},
            )
            return

        if not self._can_show_now(params.icon_type):
            self._queue(params)
            return

        # If we're at capacity, evict the oldest visible toast so the new one can show.
        if len(self._visible_toasts) >= MAX_VISIBLE_TOASTS:
            self._evict_oldest_visible(reason="evicted_for_new")

        self._create_and_show_toast(params)

    def _create_and_show_toast(self, params: ToastParams) -> None:
        """
        Create toast widget and show with animation.

        Args:
            params: Toast parameters
        """
        self._prune_visible_toasts()
        if not self._is_valid_widget(self._parent):
            return

        # Create toast widget
        toast = ToastWidget(
            self._parent,
            self._theme,
            icon_type=params.icon_type,
            toast_id=f"toast_{len(self._visible_toasts)}_{id(params)}",
        )

        # Set toast content
        toast.set_title(params.title)
        if params.message:
            toast.set_message(params.message)
        toast.set_duration(params.duration)

        # Connect closed signal
        toast.closed.connect(lambda: self._on_toast_closed(toast))
        toast.destroyed.connect(lambda *_: self._on_toast_destroyed(toast.toast_id))

        # Ensure an initial size before positioning; this affects edge spacing.
        try:
            toast.resize(toast.sizeHint())
        except Exception:
            pass
        new_size = self._toast_effective_size(toast)

        sizes = [new_size, *[self._toast_effective_size(t) for t in self._visible_toasts]]
        positions = self._calculate_stack_positions(position=params.position, sizes=sizes)
        final_pos = positions[0]
        start_pos = QPoint(final_pos) + self._start_offset_for(params.position)

        # Reposition existing toasts to make room (size-aware).
        if self._visible_toasts:
            self._shift_existing_toasts_away(params.position, new_toast_size=new_size)

        # Add to visible list
        self._visible_toasts.insert(0, toast)  # Insert at index 0 (nearest to edge)

        # Position toast at start position
        toast.move(start_pos)

        # Show toast (will fade in)
        toast.show()

        # Start slide animation
        slide_animation = QPropertyAnimation(toast, b"pos", toast)
        slide_animation.setDuration(250)
        slide_animation.setStartValue(start_pos)
        slide_animation.setEndValue(final_pos)
        slide_animation.setEasingCurve(QEasingCurve.OutCubic)
        slide_animation.start(QAbstractAnimation.DeleteWhenStopped)

        log.debug(
            "Toast created and shown",
            extra={
                "operation": "toast",
                "phase": "created",
                "toast_id": toast._toast_id,
                "visible_count": len(self._visible_toasts),
            },
        )

    def _on_toast_closed(self, toast: ToastWidget) -> None:
        """
        Handle toast closed event.

        Args:
            toast: The toast that was closed
        """
        # Remove from visible list
        if toast in self._visible_toasts:
            self._visible_toasts.remove(toast)

        log.debug(
            "Toast removed from visible list",
            extra={
                "operation": "toast",
                "phase": "removed",
                "toast_id": toast._toast_id,
                "remaining_visible": len(self._visible_toasts),
            },
        )

        # Reposition remaining toasts to fill gap
        if self._visible_toasts:
            self._reposition_toasts()

        self._flush_queue(max_to_show=1)

    def _on_toast_destroyed(self, toast_id: str) -> None:
        """
        Best-effort cleanup if a toast is deleted without emitting `closed`.
        """
        before = len(self._visible_toasts)
        self._visible_toasts = [t for t in self._visible_toasts if getattr(t, "_toast_id", None) != toast_id]
        if len(self._visible_toasts) != before and self._visible_toasts:
            try:
                self._reposition_toasts()
            except Exception:
                pass
        self._flush_queue(max_to_show=1)

    def _shift_existing_toasts_away(self, position: ToastPosition, *, new_toast_size: QSize) -> None:
        """
        Shift existing toasts away from edge to make room for new toast.

        Args:
            position: Toast position (determines shift direction)
        """
        self._prune_visible_toasts()
        if not self._visible_toasts:
            return

        sizes = [new_toast_size, *[self._toast_effective_size(t) for t in self._visible_toasts]]
        positions = self._calculate_stack_positions(position=position, sizes=sizes)

        for idx, toast in enumerate(self._visible_toasts, start=1):
            try:
                new_pos = positions[idx]
            except Exception:
                continue
            try:
                animation = QPropertyAnimation(toast, b"pos", toast)
                animation.setDuration(200)
                animation.setStartValue(toast.pos())
                animation.setEndValue(new_pos)
                animation.setEasingCurve(QEasingCurve.InOutQuad)
                animation.start(QAbstractAnimation.DeleteWhenStopped)
            except RuntimeError:
                continue

        if self._visible_toasts:
            log.debug(
                "Existing toasts shifted away from edge",
                extra={
                    "operation": "toast",
                    "phase": "reposition",
                    "count": len(self._visible_toasts),
                    "direction": "away_from_edge",
                },
            )

    def _reposition_toasts(self) -> None:
        """Reposition all visible toasts to fill gaps."""
        # Use the position from the first visible toast if available
        if not self._visible_toasts:
            return

        self._prune_visible_toasts()
        if not self._visible_toasts:
            return

        # Determine position (use manager's default)
        position = self._position

        sizes = [self._toast_effective_size(t) for t in self._visible_toasts]
        positions = self._calculate_stack_positions(position=position, sizes=sizes)
        for toast, new_pos in zip(self._visible_toasts, positions, strict=False):
            try:
                animation = QPropertyAnimation(toast, b"pos", toast)
                animation.setDuration(200)
                animation.setStartValue(toast.pos())
                animation.setEndValue(new_pos)
                animation.setEasingCurve(QEasingCurve.InOutQuad)
                animation.start(QAbstractAnimation.DeleteWhenStopped)
            except RuntimeError:
                continue

        log.debug(
            "Toasts repositioned",
            extra={
                "operation": "toast",
                "phase": "reposition",
                "count": len(self._visible_toasts),
                "direction": "toward_edge",
            },
        )

class _ToastAnchorWatcher(QObject):
    def __init__(self, parent: QObject, *, on_changed: Callable[[], None]) -> None:
        super().__init__(parent)
        self._on_changed = on_changed

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        try:
            et = event.type()
            if et in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange, QEvent.Type.ActivationChange):
                self._on_changed()
        except Exception:
            pass
        return False


__all__ = ["ToastManager"]
