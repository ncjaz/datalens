from __future__ import annotations

"""
Single toast notification widget (one-time use).

Features:
- Icon (success/warning/error/info)
- Title (single line, elided if too long)
- Message (multi-line, max 4 lines)
- Close button (IconButton with X)
- Progress bar showing remaining time
- Size constraints (300-400px width, 80-150px height)
- Slide + fade animations
- 95% opacity background with rounded corners
- Non-blocking, self-deleting after fade-out
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.icon_button import create_icon_button
from datalens.ui.widgets.icons import error_icon, info_icon, success_icon, warning_icon
from datalens.ui.widgets.notifications.toast_types import ToastIconType

if TYPE_CHECKING:
    from PySide6.QtGui import QIcon

log = logging.getLogger(__name__)

# Size constraints (prevents massive toasts from large text)
MIN_WIDTH = 300
MAX_WIDTH = 400
MIN_HEIGHT = 80
MAX_HEIGHT = 150

# Icon and spacing
ICON_SIZE = 24
CONTENT_PADDING = 12
ICON_SPACING = 10
TEXT_SPACING = 6
PROGRESS_BAR_HEIGHT = 4
CLOSE_BUTTON_SIZE = 24

# Animation parameters
SLIDE_OFFSET = 50  # pixels to slide from/to
ANIMATION_DURATION = 250  # milliseconds


class ToastWidget(QWidget):
    """
    Single toast notification widget.

    This is a one-time use widget that displays a notification with:
    - Themed icon based on toast type
    - Title and optional message
    - Progress bar showing remaining time
    - Close button
    - Smooth slide + fade animations

    The widget deletes itself after fade-out completes.
    """

    closed = Signal()  # Emitted when toast fade-out completes

    def __init__(
        self,
        parent: QWidget,
        theme: AppTheme,
        *,
        icon_type: ToastIconType = ToastIconType.INFO,
        toast_id: str | None = None,
    ) -> None:
        super().__init__(parent)

        self._theme = theme
        self._icon_type = icon_type
        self._toast_id = toast_id or f"toast_{id(self)}"
        self._duration = 5000  # Default 5 seconds
        self._title_text = ""
        self._message_text = ""

        # Animation state
        self._slide_animation: QPropertyAnimation | None = None
        self._fade_animation: QPropertyAnimation | None = None
        self._dismiss_timer: QTimer | None = None
        self._progress_timer: QTimer | None = None
        self._remaining_time = 0  # milliseconds
        self._suppressed = False
        self._suppressed_reason: str | None = None

        # Window flags for overlay appearance
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        # Size constraints
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.setMaximumSize(MAX_WIDTH, MAX_HEIGHT)

        # Build UI
        self._build_ui()

        # Apply drop shadow for elevation
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 80))  # 30% black
        self.setGraphicsEffect(shadow)

    @property
    def toast_id(self) -> str:
        return self._toast_id

    @property
    def icon_type(self) -> ToastIconType:
        return self._icon_type

    @property
    def is_suppressed(self) -> bool:
        return bool(self._suppressed)

    def _build_ui(self) -> None:
        """Build the toast widget UI."""
        # Main container with styled background
        container = QWidget(self)
        container.setObjectName("ToastWidget")
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(container)

        # Content layout
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(CONTENT_PADDING, CONTENT_PADDING, CONTENT_PADDING, CONTENT_PADDING)
        content_layout.setSpacing(TEXT_SPACING)

        # Header row: icon + title + close button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(ICON_SPACING)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # Icon
        self._icon_label = QLabel(container)
        self._icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        self._icon_label.setScaledContents(True)
        self._icon_label.setPixmap(self._get_icon_for_type().pixmap(QSize(ICON_SIZE, ICON_SIZE)))
        header_layout.addWidget(self._icon_label)

        # Title
        self._title_label = QLabel(container)
        self._title_label.setObjectName("ToastTitle")
        self._title_label.setWordWrap(False)
        self._title_label.setTextFormat(Qt.PlainText)
        self._title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._title_label.setMaximumHeight(16)  # One line at 12px font
        header_layout.addWidget(self._title_label)

        # Close button (IconButton)
        self._close_button = create_icon_button(
            self._theme,
            container,
            size=CLOSE_BUTTON_SIZE,
            icon_size=12,
            checkable=False,
        )
        self._close_button.setObjectName("ToastClose")
        self._close_button.setText("✕")  # X mark for close
        self._close_button.clicked.connect(lambda: self.close_toast("manual_close"))
        header_layout.addWidget(self._close_button)

        content_layout.addLayout(header_layout)

        # Message
        self._message_label = QLabel(container)
        self._message_label.setObjectName("ToastMessage")
        self._message_label.setWordWrap(True)
        self._message_label.setTextFormat(Qt.PlainText)
        self._message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._message_label.setMaximumHeight(60)  # ~4 lines at 11px font
        self._message_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        content_layout.addWidget(self._message_label)

        # Progress bar
        self._progress_bar = QProgressBar(container)
        self._progress_bar.setObjectName("ToastProgress")
        self._progress_bar.setFixedHeight(PROGRESS_BAR_HEIGHT)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(100)
        content_layout.addWidget(self._progress_bar)

        # Apply stylesheet
        self._apply_stylesheet()

    def _get_icon_for_type(self) -> QIcon:
        """Get the appropriate icon for the toast type."""
        icon_map = {
            ToastIconType.SUCCESS: success_icon,
            ToastIconType.WARNING: warning_icon,
            ToastIconType.ERROR: error_icon,
            ToastIconType.INFO: info_icon,
        }
        icon_func = icon_map.get(self._icon_type, info_icon)
        return icon_func(self._theme, size=ICON_SIZE)

    def _get_progress_color(self) -> QColor:
        """Get the progress bar color based on toast type."""
        color_map = {
            ToastIconType.SUCCESS: self._theme.confirm_color,
            ToastIconType.WARNING: self._theme.warning_color,
            ToastIconType.ERROR: self._theme.cancel_color,
            ToastIconType.INFO: self._theme.primary_color,
        }
        return self._theme.qcolor(color_map.get(self._icon_type, self._theme.primary_color))

    def _apply_stylesheet(self) -> None:
        """Apply theme-aware stylesheet."""
        bg = self._theme.qcolor_with_alpha(self._theme.secondary_color, 0.95)
        border = self._theme.qcolor_with_alpha(self._theme.secondary_border, 0.6)
        text = self._theme.text_color

        progress_color = self._get_progress_color()

        stylesheet = f"""
        QWidget#ToastWidget {{
            background-color: {bg.name()};
            border: 1px solid {border.name()};
            border-radius: 8px;
        }}

        QLabel#ToastTitle {{
            color: {text};
            font-size: 12px;
            font-weight: bold;
            padding: 0px;
        }}

        QLabel#ToastMessage {{
            color: {self._theme.with_alpha_hex(text, 0.85)};
            font-size: 11px;
            padding: 0px;
        }}

        QProgressBar#ToastProgress {{
            background-color: {self._theme.with_alpha_hex(text, 0.1)};
            border: none;
            border-radius: 2px;
        }}

        QProgressBar#ToastProgress::chunk {{
            background-color: {progress_color.name()};
            border-radius: 2px;
        }}
        """
        self.setStyleSheet(stylesheet)

    def set_title(self, title: str) -> None:
        """
        Set the toast title (single line, elided if too long).

        Args:
            title: Title text to display
        """
        self._title_text = title

        # Calculate available width for title
        available_width = MAX_WIDTH - ICON_SIZE - ICON_SPACING - CLOSE_BUTTON_SIZE - CONTENT_PADDING * 2 - 10

        # Elide text if too long
        font_metrics = self._title_label.fontMetrics()
        elided_title = font_metrics.elidedText(title, Qt.ElideRight, available_width)

        self._title_label.setText(elided_title)

        # Log warning if title was truncated
        if elided_title != title:
            log.warning(
                "Toast title truncated (too long)",
                extra={
                    "operation": "toast",
                    "phase": "set_title",
                    "toast_id": self._toast_id,
                    "original_length": len(title),
                    "truncated_length": len(elided_title),
                },
            )

    def set_message(self, message: str) -> None:
        """
        Set the toast message (multi-line, max 4 lines).

        Args:
            message: Message text to display
        """
        self._message_text = message
        self._message_label.setText(message)

        # Check if message was truncated (height exceeds max)
        # Note: Qt will automatically elide based on setMaximumHeight()
        if message:
            text_height = self._message_label.sizeHint().height()
            if text_height > 60:
                log.warning(
                    "Toast message may be truncated (too long)",
                    extra={
                        "operation": "toast",
                        "phase": "set_message",
                        "toast_id": self._toast_id,
                        "message_length": len(message),
                        "text_height": text_height,
                    },
                )

    def set_duration(self, milliseconds: int) -> None:
        """
        Set auto-dismiss duration.

        Args:
            milliseconds: Duration in ms (0 = no auto-dismiss)
        """
        self._duration = milliseconds
        self._remaining_time = milliseconds

    def set_suppressed(self, suppressed: bool, *, reason: str) -> None:
        """
        Temporarily hide or show the toast.

        This is used to implement "follow main window" behavior when the user
        disables showing toasts while the main window is minimized or inactive.
        """
        if suppressed:
            if self._suppressed:
                return
            self._suppressed = True
            self._suppressed_reason = reason

            if self._fade_animation:
                try:
                    self._fade_animation.stop()
                except Exception:
                    pass

            try:
                QWidget.hide(self)
            except Exception:
                pass

            log.debug(
                "Toast suppressed",
                extra={
                    "operation": "toast",
                    "phase": "suppressed",
                    "toast_id": self._toast_id,
                    "reason": reason,
                    "remaining_ms": self._remaining_time,
                },
            )
            return

        if not self._suppressed:
            return
        self._suppressed = False
        self._suppressed_reason = None

        if self._duration > 0 and self._remaining_time <= 0:
            self.close_toast("auto_dismiss")
            return

        try:
            QWidget.show(self)
            self.setWindowOpacity(1.0)
            self.raise_()
        except Exception:
            pass

        self._sync_progress_bar()

        log.debug(
            "Toast unsuppressed",
            extra={
                "operation": "toast",
                "phase": "unsuppressed",
                "toast_id": self._toast_id,
                "reason": reason,
                "remaining_ms": self._remaining_time,
            },
        )

    def _sync_progress_bar(self) -> None:
        if self._duration <= 0:
            self._progress_bar.setValue(0)
            return
        remaining = max(0, int(self._remaining_time))
        duration = max(1, int(self._duration))
        progress = int((remaining / duration) * 100)
        self._progress_bar.setValue(max(0, min(100, progress)))

    def _start_or_restart_timers(self) -> None:
        if self._dismiss_timer:
            self._dismiss_timer.stop()
        if self._progress_timer:
            self._progress_timer.stop()

        if self._duration <= 0:
            return
        if self._remaining_time <= 0:
            self.close_toast("auto_dismiss")
            return

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(lambda: self.close_toast("auto_dismiss"))
        self._dismiss_timer.start(int(self._remaining_time))
        self._start_progress_countdown()

    def show(self) -> None:
        """Show the toast with slide + fade animation."""
        if self._suppressed:
            return
        log.info(
            "Toast notification shown",
            extra={
                "operation": "toast",
                "phase": "show",
                "toast_type": self._icon_type.value,
                "title": self._title_text,
                # Avoid LogRecord reserved key "message" (would raise KeyError).
                "toast_message": self._message_text[:100] if self._message_text else "",
                "duration_ms": self._duration,
                "toast_id": self._toast_id,
            },
        )

        # Show widget (initially invisible)
        self.setWindowOpacity(0.0)
        super().show()

        # Start fade-in animation
        self._fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self._fade_animation.setDuration(ANIMATION_DURATION)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Linear)
        self._fade_animation.start()

        log.debug(
            "Toast animation started",
            extra={
                "operation": "toast",
                "phase": "animation_start",
                "toast_id": self._toast_id,
                "animation_type": "fade_in",
            },
        )

        if self._duration > 0 and self._remaining_time <= 0:
            self._remaining_time = int(self._duration)
        self._sync_progress_bar()
        self._start_or_restart_timers()

    def _start_progress_countdown(self) -> None:
        """Start the progress bar countdown animation."""
        # Update progress every 50ms
        update_interval = 50

        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._update_progress)
        self._progress_timer.start(update_interval)

    def _update_progress(self) -> None:
        """Update the progress bar based on remaining time."""
        if self._remaining_time <= 0:
            if self._progress_timer:
                self._progress_timer.stop()
            self._progress_bar.setValue(0)
            return

        # Decrease remaining time
        self._remaining_time -= 50

        # Calculate progress percentage
        progress = int((self._remaining_time / self._duration) * 100)
        self._progress_bar.setValue(max(0, progress))

    def close_toast(self, reason: str = "manual") -> None:
        """
        Close the toast with fade-out animation.

        Args:
            reason: Reason for closing (auto_dismiss, manual_close, etc.)
        """
        # Stop timers
        if self._dismiss_timer:
            self._dismiss_timer.stop()
        if self._progress_timer:
            self._progress_timer.stop()

        log.debug(
            "Toast closed",
            extra={
                "operation": "toast",
                "phase": "closed",
                "toast_id": self._toast_id,
                "close_reason": reason,
            },
        )

        # Start fade-out animation
        self._fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self._fade_animation.setDuration(ANIMATION_DURATION)
        self._fade_animation.setStartValue(self.windowOpacity())
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Linear)
        self._fade_animation.finished.connect(self._on_fade_out_complete)
        self._fade_animation.start()

    def _on_fade_out_complete(self) -> None:
        """Handle fade-out animation completion."""
        self.closed.emit()
        self.deleteLater()

        log.debug(
            "Toast animation complete",
            extra={
                "operation": "toast",
                "phase": "animation_complete",
                "toast_id": self._toast_id,
                "animation_type": "fade_out",
            },
        )


__all__ = ["ToastWidget"]
