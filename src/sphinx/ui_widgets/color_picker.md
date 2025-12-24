# Color Picker Widget

Comprehensive color selection widget with app theme integration and opacity support.

## Overview

The color picker provides multiple ways for users to select colors:

- **RGB/HSV Controls**: Precise numeric input with sliders
- **Theme Colors**: Select from app theme color palette
- **Opacity/Alpha**: Adjust transparency
- **Hex Input**: Direct hex color code entry
- **Preference Integration**: Save/load from user preferences

## Components

### ColorValue

Data class representing a color with optional theme reference and opacity.

```python
@dataclass
class ColorValue:
    color: QColor              # The actual color
    theme_reference: str | None  # Optional ref like "primary_color"
    opacity: float             # Alpha 0.0 to 1.0
```

**Key Features**:
- Can reference theme colors for dynamic theming
- Stores opacity separately for flexible application
- Serializable to/from dict for preferences

### ColorPickerWidget

Main color picker widget with all controls.

```python
from datalens.ui.widgets.color_picker import ColorPickerWidget
from datalens.ui.theme import AppTheme

theme = AppTheme()
picker = ColorPickerWidget(theme=theme)

# Connect to changes
picker.color_changed.connect(on_color_changed)

# Get current color
color = picker.current_color()  # QColor with opacity
value = picker.current_value()  # ColorValue with theme ref
```

### ColorPickerButton

Convenient button that opens a dialog.

```python
from datalens.ui.widgets.color_picker import ColorPickerButton

button = ColorPickerButton(
    theme=theme,
    initial_color=QColor("#FF5733"),
    text="Choose Color"
)

button.color_changed.connect(on_color_changed)
```

### ColorPickerDialog

Full dialog with OK/Cancel buttons.

```python
from datalens.ui.widgets.color_picker import ColorPickerDialog

dialog = ColorPickerDialog(theme=theme)
if dialog.exec() == QDialog.DialogCode.Accepted:
    selected = dialog.current_value()
    print(f"Selected: {selected.color.name()}")
```

## Usage Examples

### Basic Usage

```python
from PySide6.QtGui import QColor
from datalens.ui.widgets.color_picker import ColorPickerWidget
from datalens.core.context import get_app_context

app_ctx = get_app_context()
theme = app_ctx.theme

# Create picker
picker = ColorPickerWidget(theme=theme)

# Set initial color
picker.set_color(QColor("#FF5733"))
picker.set_opacity(0.8)

# Handle color changes
def on_color_changed(value: ColorValue):
    color = value.with_opacity()  # QColor with alpha
    print(f"Color: {color.name()}")
    print(f"Opacity: {value.opacity}")
    if value.theme_reference:
        print(f"Theme reference: {value.theme_reference}")

picker.color_changed.connect(on_color_changed)
```

### Using Theme Colors

```python
# User selects theme color (e.g., "primary_color")
# ColorValue will have theme_reference set

value = picker.current_value()
if value.theme_reference:
    # This color follows the theme
    # When theme changes, you can resolve the reference:
    new_color = QColor(getattr(theme, value.theme_reference))
```

### Saving to Preferences

```python
from datalens.services.config_service import load_settings, save_settings

# Save color to preferences
color_data = picker.to_dict()
# Returns: {
#     'r': 255,
#     'g': 87,
#     'b': 51,
#     'opacity': 0.8,
#     'theme_reference': None  # or "primary_color" if theme color
# }

# Save to settings
settings = load_settings()
settings.my_custom_color = color_data
save_settings(settings)
```

### Loading from Preferences

```python
# Load from preferences
settings = load_settings()
if hasattr(settings, 'my_custom_color'):
    picker.from_dict(settings.my_custom_color)
```

### Using ColorPickerButton

```python
# Simple button approach
button = ColorPickerButton(theme=theme, text="Background Color")

def apply_color(value: ColorValue):
    color = value.with_opacity()
    my_widget.setStyleSheet(f"background-color: {color.name()};")

button.color_changed.connect(apply_color)

# Load from preferences
if hasattr(settings, 'background_color'):
    button.from_dict(settings.background_color)
```

## Integration with Preferences Dialog

Example of integrating into a plugin's preferences:

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from datalens.ui.widgets.color_picker import ColorPickerButton
from datalens.core.context import get_app_context

class MyPluginPreferences(QWidget):
    def __init__(self, plugin_id: str, parent=None):
        super().__init__(parent)
        self._plugin_id = plugin_id

        app_ctx = get_app_context()
        theme = app_ctx.theme

        layout = QVBoxLayout(self)

        # Label color picker
        layout.addWidget(QLabel("Label Color:"))
        self._label_color_btn = ColorPickerButton(theme=theme)
        self._label_color_btn.color_changed.connect(self._on_color_changed)
        layout.addWidget(self._label_color_btn)

        # Load from preferences
        self._load_preferences()

    def _load_preferences(self):
        """Load colors from plugin preferences."""
        app_ctx = get_app_context()
        prefs = app_ctx.preferences

        label_color = prefs.get_preference(self._plugin_id, "label_color")
        if label_color:
            self._label_color_btn.from_dict(label_color)

    def _on_color_changed(self, value: ColorValue):
        """Save when color changes."""
        app_ctx = get_app_context()
        prefs = app_ctx.preferences

        color_data = self._label_color_btn.to_dict()
        prefs.set_preference(self._plugin_id, "label_color", color_data)
```

## Working with Theme References

When a color has a `theme_reference`, it means the user selected it from the theme color palette. This allows the color to dynamically update when the theme changes.

```python
def resolve_color(value: ColorValue, theme: AppTheme) -> QColor:
    """
    Resolve a ColorValue to a QColor, following theme references.

    Args:
        value: ColorValue to resolve
        theme: Current AppTheme

    Returns:
        QColor with opacity applied
    """
    if value.theme_reference:
        # Get current theme color
        color_hex = getattr(theme, value.theme_reference, value.color.name())
        color = QColor(color_hex)
    else:
        # Use custom color
        color = value.color

    # Apply opacity
    color.setAlphaF(value.opacity)
    return color

# Usage
color_value = picker.current_value()
resolved_color = resolve_color(color_value, theme)
```

## Advanced: Dynamic Theme Updates

Listen to theme changes and update colors that reference theme:

```python
class MyWidget(QWidget):
    def __init__(self, theme: AppTheme):
        super().__init__()
        self._theme = theme
        self._background_value = None  # ColorValue

        # Connect to theme changes
        theme.theme_changed.connect(self._on_theme_changed)

    def set_background_color(self, value: ColorValue):
        """Set background color (may reference theme)."""
        self._background_value = value
        self._apply_background()

    def _apply_background(self):
        """Apply background color, resolving theme references."""
        if not self._background_value:
            return

        color = resolve_color(self._background_value, self._theme)
        self.setStyleSheet(f"background-color: {color.name()};")

    def _on_theme_changed(self):
        """Re-apply colors when theme changes."""
        self._apply_background()
```

## Opacity Handling

The opacity/alpha channel is stored separately from RGB:

```python
value = ColorValue(
    color=QColor(255, 0, 0),  # Red, opaque
    opacity=0.5,              # 50% transparent
    theme_reference=None
)

# Get color with opacity applied
final_color = value.with_opacity()
# Returns QColor(255, 0, 0, 127)  # 50% alpha

# Or manually apply
color = value.color
color.setAlphaF(value.opacity)
```

## Complete Plugin Example

Here's a complete example of a plugin using color pickers:

```python
# my_plugin/preferences.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLabel
from datalens.ui.widgets.color_picker import ColorPickerButton, ColorValue
from datalens.core.context import get_app_context

class MyPluginPreferences(QWidget):
    """Preferences UI for my plugin."""

    def __init__(self, plugin_id: str, parent=None):
        super().__init__(parent)
        self._plugin_id = plugin_id

        app_ctx = get_app_context()
        theme = app_ctx.theme

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Primary color
        self._primary_btn = ColorPickerButton(theme=theme, text="Select")
        self._primary_btn.color_changed.connect(self._save_colors)
        form.addRow("Primary Color:", self._primary_btn)

        # Secondary color
        self._secondary_btn = ColorPickerButton(theme=theme, text="Select")
        self._secondary_btn.color_changed.connect(self._save_colors)
        form.addRow("Secondary Color:", self._secondary_btn)

        # Background with opacity
        self._background_btn = ColorPickerButton(theme=theme, text="Select")
        self._background_btn.color_changed.connect(self._save_colors)
        form.addRow("Background:", self._background_btn)

        layout.addLayout(form)
        layout.addStretch()

        # Load saved preferences
        self._load_preferences()

    def _load_preferences(self):
        """Load colors from preferences."""
        app_ctx = get_app_context()
        prefs = app_ctx.preferences

        # Load each color
        primary = prefs.get_preference(self._plugin_id, "primary_color")
        if primary:
            self._primary_btn.from_dict(primary)

        secondary = prefs.get_preference(self._plugin_id, "secondary_color")
        if secondary:
            self._secondary_btn.from_dict(secondary)

        background = prefs.get_preference(self._plugin_id, "background_color")
        if background:
            self._background_btn.from_dict(background)

    def _save_colors(self, value: ColorValue):
        """Save colors to preferences."""
        app_ctx = get_app_context()
        prefs = app_ctx.preferences

        # Save all colors
        prefs.set_preference(
            self._plugin_id,
            "primary_color",
            self._primary_btn.to_dict()
        )
        prefs.set_preference(
            self._plugin_id,
            "secondary_color",
            self._secondary_btn.to_dict()
        )
        prefs.set_preference(
            self._plugin_id,
            "background_color",
            self._background_btn.to_dict()
        )

# my_plugin/widget.py
class MyPluginWidget(QWidget):
    """Main plugin widget that uses the colors."""

    def __init__(self, plugin_id: str):
        super().__init__()
        self._plugin_id = plugin_id

        app_ctx = get_app_context()
        self._theme = app_ctx.theme
        self._prefs = app_ctx.preferences

        # Connect to theme changes for dynamic updates
        self._theme.theme_changed.connect(self._apply_colors)

        # Connect to preference changes
        self._prefs.preference_changed.connect(self._on_pref_changed)

        self._apply_colors()

    def _apply_colors(self):
        """Apply colors from preferences."""
        # Load colors
        primary_data = self._prefs.get_preference(self._plugin_id, "primary_color")
        if primary_data:
            primary_value = ColorValue.from_dict(primary_data)
            primary_color = resolve_color(primary_value, self._theme)

            # Use the color
            self.setStyleSheet(f"border: 2px solid {primary_color.name()};")

    def _on_pref_changed(self, plugin_id: str, key: str):
        """Handle preference changes."""
        if plugin_id == self._plugin_id and key.endswith("_color"):
            self._apply_colors()
```

## API Reference

### ColorValue

```python
@dataclass
class ColorValue:
    color: QColor
    theme_reference: str | None = None
    opacity: float = 1.0

    def to_dict() -> dict:
        """Serialize for preferences."""

    @staticmethod
    def from_dict(data: dict) -> ColorValue:
        """Deserialize from preferences."""

    def with_opacity() -> QColor:
        """Get QColor with opacity applied."""
```

### ColorPickerWidget

```python
class ColorPickerWidget(QWidget):
    color_changed = Signal(object)  # Emits ColorValue

    def __init__(
        theme: AppTheme | None = None,
        initial_color: QColor | None = None,
        parent = None
    )

    def current_color() -> QColor:
        """Get color with opacity."""

    def current_value() -> ColorValue:
        """Get full ColorValue."""

    def set_color(color: QColor, theme_reference: str | None = None):
        """Set color."""

    def set_opacity(opacity: float):
        """Set opacity (0.0 to 1.0)."""

    def to_dict() -> dict:
        """Save to preferences."""

    def from_dict(data: dict):
        """Load from preferences."""
```

### ColorPickerButton

```python
class ColorPickerButton(QPushButton):
    color_changed = Signal(object)  # Emits ColorValue

    def __init__(
        theme: AppTheme | None = None,
        initial_color: QColor | None = None,
        parent = None,
        text: str = "Choose Color"
    )

    def current_color() -> QColor:
        """Get color with opacity."""

    def current_value() -> ColorValue:
        """Get full ColorValue."""

    def set_color(color: QColor, theme_reference: str | None = None):
        """Set color."""

    def set_opacity(opacity: float):
        """Set opacity (0.0 to 1.0)."""

    def to_dict() -> dict:
        """Save to preferences."""

    def from_dict(data: dict):
        """Load from preferences."""
```

### ColorPickerDialog

```python
class ColorPickerDialog(QDialog):
    def __init__(
        theme: AppTheme | None = None,
        initial_value: ColorValue | None = None,
        parent = None
    )

    def current_value() -> ColorValue:
        """Get selected ColorValue."""
```

## Best Practices

1. **Always provide theme** when creating pickers:
   ```python
   picker = ColorPickerWidget(theme=app_ctx.theme)
   ```

2. **Use `ColorValue` for storage**, not just `QColor`:
   ```python
   # Good - preserves theme reference and opacity
   data = picker.to_dict()

   # Bad - loses theme reference
   color = picker.current_color()
   data = {'r': color.red(), 'g': color.green(), 'b': color.blue()}
   ```

3. **Resolve theme references** when applying colors:
   ```python
   value = picker.current_value()
   color = resolve_color(value, theme)  # Handles theme refs
   ```

4. **Listen to theme changes** if using theme references:
   ```python
   theme.theme_changed.connect(reapply_colors)
   ```

5. **Save to preferences immediately** or on OK:
   ```python
   # Option 1: Save on every change
   picker.color_changed.connect(lambda v: save_to_prefs(v.to_dict()))

   # Option 2: Save on dialog accept
   if dialog.exec() == QDialog.DialogCode.Accepted:
       save_to_prefs(dialog.current_value().to_dict())
   ```

## Testing

Example test for color picker:

```python
# tests/integration/ui/test_color_picker.py
import pytest
from PySide6.QtGui import QColor
from datalens.ui.widgets.color_picker import ColorPickerWidget, ColorValue

@pytest.mark.ui
def test_color_picker_basic(datalens_app):
    """Test basic color picker functionality."""
    theme = datalens_app.app_theme

    picker = ColorPickerWidget(theme=theme)

    # Set color
    test_color = QColor(255, 100, 50)
    picker.set_color(test_color)

    # Verify
    current = picker.current_color()
    assert current.red() == 255
    assert current.green() == 100
    assert current.blue() == 50

@pytest.mark.ui
def test_color_picker_opacity(datalens_app):
    """Test opacity setting."""
    picker = ColorPickerWidget()
    picker.set_opacity(0.5)

    color = picker.current_color()
    assert abs(color.alphaF() - 0.5) < 0.01

@pytest.mark.ui
def test_color_picker_preferences(datalens_app):
    """Test save/load from preferences."""
    picker = ColorPickerWidget()

    # Set color with opacity
    picker.set_color(QColor(255, 0, 0))
    picker.set_opacity(0.75)

    # Save to dict
    data = picker.to_dict()
    assert data['r'] == 255
    assert data['opacity'] == 0.75

    # Create new picker and load
    picker2 = ColorPickerWidget()
    picker2.from_dict(data)

    assert picker2.current_color().red() == 255
    assert abs(picker2.current_value().opacity - 0.75) < 0.01
```
