# Toast Notification System

## Objective

Implement a non-blocking, theme-aware toast notification system for DataLens that provides user feedback for info, success, warning, and error events. The system must:

- Never block the UI thread
- Support multiple simultaneous toasts with queue management
- Integrate with DataLens theming and iconography
- Be triggerable via EventHub, direct calls, and signals
- Support flexible positioning (corners, edges, center, widget-relative)
- Provide smooth fade in/out animations

## Reference Implementation

Based on [pyqttoast](https://github.com/niklashenning/pyqttoast) architecture:
- Queue-based overflow handling (max 3 visible, rest queued)
- One-time use pattern (new instance per toast)
- Preset system for common notification types
- Configurable duration with auto-dismiss
- Progress bar showing remaining time

## Animation & Stacking Behavior

### Appearance Animation (New Toast)

When a toast appears, it performs a **slide + fade** animation:

**Bottom positions** (BOTTOM_LEFT, BOTTOM_CENTER, BOTTOM_RIGHT):
1. Toast starts **below** its final position (offset: +50px Y)
2. Simultaneously:
   - Slides **up** to final position (250ms, ease-out curve)
   - Fades in from 0% to 100% opacity (250ms)

**Top positions** (TOP_LEFT, TOP_CENTER, TOP_RIGHT):
1. Toast starts **above** its final position (offset: -50px Y)
2. Simultaneously:
   - Slides **down** to final position (250ms, ease-out curve)
   - Fades in from 0% to 100% opacity (250ms)

**Center positions** (CENTER_LEFT, CENTER, CENTER_RIGHT):
1. Toast starts at final position
2. Only fades in from 0% to 100% opacity (250ms)
3. Optional: slight scale animation (0.9x to 1.0x) for pop effect

### Dismissal Animation (Closing Toast)

1. Fade out from 100% to 0% opacity (250ms)
2. No slide (stays in place)
3. After fade completes: widget deletes itself

### Stacking & Repositioning (Multiple Toasts)

**When new toast appears:**
1. New toast slides into the **nearest** position (position 0)
2. Existing toasts **smoothly slide** away from the edge:
   - Bottom positions: existing toasts slide **up** to make room
   - Top positions: existing toasts slide **down** to make room
   - Center positions: existing toasts slide **away from center**

**When toast closes:**
1. Closing toast fades out in place
2. Remaining toasts **smoothly slide** toward the edge to fill the gap:
   - Bottom positions: toasts slide **down**
   - Top positions: toasts slide **up**
   - Center positions: toasts slide **toward center**

**Example (BOTTOM_RIGHT, 3 toasts visible):**
```
Initial state (2 toasts):
                        ┌─── Toast #2 (oldest, furthest from edge)
                        │
                   10px │
                        ▼
                        ┌─── Toast #1 (middle)
                        │
                   10px │
                        ▼
                        ┌─── Toast #0 (newest, at edge)

New toast #3 appears:
1. Toast #3 slides up from below edge (starts at +50px)
2. Toast #0, #1, #2 simultaneously slide up by (toast_height + spacing)
3. Result:
                        ┌─── Toast #2 (pushed further up)
                   10px │
                        ┌─── Toast #1 (pushed up)
                   10px │
                        ┌─── Toast #0 (pushed up)
                   10px │
                        ┌─── Toast #3 (NEW, at edge)

Toast #2 closes:
1. Toast #2 fades out in place
2. Toast #0, #1, #3 slide up to fill gap
3. Result:
                        ┌─── Toast #1 (moved up)
                   10px │
                        ┌─── Toast #0 (moved up)
                   10px │
                        ┌─── Toast #3 (moved up)
```

### Stacking Limits

- **Max visible**: 3 toasts (configurable)
- **Max queued**: 10 toasts
- **Spacing**: 10px between toasts
- **Edge margin**: 20px from screen edge

When 4th toast appears while 3 are visible:
- Toast #0, #1, #2 remain visible and in place
- Toast #3 enters the queue
- Toast #3 appears when any visible toast closes

### Animation Parameters

| Animation | Duration | Curve | Property |
|-----------|----------|-------|----------|
| Slide in | 250ms | QEasingCurve.OutCubic | position (QPoint) |
| Fade in | 250ms | QEasingCurve.Linear | windowOpacity (float) |
| Slide out | 250ms | QEasingCurve.InOutCubic | position (QPoint) |
| Fade out | 250ms | QEasingCurve.Linear | windowOpacity (float) |
| Reposition | 200ms | QEasingCurve.InOutQuad | position (QPoint) |

## Logging

All toast events are logged for diagnosis and audit trail.

### Log Levels

**INFO** - User-visible toast shown:
```python
log.info(
    "Toast notification shown",
    extra={
        "operation": "toast",
        "phase": "show",
        "toast_type": "success",  # success, warning, error, info
        "title": "Export Complete",
        "message": "File saved to Desktop",
        "duration_ms": 5000,
        "position": "bottom_right",
        "trigger": "direct_call",  # direct_call, event_hub, signal
        "caller_module": "datalens.plugins.export.service",
    }
)
```

**DEBUG** - Queue and lifecycle events:
```python
# Toast queued
log.debug(
    "Toast queued (max visible reached)",
    extra={
        "operation": "toast",
        "phase": "queued",
        "queue_size": 3,
        "toast_title": "...",
    }
)

# Toast closed
log.debug(
    "Toast closed",
    extra={
        "operation": "toast",
        "phase": "closed",
        "toast_id": "...",
        "close_reason": "auto_dismiss",  # auto_dismiss, manual_close
        "visible_time_ms": 4982,
    }
)

# Toast dequeued
log.debug(
    "Toast dequeued",
    extra={
        "operation": "toast",
        "phase": "dequeued",
        "remaining_queue_size": 2,
    }
)
```

**WARNING** - Queue overflow:
```python
log.warning(
    "Toast queue full, discarding oldest",
    extra={
        "operation": "toast",
        "phase": "queue_overflow",
        "max_queue_size": 10,
        "discarded_toast_title": "...",
    }
)
```

### Trigger Tracking

Toast system tracks how each toast was triggered:

1. **Direct call**: `show_success()`, `show_warning()`, etc.
   - Caller module extracted via `inspect.stack()`

2. **EventHub**: `event_hub.publish("toast_requested", ...)`
   - Event publisher tracked in `ToastRequested.publisher_module` field

3. **Signal**: Connected via `signal.connect(toast_slot)`
   - Sender object name logged

### Audit Log Example

```
2025-12-21 14:32:01.234 | INFO  | toast | op=toast phase=show type=success | Export Complete
2025-12-21 14:32:01.235 | DEBUG | toast | op=toast phase=animation_start | Slide+fade in (250ms)
2025-12-21 14:32:01.485 | DEBUG | toast | op=toast phase=animation_complete | Visible
2025-12-21 14:32:02.100 | INFO  | toast | op=toast phase=show type=warning | Memory Low
2025-12-21 14:32:02.101 | DEBUG | toast | op=toast phase=reposition | Existing toasts sliding up
2025-12-21 14:32:06.235 | DEBUG | toast | op=toast phase=closed reason=auto_dismiss | Export Complete (5000ms)
2025-12-21 14:32:06.236 | DEBUG | toast | op=toast phase=reposition | Remaining toasts sliding down
```

## Tasks (Ordered)

### 1. Create Missing Icons

**Files**: `datalens/ui/widgets/icons/`

We need three new icons to complete the notification set:

- ✅ `warning_icon.py` - Already exists (exclamation mark in warning color circle)
- ❌ `success_icon.py` - Checkmark in confirm color circle
- ❌ `error_icon.py` - X mark in cancel color circle
- ❌ `info_icon.py` - "i" mark in primary color circle

**Design Spec** (following `iconography.md`):
- All icons: circular background with layered translucent fills
- Outer glow (alpha 0.5) + inner fill (alpha 0.6)
- Symbol in `text_color` at 95% opacity
- Use semantic colors: `confirm_color`, `cancel_color`, `warning_color`, `primary_color`
- Stroke weights: 2-3px for shapes
- Size: default 28px, scalable

### 2. Create Toast Widget (UI Layer)

**File**: `datalens/ui/widgets/notifications/toast_widget.py`

Single toast notification widget with size constraints and text eliding:

```python
class ToastWidget(QWidget):
    """
    Single toast notification (one-time use).

    Features:
    - Icon (success/warning/error/info)
    - Title + message text
    - Close button (X)
    - Optional progress bar showing remaining duration
    - Fade in/out animations (QPropertyAnimation on windowOpacity)
    - Auto-dismiss timer (QTimer)

    Lifecycle:
    1. Create instance
    2. Configure (title, text, duration, icon type)
    3. show() - starts fade-in + auto-dismiss timer
    4. Auto-hide or manual close triggers fade-out
    5. Widget deletes itself after fade-out completes
    """

    closed = Signal()  # Emitted when toast is fully hidden

    def __init__(self, parent: QWidget, theme: AppTheme):
        # Frameless window flag for modern appearance
        # WindowStaysOnTopHint to ensure visibility

    def set_title(self, title: str) -> None:
        # Elide text if exceeds available width
        # Single line only, no wrapping
        # Log warning if title was truncated
        ...

    def set_message(self, message: str) -> None:
        # Word wrap enabled, up to 4 lines
        # Elide if exceeds MAX_HEIGHT (60px)
        # Log warning if message was truncated
        ...

    def set_duration(self, milliseconds: int) -> None:
        # 0 = no auto-dismiss (manual close only)
        ...

    def set_icon_type(self, icon_type: ToastIconType) -> None:
        # SUCCESS, WARNING, ERROR, INFO
        ...

    def show(self) -> None:
        # Log toast shown (INFO level)
        # Start slide+fade-in animation (250ms)
        # Start auto-dismiss timer if duration > 0
        # Start progress bar countdown animation
        ...

    def close(self, reason: str = "manual") -> None:
        # Log toast closed (DEBUG level)
        # Start fade-out animation (250ms, no slide)
        # Emit closed signal when complete
        # Schedule deleteLater()

    def _get_start_position(self, final_pos: QPoint) -> QPoint:
        # Calculate starting position based on toast position
        # Bottom: +50px Y offset (below final position)
        # Top: -50px Y offset (above final position)
        # Center: no offset (fade only)
```

**Styling**:

Widget appearance uses AppTheme with reduced opacity for modern glass-like effect:

```python
# Background
background = theme.qcolor_with_alpha(theme.secondary_color, 0.95)  # 95% opacity

# Border (1px, varies by toast type)
border_color = {
    ToastIconType.SUCCESS: theme.qcolor_with_alpha(theme.confirm_border, 0.8),
    ToastIconType.WARNING: theme.qcolor_with_alpha(theme.warning_border, 0.8),
    ToastIconType.ERROR: theme.qcolor_with_alpha(theme.cancel_border, 0.8),
    ToastIconType.INFO: theme.qcolor_with_alpha(theme.primary_border, 0.6),
}

# Text colors
title_color = theme.qcolor_with_alpha(theme.text_color, 1.0)  # Full opacity
message_color = theme.qcolor_with_alpha(theme.text_color, 0.85)  # Slightly muted

# Corner radius
border_radius = 8px
```

**Size Constraints**:

To prevent massive toasts from large text, enforce strict size limits:

```python
# Fixed dimensions
MIN_WIDTH = 300px
MAX_WIDTH = 400px
MIN_HEIGHT = 80px
MAX_HEIGHT = 150px

# Icon
ICON_SIZE = 24px

# Padding
CONTENT_PADDING = 12px (all sides)
ICON_SPACING = 10px (between icon and text)
TEXT_SPACING = 6px (between title and message)
PROGRESS_BAR_HEIGHT = 4px
```

**Text Handling**:

Title and message must be contained within bounds using:

```python
# Title
title_label = QLabel()
title_label.setWordWrap(False)  # Single line only
title_label.setTextFormat(Qt.PlainText)  # No HTML
title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
title_label.setMaximumHeight(16)  # One line at 12px font

# Elide if too long
font_metrics = title_label.fontMetrics()
elided_title = font_metrics.elidedText(
    title,
    Qt.ElideRight,
    MAX_WIDTH - ICON_SIZE - ICON_SPACING - CLOSE_BUTTON_WIDTH - CONTENT_PADDING * 2
)
title_label.setText(elided_title)

# Message
message_label = QLabel()
message_label.setWordWrap(True)  # Multi-line allowed
message_label.setTextFormat(Qt.PlainText)  # No HTML
message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
message_label.setMaximumHeight(60)  # ~4 lines at 11px font
message_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)

# Scroll if message exceeds max height (rare, but graceful)
# Option 1: Elide with "..." at end
# Option 2: QScrollArea (adds complexity)
# Recommendation: Elide + log warning if message truncated
```

**Visual Structure**:

```
┌────────────────────────────────────────────┐ ─┬─
│  ╭────╮                                     │  │
│  │Icon│  Title (elided if long)        [×] │  │ Header: ~40px
│  ╰────╯                                     │  │
├────────────────────────────────────────────┤ ─┼─
│           Message text here, wrapped to    │  │
│           multiple lines if needed.        │  │ Message: up to 60px
│           Maximum 4 lines visible...       │  │
├────────────────────────────────────────────┤ ─┼─
│  ▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░ (progress) │  │ Progress: 4px
└────────────────────────────────────────────┘ ─┴─
 │◄─────────── 300-400px ─────────────────►│
```

**QSS Stylesheet Example**:

```python
def _build_stylesheet(self) -> str:
    bg = self._theme.qcolor_with_alpha(self._theme.secondary_color, 0.95)
    border = self._get_border_color()  # Based on icon type
    text = self._theme.text_color

    return f"""
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

    QPushButton#ToastClose {{
        background-color: transparent;
        border: none;
        color: {self._theme.with_alpha_hex(text, 0.6)};
        font-size: 16px;
        padding: 4px;
        border-radius: 4px;
    }}

    QPushButton#ToastClose:hover {{
        background-color: {self._theme.with_alpha_hex(text, 0.1)};
        color: {text};
    }}

    QProgressBar#ToastProgress {{
        background-color: {self._theme.with_alpha_hex(text, 0.1)};
        border: none;
        height: 4px;
        border-radius: 2px;
    }}

    QProgressBar#ToastProgress::chunk {{
        background-color: {self._get_progress_color().name()};
        border-radius: 2px;
    }}
    """
```

**Drop Shadow**:

```python
# Add subtle drop shadow for elevation
shadow = QGraphicsDropShadowEffect()
shadow.setBlurRadius(20)
shadow.setXOffset(0)
shadow.setYOffset(4)
shadow.setColor(QColor(0, 0, 0, 80))  # 30% black
self.setGraphicsEffect(shadow)
```

**Layout**:
```
┌─────────────────────────────────────┐
│ [Icon]  Title               [X]     │
│         Message text here...        │
│ ▓▓▓▓▓░░░░░░░░░░░░░░░░░░ (progress)  │
└─────────────────────────────────────┘

Constraints:
- Width: 300-400px (fixed, doesn't grow with text)
- Height: 80-150px (grows with content, capped at max)
- Title: Single line, elided with "..." if too long
- Message: Up to 4 lines, wrapped, elided if exceeds
- Background: 95% opacity for glass effect
- Corners: 8px radius
- Border: 1px, color varies by type
```

### 3. Create Toast Manager (Coordination Layer)

**File**: `datalens/ui/widgets/notifications/toast_manager.py`

Manages multiple toasts, positioning, and queue:

```python
class ToastPosition(Enum):
    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    CENTER_LEFT = "center_left"
    CENTER = "center"
    CENTER_RIGHT = "center_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"

class ToastIconType(Enum):
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"

class ToastManager:
    """
    Singleton managing toast lifecycle, positioning, and queuing.

    Features:
    - Max visible toasts (default 3)
    - Queue for overflow
    - Dynamic repositioning as toasts close
    - Screen-relative or widget-relative positioning
    - Thread-safe enqueue from any thread (via Qt signals)

    Non-blocking guarantee:
    - show_toast() returns immediately
    - Toast creation deferred to UI thread via QTimer.singleShot(0, ...)
    - No blocking operations
    """

    _instance: ToastManager | None = None

    @classmethod
    def instance(cls, parent: QWidget | None = None) -> ToastManager:
        # Lazy singleton

    def __init__(self, parent: QWidget):
        self._parent = parent  # Main window for screen positioning
        self._theme: AppTheme = ...
        self._position = ToastPosition.BOTTOM_RIGHT
        self._max_visible = 3
        self._spacing = 10  # Pixels between toasts
        self._margin = 20   # Edge margin
        self._visible_toasts: list[ToastWidget] = []
        self._queued_toasts: deque[dict] = deque()

    def set_position(self, position: ToastPosition) -> None:
        ...

    def set_max_visible(self, count: int) -> None:
        ...

    def show_toast(
        self,
        title: str,
        message: str = "",
        icon_type: ToastIconType = ToastIconType.INFO,
        duration: int = 5000,
        trigger: str = "direct_call",
        caller_module: str | None = None,
    ) -> None:
        """
        Show a toast notification (non-blocking).

        Args:
            title: Toast title
            message: Optional message text
            icon_type: Type of notification
            duration: Auto-dismiss time in ms (0 = manual close only)
            trigger: How toast was triggered (direct_call, event_hub, signal)
            caller_module: Module that triggered the toast (for logging)

        Thread-safe: Can be called from any thread.
        Returns immediately (toast creation deferred to UI thread).
        Logs at INFO level when shown.
        """
        # Extract caller module if not provided (using inspect.stack())
        # Log toast request (INFO level)
        # Queue toast parameters
        # Use QTimer.singleShot(0, ...) to defer to UI thread
        # If under max_visible: create and position immediately
        # If at max: add to queue (log DEBUG)
        # If queue full: discard oldest and log WARNING

    def _create_toast(self, params: dict) -> ToastWidget:
        # Create widget
        # Connect closed signal to _on_toast_closed
        # Calculate final position
        # Calculate start position (based on stack direction)
        # Set widget to start position (invisible)
        # Call show() which triggers slide+fade animation
        # Log animation start (DEBUG)

    def _on_toast_closed(self, toast: ToastWidget) -> None:
        # Remove from visible list
        # Log toast closed (DEBUG)
        # Reposition remaining toasts (smooth slide animation)
        # If queue not empty:
        #   - Dequeue next toast (log DEBUG)
        #   - Show it with slide+fade animation

    def _reposition_toasts(self) -> None:
        # Calculate new positions for all visible toasts
        # Create QPropertyAnimation for each toast's position
        # Duration: 200ms, curve: InOutQuad
        # Start all animations simultaneously (smooth stacking)
        # Log repositioning (DEBUG)

    def _calculate_position(self, index: int, is_start_position: bool = False) -> QPoint:
        # Based on self._position and parent geometry
        # Stack vertically with self._spacing
        # Index 0 = nearest to edge, index N = furthest from edge
        #
        # if is_start_position:
        #   Bottom positions: add +50px Y offset (below final)
        #   Top positions: add -50px Y offset (above final)
        #   Center positions: same as final position
        # else:
        #   Return final position for this index in the stack
```

### 4. Create Convenience API (Service Layer)

**File**: `datalens/services/notifications/toast_service.py`

Convenience functions for common toast patterns:

```python
def show_success(title: str, message: str = "", duration: int = 5000) -> None:
    """Show a success toast (green checkmark)."""
    ToastManager.instance().show_toast(
        title=title,
        message=message,
        icon_type=ToastIconType.SUCCESS,
        duration=duration,
    )

def show_warning(title: str, message: str = "", duration: int = 5000) -> None:
    """Show a warning toast (yellow exclamation)."""
    ToastManager.instance().show_toast(
        title=title,
        message=message,
        icon_type=ToastIconType.WARNING,
        duration=duration,
    )

def show_error(title: str, message: str = "", duration: int = 0) -> None:
    """Show an error toast (red X). Defaults to manual dismiss."""
    ToastManager.instance().show_toast(
        title=title,
        message=message,
        icon_type=ToastIconType.ERROR,
        duration=duration,
    )

def show_info(title: str, message: str = "", duration: int = 5000) -> None:
    """Show an info toast (blue i)."""
    ToastManager.instance().show_toast(
        title=title,
        message=message,
        icon_type=ToastIconType.INFO,
        duration=duration,
    )
```

### 5. EventHub Integration

**File**: Add to `datalens/core/events.py`

New event types for toast notifications:

```python
@dataclass(frozen=True)
class ToastRequested:
    """Request to show a toast notification."""
    title: str
    message: str = ""
    icon_type: str = "info"  # success, warning, error, info
    duration: int = 5000
    timestamp_s: float = field(default_factory=time.time)
```

**Usage from any component**:
```python
# Publish toast request (non-blocking)
event_hub.publish(
    "toast_requested",
    ToastRequested(
        title="Export Complete",
        message="File saved to Desktop",
        icon_type="success",
    )
)
```

**Main window subscribes**:
```python
# In main_window.py __init__
self._event_hub.subscribe(
    "toast_requested",
    self._on_toast_requested,
)

def _on_toast_requested(self, event: ToastRequested) -> None:
    icon_map = {
        "success": ToastIconType.SUCCESS,
        "warning": ToastIconType.WARNING,
        "error": ToastIconType.ERROR,
        "info": ToastIconType.INFO,
    }
    ToastManager.instance().show_toast(
        title=event.title,
        message=event.message,
        icon_type=icon_map.get(event.icon_type, ToastIconType.INFO),
        duration=event.duration,
    )
```

### 6. Add Demo to Widget Test Plugin

**File**: `datalens/plugins/widget_test/ui/sections/toast_demo.py`

Demo section showing:
- Buttons to trigger each toast type
- Position selector dropdown
- Duration slider
- Custom title/message inputs
- "Spam 10 toasts" button to test queue

## Correctness Criteria

1. **Non-blocking**: `show_toast()` returns immediately; widget creation deferred to UI thread
2. **Thread-safe**: Can call from background threads without crashes
3. **Queue management**: Overflow toasts wait in queue, shown as space becomes available
4. **Clean lifecycle**: Widgets delete themselves after fade-out; no memory leaks
5. **Position accuracy**: Toasts appear at correct screen/widget positions
6. **Animation smoothness**: Fade in/out and repositioning animations are smooth (60fps)
7. **Theme integration**: All colors derive from AppTheme; updates on theme change
8. **Icon consistency**: Icons follow iconography.md guidelines
9. **Accessibility**: Toasts stay on top; text is readable; close button is accessible
10. **Size constraints**: Toasts never exceed MAX_WIDTH/MAX_HEIGHT regardless of text length
11. **Text eliding**: Long titles/messages gracefully truncated with "..." indicator
12. **Opacity styling**: Background uses 95% opacity for modern glass effect; rounded corners

## Failure Modes

1. **Queue overflow**: If queue grows unbounded (e.g., spam from loop)
   - **Mitigation**: Max queue size (default 10); oldest discarded
   - **Log**: Warning when queue limit reached

2. **Parent widget destroyed**: ToastManager holds reference to deleted parent
   - **Mitigation**: Use QPointer or weak reference; check validity before positioning
   - **Fallback**: Position relative to primary screen if parent invalid

3. **Theme change during animation**: Colors update mid-animation
   - **Accept**: Toasts use theme at creation time; future toasts use new theme
   - **Future**: Subscribe to theme change event and update visible toasts

4. **Concurrent show_toast() from multiple threads**: Race conditions
   - **Mitigation**: All widget creation happens on UI thread via QTimer.singleShot
   - **Queue protected**: Use thread-safe deque or lock

## Performance Constraints

1. **UI thread**: Toast creation, positioning, animation setup must be < 16ms
2. **Animation**: 60fps during fade in/out and repositioning
3. **Memory**: Each toast ~1KB; max 13 instances (3 visible + 10 queued) = ~13KB
4. **CPU**: Minimal; Qt handles animation timing

## Validation Steps

1. **Manual testing**:
   - Trigger each toast type
   - Test all 9 positions
   - Spam toasts to verify queue
   - Close toasts manually
   - Test from background thread

2. **Visual verification**:
   - Icons render correctly
   - Theme colors match design
   - Animations are smooth
   - Text is readable

3. **Code checks**:
   - `python -m compileall -q datalens/ui/widgets/notifications`
   - `python -m compileall -q datalens/services/notifications`
   - Import test: `from datalens.services.notifications import show_success`

4. **Integration test**:
   - Add to widget_test plugin
   - Verify EventHub integration
   - Test theme switching while toasts visible

## API Summary

### Direct Calls (Recommended)
```python
from datalens.services.notifications import show_success, show_warning, show_error, show_info

show_success("Task Complete", "All files processed successfully")
show_warning("Memory Low", "Consider closing unused projects")
show_error("Export Failed", "Insufficient disk space")
show_info("Update Available", "Version 2.1 is ready to install")
```

### EventHub (Decoupled)
```python
event_hub.publish("toast_requested", ToastRequested(
    title="Capture Started",
    message="Recording to project database",
    icon_type="success",
))
```

### Direct Manager (Advanced)
```python
from datalens.ui.widgets.notifications import ToastManager, ToastIconType, ToastPosition

manager = ToastManager.instance()
manager.set_position(ToastPosition.TOP_RIGHT)
manager.set_max_visible(5)
manager.show_toast("Custom Toast", icon_type=ToastIconType.WARNING, duration=10000)
```

## File Structure

```
datalens/
├── ui/
│   ├── widgets/
│   │   ├── icons/
│   │   │   ├── success_icon.py          # NEW: Checkmark icon
│   │   │   ├── error_icon.py            # NEW: X mark icon
│   │   │   ├── info_icon.py             # NEW: Information icon
│   │   │   └── warning_icon.py          # EXISTS: Exclamation icon
│   │   └── notifications/               # NEW PACKAGE
│   │       ├── __init__.py
│   │       ├── toast_widget.py          # Single toast UI
│   │       └── toast_manager.py         # Multi-toast coordination
├── services/
│   └── notifications/                   # NEW PACKAGE
│       ├── __init__.py
│       └── toast_service.py             # Convenience API
├── core/
│   └── events.py                        # ADD: ToastRequested event
└── plugins/
    └── widget_test/
        └── ui/
            └── sections/
                └── toast_demo.py        # NEW: Demo section
```

## Dependencies

- **Qt**: QWidget, QLabel, QTimer, QPropertyAnimation, QGraphicsOpacityEffect
- **Existing**: AppTheme, warning_icon
- **New icons**: success_icon, error_icon, info_icon

## Notes

- Toast positioning uses parent widget geometry (main window) for screen-relative positions
- Widget-relative positioning (future enhancement): pass target widget to show_toast()
- Progress bar is optional (can be disabled per toast or globally)
- Toasts are frameless top-level windows (not child widgets) for proper stacking
- All animations use Qt's animation framework (non-blocking)
- Theme integration: ToastManager subscribes to theme changes to update future toasts

## Future Enhancements

1. **Click-through actions**: Toasts can contain action buttons (e.g., "Undo", "View")
2. **Rich text**: Support for formatted messages with links
3. **Widget-relative positioning**: Position relative to specific UI elements
4. **Sound effects**: Optional audio cues for different toast types
5. **Persistence**: Option to log toasts to a notification center/history panel
6. **Grouping**: Collapse multiple similar toasts into a single expandable toast
