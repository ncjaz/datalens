from __future__ import annotations

"""
Layout utilities for DataLens V2 workspaces.

These helpers enable systemic, maintainable sizing without hardcoded values.
"""

from PySide6.QtWidgets import QFormLayout, QGroupBox, QLayout, QWidget

from datalens.core.logging import get_logger

log = get_logger(__name__)


def auto_size_form_layout(
    layout: QFormLayout,
    container: QWidget,
    *,
    scale: float = 1.15,
    set_minimum: bool = True,
) -> int:
    """
    Calculate and optionally apply automatic minimum width for a form layout.

    This uses Qt's introspection to compute the natural size of a form layout
    based on its fields, then applies a scale factor and sets it as the
    container's minimum width.

    **Performance**: This function calls `layout.activate()` which forces
    one-time layout calculation. The cost is O(n) in number of child widgets,
    typically <0.1ms for forms with 5-15 fields. This is paid once during
    widget construction, not during runtime.

    Args:
        layout: The QFormLayout to size.
        container: The parent widget/group box containing the layout.
        scale: Multiplier for the computed size (default 1.15 = 15% margin).
        set_minimum: If True, calls `container.setMinimumWidth()` automatically.

    Returns:
        The computed minimum width (after scaling).

    Example:
        ```python
        device_group = QGroupBox("Device", parent)
        device_layout = QFormLayout(device_group)
        device_layout.addRow("Camera:", camera_combo)
        device_layout.addRow("Resolution:", resolution_combo)

        # Auto-size with 20% margin
        auto_size_form_layout(device_layout, device_group, scale=1.20)
        ```

    Note:
        Call this **after** adding all widgets to the layout, but **before**
        showing the container. Calling it multiple times or after widgets
        are added/removed will trigger re-calculation.
    """
    if layout is None or container is None:
        log.warning("auto_size_form_layout called with None layout or container")
        return 0

    if scale <= 0:
        log.warning(f"auto_size_form_layout called with invalid scale: {scale}, using 1.15")
        scale = 1.15

    try:
        # Force layout to calculate sizes (one-time cost during construction).
        layout.activate()

        # Get layout's preferred size from Qt's introspection.
        size_hint = layout.sizeHint()
        natural_width = size_hint.width()

        # Add margins from the layout.
        margins = layout.contentsMargins()
        total_margin = margins.left() + margins.right()

        # If container is a QGroupBox, account for frame borders.
        extra_padding = 0
        if isinstance(container, QGroupBox):
            # QGroupBox typically has ~2px border + title space.
            extra_padding = 8

        # Compute final minimum width with scale factor.
        min_width = int((natural_width + total_margin + extra_padding) * scale)

        # Enforce reasonable absolute minimum (avoid zero/negative widths).
        min_width = max(min_width, 50)

        if set_minimum:
            container.setMinimumWidth(min_width)

        log.debug(
            f"auto_size_form_layout: natural={natural_width}, margins={total_margin}, "
            f"padding={extra_padding}, scale={scale}, final={min_width}"
        )

        return min_width

    except Exception:
        log.warning("auto_size_form_layout failed, using fallback minimum", exc_info=True)
        fallback = 200
        if set_minimum:
            container.setMinimumWidth(fallback)
        return fallback


def auto_size_layout(
    layout: QLayout,
    container: QWidget,
    *,
    scale: float = 1.15,
    set_minimum: bool = True,
) -> int:
    """
    Calculate and optionally apply automatic minimum width for any QLayout.

    Similar to `auto_size_form_layout()` but works with any QLayout subclass
    (QVBoxLayout, QHBoxLayout, QGridLayout, etc.).

    Args:
        layout: The QLayout to size.
        container: The parent widget containing the layout.
        scale: Multiplier for the computed size (default 1.15 = 15% margin).
        set_minimum: If True, calls `container.setMinimumWidth()` automatically.

    Returns:
        The computed minimum width (after scaling).

    Example:
        ```python
        controls = QWidget(parent)
        controls_layout = QVBoxLayout(controls)
        controls_layout.addWidget(device_group)
        controls_layout.addWidget(capture_group)

        # Auto-size entire controls panel
        auto_size_layout(controls_layout, controls, scale=1.10)
        ```
    """
    if layout is None or container is None:
        log.warning("auto_size_layout called with None layout or container")
        return 0

    if scale <= 0:
        log.warning(f"auto_size_layout called with invalid scale: {scale}, using 1.15")
        scale = 1.15

    try:
        layout.activate()
        size_hint = layout.sizeHint()
        natural_width = size_hint.width()

        margins = layout.contentsMargins()
        total_margin = margins.left() + margins.right()

        extra_padding = 0
        if isinstance(container, QGroupBox):
            extra_padding = 8

        min_width = int((natural_width + total_margin + extra_padding) * scale)

        # Enforce reasonable absolute minimum (avoid zero/negative widths).
        min_width = max(min_width, 50)

        if set_minimum:
            container.setMinimumWidth(min_width)

        log.debug(
            f"auto_size_layout: natural={natural_width}, margins={total_margin}, "
            f"padding={extra_padding}, scale={scale}, final={min_width}"
        )

        return min_width

    except Exception:
        log.warning("auto_size_layout failed, using fallback minimum", exc_info=True)
        fallback = 200
        if set_minimum:
            container.setMinimumWidth(fallback)
        return fallback


__all__ = [
    "auto_size_form_layout",
    "auto_size_layout",
]
