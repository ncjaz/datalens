from __future__ import annotations

"""
Styled icon buttons for DataLens V2.

These match the V1 annotation navigation button style for consistency.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QToolButton, QWidget

from datalens.ui.theme.app_theme import AppTheme


def create_icon_button(
    theme: AppTheme,
    parent: QWidget | None = None,
    *,
    size: int = 44,
    icon_size: int = 28,
    checkable: bool = False,
    accent_color: str | None = None,
    checked_accent_color: str | None = None,
    checked_solid: bool = False,
) -> QToolButton:
    """
    Create a styled icon button matching V1 annotation navigation style.

    This creates a pill-shaped button with theme-aware background and hover effects.
    The style is derived from the V1 annotation plugin's media navigation buttons.

    Args:
        theme: Current AppTheme for styling.
        parent: Parent widget.
        size: Button fixed width/height in pixels (default 44).
        icon_size: Icon size in pixels (default 28).
        checkable: If True, button is checkable/toggleable (default False).
        accent_color: Base (unchecked) accent color override.
        checked_accent_color: Checked-state accent color override.

    Returns:
        A styled QToolButton.

    Example:
        ```python
        refresh_btn = create_icon_button(theme, parent, checkable=True)
        refresh_btn.setIcon(refresh_icon(theme, size=18))
        refresh_btn.clicked.connect(do_refresh)
        ```

    Style characteristics:
    - Fixed size with rounded corners (pill shape)
    - Semi-transparent tertiary color background (tool/utility emphasis)
    - Smooth hover effect
    - Pointing hand cursor
    - Theme-aware colors that update automatically

    Note:
        Call `apply_icon_button_theme()` after theme changes to update colors.
    """
    button = QToolButton(parent)
    button.setCheckable(checkable)
    button.setAutoRaise(False)
    button.setIconSize(QSize(icon_size, icon_size))
    button.setFixedSize(size, size)
    button.setCursor(Qt.PointingHandCursor)
    button.setFocusPolicy(Qt.NoFocus)

    apply_icon_button_theme(
        button,
        theme,
        accent_color=accent_color,
        checked_accent_color=checked_accent_color,
        checked_solid=checked_solid,
    )
    return button


def apply_icon_button_theme(
    button: QToolButton,
    theme: AppTheme,
    *,
    accent_color: str | None = None,
    checked_accent_color: str | None = None,
    checked_solid: bool = False,
) -> None:
    """
    Apply theme-aware styling to an icon button.

    This applies the V1-style pill button appearance with theme colors.

    Args:
        button: The QToolButton to style.
        theme: Current AppTheme.
        accent_color: Base (unchecked) accent color override.
        checked_accent_color: Checked-state accent color override.

    Color scheme:
    - Base: tertiary color at 24% opacity (enabled) or secondary at 18% (disabled)
    - Hover: tertiary color at 32% opacity
    - Checked: primary color at 32% opacity (subtle, tool-style)
    - Checked hover: primary color at 40% opacity
    - Disabled: secondary color at 16% opacity

    Example:
        ```python
        # Update button theme when app theme changes
        apply_icon_button_theme(my_button, new_theme)
        ```
    """
    enabled = button.isEnabled()
    checkable = button.isCheckable()

    accent = str(accent_color or theme.tertiary_color)
    checked_accent = str(checked_accent_color or theme.primary_color)

    base_bg = theme.with_alpha_hex(
        accent if enabled else theme.secondary_color,
        0.24 if enabled else 0.18,
    )
    hover_bg = theme.with_alpha_hex(accent, 0.32)
    disabled_bg = theme.with_alpha_hex(theme.secondary_color, 0.16)

    # Base styles (always applied)
    stylesheet = (
        "QToolButton {"
        f"background-color: {base_bg};"
        "border: none;"
        "border-radius: 18px;"
        "padding: 6px;"
        "}"
        f"QToolButton:hover:!disabled {{ background-color: {hover_bg}; }}"
        f"QToolButton:disabled {{ background-color: {disabled_bg}; }}"
    )

    # Add checked state styling if button is checkable
    if checkable:
        if checked_solid:
            # Use solid accent color like the Toggle widget for visual consistency.
            checked_bg = checked_accent
            checked_hover_bg = theme.with_alpha_hex(checked_accent, 0.85)
        else:
            # Subtle checked state: keep the same opacity scheme as the base button
            # and avoid a distracting solid fill for tool-style icon buttons.
            checked_bg = theme.with_alpha_hex(checked_accent, 0.32)
            checked_hover_bg = theme.with_alpha_hex(checked_accent, 0.40)
        stylesheet += (
            f"QToolButton:checked {{ background-color: {checked_bg}; }}"
            f"QToolButton:checked:hover {{ background-color: {checked_hover_bg}; }}"
        )

    button.setStyleSheet(stylesheet)


__all__ = [
    "create_icon_button",
    "apply_icon_button_theme",
]
