from __future__ import annotations

"""
Resizable splitter for DataLens V2 workspaces.

This provides a better-performing alternative to the welcome screen's approach.
Key improvements:
- Opaque resize by default (prevents continuous repaint flicker)
- Automatic state persistence via QSettings
- Theme-aware handle styling
- Configurable handle width and hover effects
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QWidget

from datalens.ui.qt_settings import plugin_ui_scope
from datalens.ui.theme.app_theme import AppTheme


class DatalensResizableSplitter(QSplitter):
    """
    Theme-aware resizable splitter with automatic state persistence.

    This splitter:
    - Uses opaque resize (better performance than welcome screen's transparent)
    - Automatically saves/restores state to QSettings
    - Applies theme-consistent handle styling
    - Prevents child widgets from collapsing

    Performance notes:
    - Opaque resize (default) only repaints on mouse release → smooth dragging
    - Transparent resize repaints continuously during drag → can cause lag with
      heavy widgets (like video preview). Only use transparent for lightweight panels.

    Example:
        ```python
        splitter = DatalensResizableSplitter(
            orientation=Qt.Horizontal,
            theme=theme,
            plugin_id="capture",
            state_key="main_splitter",
            parent=self,
        )
        splitter.addWidget(preview_widget)
        splitter.addWidget(controls_widget)
        splitter.setStretchFactor(0, 3)  # Preview gets 3x space
        splitter.setStretchFactor(1, 1)  # Controls gets 1x space
        ```
    """

    def __init__(
        self,
        orientation: Qt.Orientation,
        theme: AppTheme,
        *,
        plugin_id: str | None = None,
        state_key: str | None = None,
        handle_width: int = 6,
        opaque_resize: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """
        Initialize a resizable splitter.

        Args:
            orientation: Qt.Horizontal or Qt.Vertical.
            theme: Current AppTheme for styling.
            plugin_id: Plugin ID for QSettings namespacing (if state_key provided).
            state_key: Key for saving/restoring splitter state in QSettings.
            handle_width: Width of the drag handle in pixels (default 6).
            opaque_resize: If True, only repaint on release (better performance).
                          If False, repaint continuously during drag (can lag).
            parent: Parent widget.
        """
        super().__init__(orientation, parent)
        self._theme = theme
        self._plugin_id = plugin_id
        self._state_key = state_key
        self._settings_scope = None

        # Configure splitter behavior.
        self.setHandleWidth(handle_width)
        self.setChildrenCollapsible(False)  # Prevent panels from collapsing
        self.setOpaqueResize(opaque_resize)

        # Set up QSettings scope if persistence is requested.
        if plugin_id is not None and state_key is not None:
            self._settings_scope = plugin_ui_scope(plugin_id, "splitters")

        # Apply theme styling.
        self._apply_theme()

        # Restore state if available.
        self._restore_state()

    def _apply_theme(self) -> None:
        """Apply theme-aware styling to the splitter handle."""
        t = self._theme
        handle_line = t.with_alpha_hex(t.text_color, 0.10)
        handle_hover = t.with_alpha_hex(t.primary_color, 0.15)

        if self.orientation() == Qt.Horizontal:
            self.setStyleSheet(
                f"""
                QSplitter::handle:horizontal {{
                    background-color: transparent;
                    border-left: 1px solid {handle_line};
                }}
                QSplitter::handle:horizontal:hover {{
                    background-color: {handle_hover};
                }}
                """
            )
        else:
            self.setStyleSheet(
                f"""
                QSplitter::handle:vertical {{
                    background-color: transparent;
                    border-top: 1px solid {handle_line};
                }}
                QSplitter::handle:vertical:hover {{
                    background-color: {handle_hover};
                }}
                """
            )

    def _restore_state(self) -> None:
        """Restore splitter state from QSettings if configured."""
        if self._settings_scope is None or self._state_key is None:
            return

        try:
            self._settings_scope.restore_splitter(self._state_key, self)
        except Exception:
            # State restoration is best-effort; don't crash if it fails.
            pass

    def save_state_to_settings(self) -> None:
        """
        Manually save current splitter state to QSettings.

        This is automatically called on close events for windows/dialogs,
        but you can call it manually if needed (e.g., on workspace switch).
        """
        if self._settings_scope is None or self._state_key is None:
            return

        try:
            self._settings_scope.save_splitter(self._state_key, self)
        except Exception:
            pass

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Save state when splitter's parent window closes."""
        self.save_state_to_settings()
        super().closeEvent(event)


__all__ = ["DatalensResizableSplitter"]
