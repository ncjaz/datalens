# Layout utilities

DataLens V2 provides systemic layout utilities that eliminate hardcoded sizing
values and enable maintainable, responsive UIs.

## Overview

Rather than manually setting `setMinimumWidth(320)` on every group box and
widget, use the auto-sizing utilities that introspect Qt's layout system to
compute natural sizes automatically.

**Benefits:**
- No hardcoded magic numbers
- Automatic adaptation when controls are added/removed
- Consistent sizing across all plugins
- Better DPI scaling support
- Reduced bugs from miscalculated minimums

**Performance:** The systemic approach has negligible overhead. Auto-sizing
calls `layout.activate()` once during widget construction (O(n) in child
widgets, typically <0.1ms for 5-15 fields). This is a one-time cost paid
during initialization, not during runtime.

## Auto-sizing utilities

### `auto_size_form_layout()`

Automatically size form layouts based on their fields.

```python
from datalens.ui.widgets.layouts import auto_size_form_layout

device_group = QGroupBox("Device", parent)
device_layout = QFormLayout(device_group)
device_layout.addRow("Camera:", camera_combo)
device_layout.addRow("Resolution:", resolution_combo)

# Auto-size with 15% margin (after adding all fields)
auto_size_form_layout(device_layout, device_group, scale=1.15)
```

**When to call:** After adding all widgets to the layout, but before showing
the container.

**Scale parameter:** Multiplier for computed size (default 1.15 = 15% margin).
- Use 1.10-1.15 for compact forms
- Use 1.20-1.30 for breathing room
- Use 1.0 for exact fit (not recommended)

### `auto_size_layout()`

Automatically size any QLayout (QVBoxLayout, QHBoxLayout, QGridLayout, etc.).

```python
from datalens.ui.widgets.layouts import auto_size_layout

controls = QWidget(parent)
controls_layout = QVBoxLayout(controls)
controls_layout.addWidget(device_group)
controls_layout.addWidget(capture_group)

# Auto-size entire controls panel
auto_size_layout(controls_layout, controls, scale=1.10)
```

## Resizable splitters

### `DatalensResizableSplitter`

Theme-aware resizable splitter with automatic state persistence and better
performance than `QSplitter` with transparent resize.

```python
from datalens.ui.widgets.core import DatalensResizableSplitter

splitter = DatalensResizableSplitter(
    orientation=Qt.Horizontal,
    theme=theme,
    plugin_id="capture",
    state_key="workspace_splitter",
    parent=self,
)

splitter.addWidget(preview_widget)
splitter.addWidget(controls_widget)

# Set stretch factors (preview gets 3x space, controls get 1x)
splitter.setStretchFactor(0, 3)
splitter.setStretchFactor(1, 1)
```

**Features:**
- Opaque resize by default (better performance than welcome screen's approach)
- Automatic state persistence via QSettings
- Theme-aware handle styling with hover effects
- Prevents child widgets from collapsing (`setChildrenCollapsible(False)`)

**Performance notes:**
- **Opaque resize (default):** Only repaints on mouse release → smooth dragging
  even with heavy widgets like video preview
- **Transparent resize:** Repaints continuously during drag → can lag with
  complex panels. Only use for lightweight panels.

**State persistence:** Splitter positions are automatically saved to QSettings
and restored on next launch. No manual save/restore code needed.

## Complete example: Capture workspace

Here's how the capture plugin uses both utilities together:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QGroupBox, QVBoxLayout, QWidget

from datalens.ui.widgets.core import DatalensResizableSplitter
from datalens.ui.widgets.layouts import auto_size_form_layout, auto_size_layout

# Create root layout
root = QVBoxLayout(self)
root.setContentsMargins(18, 18, 18, 18)
root.setSpacing(0)

# Create resizable splitter
splitter = DatalensResizableSplitter(
    orientation=Qt.Horizontal,
    theme=theme,
    plugin_id="capture",
    state_key="workspace_splitter",
    parent=self,
)

# Left: preview panel
preview_group = QGroupBox("Camera Preview", splitter)
# Prevent splitter from hiding preview entirely (safety minimum)
preview_group.setMinimumWidth(320)
# ... add preview widgets ...

# Right: controls panel
controls_scroll = QScrollArea(splitter)
controls_scroll.setWidgetResizable(True)

controls = QWidget(controls_scroll)
controls_scroll.setWidget(controls)
controls_layout = QVBoxLayout(controls)

# Device group (form layout)
device_group = QGroupBox("Device", controls)
device_layout = QFormLayout(device_group)
device_layout.addRow("Camera:", camera_combo)
device_layout.addRow("Auto-refresh modifier:", modifier_combo)

# Auto-size device group
auto_size_form_layout(device_layout, device_group, scale=1.15)
controls_layout.addWidget(device_group)

# Capture group (vertical layout)
capture_group = QGroupBox("Capture", controls)
capture_layout = QVBoxLayout(capture_group)
# ... add buttons, checkboxes ...

# Auto-size capture group
auto_size_layout(capture_layout, capture_group, scale=1.15)
controls_layout.addWidget(capture_group)

controls_layout.addStretch(1)

# Auto-size entire controls panel and use computed width for scroll area minimum.
# This prevents clipping when user drags the splitter.
computed_width = auto_size_layout(controls_layout, controls, scale=1.15)
controls_scroll.setMinimumWidth(computed_width + 20)  # +20 for scroll area margins

# Add to splitter
splitter.addWidget(preview_group)
splitter.addWidget(controls_scroll)
splitter.setStretchFactor(0, 3)  # Preview gets 3x space
splitter.setStretchFactor(1, 1)  # Controls get 1x space

root.addWidget(splitter, 1)
```

**Key insight:** The auto-sizing utilities return the computed width, which you
can use to set the minimum on parent containers (like scroll areas). This
combines the benefits of systemic sizing with splitter safety.

## Migration from hardcoded values

**Before (hardcoded minimums):**
```python
device_group = QGroupBox("Device", controls)
device_group.setMinimumWidth(320)  # Magic number
device_layout = QFormLayout(device_group)
# ... add fields ...

controls_scroll.setMinimumWidth(360)  # Magic number
controls_scroll.setMaximumWidth(480)  # Magic number
self.setMinimumWidth(920)  # Magic number
```

**After (systemic sizing):**
```python
device_group = QGroupBox("Device", controls)
device_layout = QFormLayout(device_group)
# ... add fields ...

# Automatically computed from actual field widths
auto_size_form_layout(device_layout, device_group, scale=1.15)

# No hardcoded minimums needed - splitter handles resizing
# Controls panel automatically sized from its children
auto_size_layout(controls_layout, controls, scale=1.10)
```

## Best practices

### 1. Call auto-sizing in the right order

Auto-size leaf containers first, then parent containers:

```python
# ✓ Correct order: leaf → parent
auto_size_form_layout(device_layout, device_group)  # Leaf
auto_size_layout(controls_layout, controls)          # Parent

# ✗ Wrong order: parent → leaf
auto_size_layout(controls_layout, controls)          # Parent first
auto_size_form_layout(device_layout, device_group)  # Leaf second (too late)
```

### 2. Choose appropriate scale factors

- **Forms with labels + controls:** 1.15-1.20 (15-20% margin)
- **Button rows / tight layouts:** 1.10-1.15 (10-15% margin)
- **Panels with nested groups:** 1.10 (rely on child margins)
- **Never use 1.0:** Always add at least 10% breathing room

### 3. Use splitters for major layout divisions

Use `DatalensResizableSplitter` for major workspace divisions (preview vs
controls, tree vs detail, etc.). This gives users control and eliminates the
need for hardcoded widths entirely.

**IMPORTANT: Always set minimum widths on splitter children** to prevent panels
from being hidden when users drag the splitter handle:

```python
# ✓ Correct: use computed width from auto-sizing as safety minimum
controls = QWidget(controls_scroll)
controls_layout = QVBoxLayout(controls)
# ... add all controls ...

# Compute natural width, then use it as scroll area's minimum
computed_width = auto_size_layout(controls_layout, controls, scale=1.15)
controls_scroll.setMinimumWidth(computed_width + 20)  # +20 for margins

# For panels without auto-sizing, use a reasonable hardcoded minimum
preview_group = QGroupBox("Preview", splitter)
preview_group.setMinimumWidth(320)

splitter.addWidget(preview_group)
splitter.addWidget(controls_scroll)
```

These are **safety minimums**, not natural sizing. They prevent the splitter
from collapsing panels to zero width. When possible, use the computed width
from `auto_size_layout()` instead of hardcoding values.

**Don't use splitters for:**
- Minor layout tweaks (use layouts with size policies instead)
- Nested splitters (gets confusing; prefer one primary splitter)
- Vertical space allocation (use QVBoxLayout with stretch factors instead)

### 4. Let Qt handle the math

Don't manually calculate minimums like `480 + 360 + 50 = 890`. Let Qt's layout
system compute the natural size by calling `auto_size_layout()` on the parent.

### 5. Test with different DPI settings

Auto-sizing adapts to DPI scaling automatically. Test your workspace at 100%,
125%, 150%, and 200% scaling to verify it remains readable.

## Troubleshooting

### Splitter allows hiding panels by dragging

**Cause:** Missing minimum width on splitter's direct children.

**Fix:** Set minimum widths on widgets added to the splitter:
```python
# ✗ Wrong: no minimum width
preview_group = QGroupBox("Preview", splitter)
splitter.addWidget(preview_group)  # Can be dragged to zero width!

# ✓ Correct: safety minimum prevents hiding
preview_group = QGroupBox("Preview", splitter)
preview_group.setMinimumWidth(320)  # User can't hide preview
splitter.addWidget(preview_group)
```

### Controls still clipping after auto-sizing

**Cause:** You called `auto_size_layout()` before adding all child widgets.

**Fix:** Move the `auto_size_layout()` call to after all `addWidget()` calls.

### Splitter not saving/restoring position

**Cause:** Missing `plugin_id` or `state_key` parameter.

**Fix:** Always provide both for persistence:
```python
splitter = DatalensResizableSplitter(
    orientation=Qt.Horizontal,
    theme=theme,
    plugin_id="your_plugin_id",    # Required for persistence
    state_key="workspace_splitter",  # Required for persistence
    parent=self,
)
```

### Performance lag during splitter drag

**Cause:** Using transparent resize with heavy widgets (like video preview).

**Fix:** Use opaque resize (the default):
```python
splitter = DatalensResizableSplitter(
    ...,
    opaque_resize=True,  # Default (only repaints on mouse release)
)
```

### Computed width too small/large

**Cause:** Wrong scale factor.

**Fix:** Adjust the `scale` parameter:
```python
# Too tight? Increase scale
auto_size_form_layout(layout, container, scale=1.25)  # Was 1.15

# Too loose? Decrease scale
auto_size_form_layout(layout, container, scale=1.10)  # Was 1.20
```

## Related docs

- [UI Presentation](ui_presentation.md) - Workspace construction patterns
- [Theming](theming.md) - Theme-aware styling
- [Iconography](iconography.md) - Icon sizing guidelines
