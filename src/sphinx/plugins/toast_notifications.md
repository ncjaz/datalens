# Toast Notifications

Toast notifications are lightweight, non-blocking pop-up messages that provide feedback to users without interrupting their workflow. DataLens provides a comprehensive toast notification system with automatic positioning, queueing, and animations.

## Overview

The toast notification system consists of several components:

- **ToastWidget**: Individual toast notification widget with animations
- **ToastManager**: Singleton manager that handles positioning, queuing, and lifecycle
- **Toast Service**: Convenience API functions (`show_success`, `show_warning`, `show_error`, `show_info`)
- **ToastTypes**: Enums and dataclasses for toast configuration

## Key Features

### Non-Blocking Operation

Toast notifications are **completely non-blocking**. Calling `show_toast()` returns immediately, and the toast is created asynchronously on the UI thread using `QTimer.singleShot(0, ...)`. This ensures:

- No performance impact on the calling code
- Safe to call from any thread
- No UI freezing

### Singleton Pattern

The `ToastManager` uses a singleton pattern to ensure consistent behavior across the entire application:

```python
from datalens.ui.widgets.notifications.toast_manager import ToastManager

# First call requires parent and theme
manager = ToastManager.get_instance(parent=main_window, theme=app_theme)

# Subsequent calls can omit parameters
manager = ToastManager.get_instance()
```

The singleton is automatically initialized when the main window is created, so plugins can access it without worrying about initialization.

### Queue Management

The system automatically manages toast overflow:

- **Maximum visible toasts**: 3 toasts on screen at once
- **Maximum queued toasts**: Up to 10 toasts can be queued
- **Eviction policy**: When at capacity, the oldest visible toast is removed to show new ones
- **Overflow handling**: If the queue is full, the oldest queued toast is discarded

### Positioning

Toasts can be positioned at 9 locations on the screen:

```python
from datalens.ui.widgets.notifications.toast_types import ToastPosition

ToastPosition.TOP_LEFT       # Top-left corner
ToastPosition.TOP_CENTER     # Top edge, centered
ToastPosition.TOP_RIGHT      # Top-right corner
ToastPosition.CENTER_LEFT    # Left edge, centered
ToastPosition.CENTER         # Screen center
ToastPosition.CENTER_RIGHT   # Right edge, centered
ToastPosition.BOTTOM_LEFT    # Bottom-left corner
ToastPosition.BOTTOM_CENTER  # Bottom edge, centered
ToastPosition.BOTTOM_RIGHT   # Bottom-right corner (default)
```

### Animations

Each toast features smooth animations:

1. **Slide in**: Toast slides from the edge (50px offset) to its final position
2. **Fade in**: Opacity transitions from 0% to 100% over 250ms
3. **Fade out**: When dismissed, opacity transitions to 0% over 250ms
4. **Stack repositioning**: When toasts are added/removed, existing toasts smoothly reposition

### Size Constraints

Toasts have enforced size constraints to prevent massive notifications:

- **Width**: 300px (min) to 400px (max)
- **Height**: 80px (min) to 150px (max)
- **Title**: Single line, elided with "..." if too long
- **Message**: Maximum 4 lines (~60px), word-wrapped

If text exceeds these constraints, it's automatically truncated and a warning is logged.

## How to Use

### Simple API (Recommended)

For most use cases, use the convenience functions:

```python
from datalens.services.notifications.toast_service import (
    show_success,
    show_warning,
    show_error,
    show_info,
)

# Success notification (green checkmark icon)
show_success("Export Complete", "File saved to Desktop/export.csv")

# Warning notification (yellow warning icon, 7s duration)
show_warning("Memory Low", "Consider closing unused projects")

# Error notification (red X icon, 10s duration)
show_error("Export Failed", "Disk full or permission denied")

# Info notification (blue info icon)
show_info("Processing Started", "This may take a few minutes")
```

### Advanced API

For advanced use cases, use the `ToastManager` directly:

```python
from datalens.ui.widgets.notifications.toast_manager import ToastManager
from datalens.ui.widgets.notifications.toast_types import ToastIconType, ToastPosition

manager = ToastManager.get_instance()

manager.show_toast(
    title="Custom Toast",
    message="This is a custom toast with specific settings",
    icon_type=ToastIconType.SUCCESS,
    duration=8000,  # 8 seconds (0 = manual close only)
    position=ToastPosition.TOP_RIGHT,
    trigger="direct_call",  # For logging purposes
)
```

### From Plugins

Plugins can show toasts using either the simple or advanced API:

```python
# In your plugin code
from datalens.services.notifications.toast_service import show_success

class MyPlugin:
    def on_export_complete(self, filename: str):
        show_success(
            "Export Complete",
            f"File saved to {filename}",
            duration=5000,
        )
```

No initialization required - the `ToastManager` singleton is already set up by the main application.

## How It Works Internally

### Lifecycle of a Toast

1. **Request**: User calls `show_success()` or `manager.show_toast()`
2. **Logging**: Request is logged with caller module, toast type, and trigger
3. **Deferred creation**: `QTimer.singleShot(0, ...)` schedules toast creation on UI thread
4. **Queue check**: If at capacity (3 visible), oldest toast is evicted or new toast is queued
5. **Widget creation**: `ToastWidget` is instantiated with theme and content
6. **Positioning**: Manager calculates position based on existing toasts and window size
7. **Animation**: Toast slides in from edge while fading in (250ms)
8. **Display**: Toast is visible for `duration` milliseconds
9. **Dismissal**: Auto-dismiss timer fires OR user clicks close button
10. **Fade out**: Toast fades out (250ms)
11. **Cleanup**: Widget emits `closed` signal and deletes itself
12. **Reposition**: Remaining toasts smoothly reposition to fill gap
13. **Queue flush**: If toasts are queued, show next one

### Thread Safety

The toast system is thread-safe:

- `show_toast()` can be called from any thread
- All widget operations are deferred to the UI thread via `QTimer.singleShot(0, ...)`
- Queue operations use `collections.deque` which is thread-safe for basic operations

### Window Following

Toasts automatically follow their parent window:

- **Window move**: Toasts reposition immediately (no animation) to stay attached
- **Window resize**: Toast stack recalculates positions
- **Window minimize**: Toasts can be configured to hide when window is minimized
- **Window inactive**: Toasts can be configured to hide when window is inactive

This is implemented using an event filter (`_ToastAnchorWatcher`) on the top-level window.

### Memory Management

Toasts are self-cleaning:

- Each `ToastWidget` has `Qt.WA_DeleteOnClose` set
- After fade-out animation completes, widget calls `self.deleteLater()`
- Manager removes toast from `_visible_toasts` list
- No manual cleanup required

### Testing Behavior

In automated tests, toast durations are automatically shortened:

```python
# Detects testing environment via:
# - DATALENS_TESTING=1 environment variable
# - PYTEST_CURRENT_TEST environment variable

# In tests, durations are clamped:
# - If duration == 0 (manual close): becomes 250ms
# - If duration > 0: min(duration, 750ms)
```

This prevents toasts from outliving the workspace during test teardown.

## Visual Appearance

### Theme Integration

Toasts use the application theme:

- **Background**: `secondary_color` at 95% opacity with rounded corners
- **Border**: `secondary_border` at 60% opacity
- **Title**: Bold, 12px, `text_color`
- **Message**: Regular, 11px, `text_color` at 85% opacity
- **Progress bar**: Color matches toast type (confirm/warning/cancel/primary)

### Icons

Each toast type has a themed icon:

| Type    | Icon                     | Color           | Default Duration |
|---------|--------------------------|-----------------|------------------|
| Success | Checkmark in circle      | confirm_color   | 5 seconds        |
| Warning | Exclamation in triangle  | warning_color   | 7 seconds        |
| Error   | X in circle              | cancel_color    | 10 seconds       |
| Info    | 'i' in circle            | primary_color   | 5 seconds        |

Icons follow the [iconography guidelines](iconography.md) with 24×24px size.

### Components

Each toast contains:

1. **Icon**: 24×24px themed icon on the left
2. **Title**: Single-line bold text, elided if too long
3. **Message**: Multi-line text (max 4 lines), word-wrapped
4. **Close button**: Icon button with "✕" symbol on the right
5. **Progress bar**: 4px high bar at bottom showing remaining time

### Drop Shadow

Toasts have a subtle drop shadow for elevation:

- Blur radius: 20px
- Offset: (0px, 4px) - shadow below toast
- Color: Black at 30% opacity

## Logging

The toast system provides comprehensive logging for diagnosis:

### Request Logging

When a toast is requested:

```
INFO | Toast request received | operation=toast phase=request toast_type=success
     title="Export Complete" toast_message="File saved to Desktop" duration_ms=5000
     position=bottom_right trigger=direct_call caller_module=my_plugin
```

### Lifecycle Logging

```
DEBUG | Toast created and shown | operation=toast phase=created toast_id=toast_0_12345
      visible_count=1

INFO  | Toast notification shown | operation=toast phase=show toast_type=success
      title="Export Complete" toast_message="File saved to Desktop" duration_ms=5000

DEBUG | Toast animation started | operation=toast phase=animation_start animation_type=fade_in

DEBUG | Toast closed | operation=toast phase=closed toast_id=toast_0_12345
      close_reason=auto_dismiss

DEBUG | Toast removed from visible list | operation=toast phase=removed
      toast_id=toast_0_12345 remaining_visible=0
```

### Queue Logging

```
DEBUG | Toast queued | operation=toast phase=queued queue_size=1 toast_title="..."

WARNING | Toast queue full, discarding oldest queued toast | operation=toast
        phase=queue_overflow max_queue_size=10 discarded_toast_title="..."
```

### Error Logging

```
WARNING | Toast title truncated (too long) | operation=toast phase=set_title
        toast_id=toast_0_12345 original_length=150 truncated_length=80

WARNING | ToastManager parent is no longer valid; dropping toast request |
        operation=toast phase=dropped toast_title="..."
```

All logging uses structured `extra={}` dicts for machine-readable log analysis.

## Common Patterns

### Success Feedback

```python
from datalens.services.notifications.toast_service import show_success

def save_file(filepath: str):
    # ... save logic ...
    show_success(
        "File Saved",
        f"Saved to {filepath}",
    )
```

### Error Handling

```python
from datalens.services.notifications.toast_service import show_error

def export_data():
    try:
        # ... export logic ...
        show_success("Export Complete")
    except Exception as e:
        show_error(
            "Export Failed",
            str(e),
            duration=10000,  # Longer duration for errors
        )
```

### Long-Running Operations

```python
from datalens.services.notifications.toast_service import show_info, show_success

def process_large_dataset():
    show_info("Processing Started", "This may take a few minutes")

    # ... processing ...

    show_success("Processing Complete", "Processed 10,000 rows")
```

### Manual Dismissal

```python
from datalens.ui.widgets.notifications.toast_manager import ToastManager
from datalens.ui.widgets.notifications.toast_types import ToastIconType

manager = ToastManager.get_instance()

# duration=0 means user must manually close the toast
manager.show_toast(
    title="Important Notice",
    message="Please read this carefully before continuing",
    icon_type=ToastIconType.WARNING,
    duration=0,  # No auto-dismiss
)
```

## Best Practices

### When to Use Toasts

✅ **Good uses:**
- Operation completion feedback ("File saved", "Export complete")
- Non-critical warnings ("Memory low", "Slow network detected")
- Background process notifications ("Sync started", "Update available")
- Success confirmations ("Settings saved", "Preferences updated")

❌ **Avoid toasts for:**
- Critical errors that require user action (use a dialog instead)
- Information that must be acknowledged (use a dialog instead)
- Long messages (>100 characters) - users may not read them in time
- High-frequency events (use status bar instead)

### Message Length

Keep messages concise:

- **Title**: 1-5 words (e.g., "Export Complete", "File Saved")
- **Message**: 1-2 sentences (e.g., "Saved to Desktop/export.csv")

Long messages are automatically truncated, and users may not have time to read them before the toast auto-dismisses.

### Duration Guidelines

- **Success**: 5 seconds (default) - Quick acknowledgment
- **Info**: 5 seconds (default) - Brief information
- **Warning**: 7 seconds (default) - Extra time to notice
- **Error**: 10 seconds (default) - More time to read details
- **Manual**: 0 (user must close) - For critical information

### Positioning

The default position is `BOTTOM_RIGHT`, which works well for most use cases:

- Doesn't obscure main content area
- Conventional location for notifications
- Multiple toasts stack nicely

Only override position for specific use cases (e.g., context-specific notifications near a specific UI element).

### Error Logging vs. Toast Notifications

Not every error should show a toast:

```python
# ✅ Good: Show toast for user-facing errors
try:
    save_file(path)
except PermissionError:
    show_error("Cannot Save File", "Permission denied")

# ❌ Bad: Don't show toast for internal errors
try:
    some_internal_calculation()
except ValueError as e:
    log.error(f"Calculation failed: {e}")  # Log only, no toast
```

## Advanced Topics

### Custom Toast Types

While not recommended, you can create custom icon types by extending `ToastIconType`:

```python
from datalens.ui.widgets.notifications.toast_types import ToastIconType

# This requires modifying toast_widget.py to handle the new type
# and providing a custom icon. Use existing types when possible.
```

### Programmatic Dismissal

Toasts automatically clean themselves up, but you can track them:

```python
manager = ToastManager.get_instance()

# Toasts don't return a handle, so you can't dismiss them programmatically
# This is intentional - toasts are fire-and-forget notifications

# If you need dismissible messages, use a dialog instead
```

### Suppression on Minimize/Inactive

The toast system respects user preferences for showing toasts when the window is minimized or inactive. This is configured via `ToastUiSettings`:

```python
from datalens.domain.system.ui import ToastUiSettings, ToastKind

settings = ToastUiSettings()
# Configure per-type behavior...

manager.apply_ui_settings(settings)
```

Toasts automatically hide when suppressed and reappear when the window becomes eligible again.

## See Also

- [Iconography Guidelines](iconography.md) - Icon design for toast notifications
- [Public API Reference](public_api.md#toast-notifications) - Toast API documentation
- [Theming](theming.md) - How toasts integrate with the application theme
