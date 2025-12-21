from __future__ import annotations

from PySide6.QtWidgets import QAbstractButton

from PySide6.QtCore import QObject

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.icons.animated.icon_animator import ButtonIconAnimator
from datalens.ui.widgets.icons.autodiscovery_icon import autodiscovery_icon


class AutoDiscoveryAnimator(ButtonIconAnimator):
    """
    Animate the autodiscovery glyph by rotating its arcs.

    Usage:
        animator = AutoDiscoveryAnimator(theme, size=18)
        animator.start(button)
        ...
        animator.stop()
    """

    def __init__(
        self,
        theme: AppTheme,
        *,
        size: int = 18,
        interval_ms: int = 60,
        degrees_per_tick: float = 8.0,
        parent: QObject | None = None,
    ) -> None:
        self._theme = theme
        self._size = int(size)
        super().__init__(
            frame_supplier=lambda angle: autodiscovery_icon(self._theme, size=self._size, rotation_deg=angle),
            interval_ms=interval_ms,
            degrees_per_tick=degrees_per_tick,
            parent=parent,
        )

    def start(self, button: QAbstractButton) -> None:  # type: ignore[override]
        super().start(button)


__all__ = ["AutoDiscoveryAnimator"]
