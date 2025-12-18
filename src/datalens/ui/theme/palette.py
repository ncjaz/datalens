"""
Qt palette helpers.

V2 follows the V1 approach: a global QApplication palette is derived primarily
from the theme's ``background_color`` so widget surfaces naturally render as
two-tone (Window vs Base/AlternateBase) without needing per-widget styles.

The canonical implementation lives on :class:`datalens.ui.theme.app_theme.AppTheme`
as ``apply_to(app)``. This module exists as a stable import location for code
and documentation that prefers an explicit "palette" entrypoint.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from datalens.ui.theme.app_theme import AppTheme


def apply_palette(app: QApplication, theme: AppTheme) -> None:
    theme.apply_to(app)
