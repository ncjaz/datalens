from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from datalens.core.context import get_app_context
from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton

from .common import make_section_box

log = get_logger(__name__)

_WIDGET_TEST_PLUGIN_ID = PluginId("widget_test")


def build_preferences_demo_section(parent: QWidget, *, theme: AppTheme) -> QWidget:
    """
    Demo: manifest-driven plugin preferences.

    This section exists to validate the "Preferences -> Plugins" system:
    - schema comes from `manifest.json` (no runtime plugin import needed)
    - values persist under `settings.json` (AppSettings.plugin_settings)
    - changes are published via EventHub so UIs can refresh live
    """

    box = make_section_box(parent, "Plugin Preferences (manifest-driven)")
    layout = QGridLayout(box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setHorizontalSpacing(10)
    layout.setVerticalSpacing(8)

    intro = QLabel(
        "These values come from Preferences -> Plugins -> Widget Test.\n"
        "They are loaded from settings.json and can change live via EventHub.",
        box,
    )
    intro.setWordWrap(True)
    intro.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
    layout.addWidget(intro, 0, 0, 1, 3)

    values_label = QLabel("", box)
    values_label.setWordWrap(True)
    values_label.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.85)}; font-size: 11px;")
    layout.addWidget(values_label, 1, 0, 1, 3)

    def refresh() -> None:
        app_ctx = get_app_context()
        prefs = app_ctx.preferences
        verbose = prefs.get(_WIDGET_TEST_PLUGIN_ID, "verbose_logging", default=False)
        mode = prefs.get(_WIDGET_TEST_PLUGIN_ID, "demo_mode", default="basic")
        values_label.setText(f"verbose_logging={bool(verbose)} | demo_mode={mode}")

    refresh_btn = DatalensButton("Log current prefs", theme, ButtonVariant.SECONDARY, box)
    layout.addWidget(refresh_btn, 2, 0)

    def log_snapshot() -> None:
        app_ctx = get_app_context()
        snap = app_ctx.preferences.snapshot()
        log.info(
            "Widget test plugin preferences snapshot",
            extra={"plugin_id": "widget_test", "operation": "plugin_prefs", "phase": "snapshot", "snapshot": snap},
        )

    refresh_btn.clicked.connect(lambda *_: log_snapshot())

    try:
        unsub = get_app_context().preferences.subscribe(_WIDGET_TEST_PLUGIN_ID, lambda *_: refresh())
        box.destroyed.connect(lambda *_: unsub())
    except Exception:
        log.debug("Failed to subscribe widget_test prefs demo (best-effort)", exc_info=True)

    return box


__all__ = ["build_preferences_demo_section"]

