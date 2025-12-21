from __future__ import annotations

import time

from PySide6.QtCore import Qt

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.ui.shortcuts.chords import chord_modifier_label, chord_to_modifiers
from datalens.ui.widgets.core.icon_button import apply_icon_button_theme
from datalens.ui.widgets.core.modifier_click import ModifierClickAction, ModifierClickRouter
from datalens.ui.widgets.icons.animated.refresh import RefreshAnimator

from ..ids import CAPTURE_GESTURE_AUTO_REFRESH_DEFAULT_CHORD, CAPTURE_GESTURE_AUTO_REFRESH_TOGGLE
from .workspace_constants import _CAPTURE_PLUGIN_ID, _DEFAULT_SCAN_MODE, _SETTING_SCAN_MODE

log = get_logger(__name__)


def set_refresh_button_accent(self, *, scanning: bool) -> None:
    """
    Set the refresh icon button accent.

    UX:
    - idle: tertiary (subtle)
    - scanning: primary (more visible feedback)
    """
    try:
        apply_icon_button_theme(
            self._refresh_btn,
            self._theme,
            accent_color=self._theme.primary_color if scanning else self._theme.tertiary_color,
            checked_solid=False,
        )
    except Exception:
        return


def subscribe_preferences(self) -> None:
    try:
        prior = self._prefs_unsub
        self._prefs_unsub = None
        if callable(prior):
            prior()
    except Exception:
        log.debug("Failed to unsubscribe prior preferences listener (best-effort)", exc_info=True)

    def on_changed(pid: PluginId, keys: set[str]) -> None:
        if self._disposed:
            return
        if str(pid) != str(_CAPTURE_PLUGIN_ID):
            return
        on_preferences_changed(self, keys)

    try:
        self._prefs_unsub = self._app_ctx.preferences.subscribe(_CAPTURE_PLUGIN_ID, on_changed)
    except Exception:
        self._prefs_unsub = None
        log.debug("Failed to subscribe to capture preferences (best-effort)", exc_info=True)


def on_preferences_changed(self, keys: set[str]) -> None:
    prefs = self._app_ctx.preferences
    if _SETTING_SCAN_MODE in keys:
        try:
            raw = prefs.get(_CAPTURE_PLUGIN_ID, _SETTING_SCAN_MODE, default=_DEFAULT_SCAN_MODE)
            mode = str(raw) if raw in ("manual", "auto") else _DEFAULT_SCAN_MODE
            if mode != self._scan_mode:
                self._scan_mode = mode
                sync_auto_refresh_from_sources(self, immediate=True)
        except Exception:
            log.debug("Failed to apply scan mode preference (best-effort)", exc_info=True)


def desired_auto_refresh_enabled(self) -> bool:
    """
    Return whether auto-refresh is *desired* (not whether it is currently active).

    Sources:
    - user preference `scan_mode` ("auto" enables it)
    - temporary UI override from modifier-click on the refresh button

    The refresh system still disables auto-refresh while capture is running.
    """
    if self._auto_refresh_override is not None:
        return bool(self._auto_refresh_override)
    return bool(self._scan_mode == "auto")


def sync_auto_refresh_from_sources(self, *, immediate: bool) -> None:
    """
    Sync the active auto-refresh state from preferences + temporary overrides.

    This keeps the UX consistent:
    - shift-click can enable continuous refresh temporarily
    - a normal click can clear the temporary override
    - user preferences remain the baseline (no "hidden toggles" in the main UI)
    """
    desired = desired_auto_refresh_enabled(self)
    running = False
    try:
        running = bool(self._service.is_running())
    except Exception:
        running = False

    enabled = bool(desired and self._view_active and not running)
    if enabled == self._auto_refresh_enabled and not immediate:
        try:
            update_refresh_tooltip(self)
        except Exception:
            pass
        return

    if log.isEnabledFor(10):  # logging.DEBUG
        log.debug(
            "Syncing auto-refresh state",
            extra={
                "operation": "capture",
                "phase": "sync_auto_refresh",
                "desired": bool(desired),
                "enabled": bool(enabled),
                "override": self._auto_refresh_override,
                "scan_mode": str(self._scan_mode),
                "view_active": bool(self._view_active),
                "capture_running": bool(running),
            },
        )

    set_auto_refresh(self, enabled, immediate=bool(immediate and enabled))


def effective_auto_refresh_toggle_chord(self) -> str:
    """
    Return the effective chord used to toggle auto-refresh via the Refresh button.

    This is a *gesture* binding (press/hold), not a globally dispatched command.
    """
    chord = self._app_ctx.shortcuts.get_effective_gesture_chord(
        plugin_id=_CAPTURE_PLUGIN_ID,
        gesture_id=str(CAPTURE_GESTURE_AUTO_REFRESH_TOGGLE),
        default=CAPTURE_GESTURE_AUTO_REFRESH_DEFAULT_CHORD,
    )
    return str(chord or "").strip()


def install_refresh_click_router(self) -> None:
    try:
        if self._refresh_click_router is not None:
            self._refresh_btn.removeEventFilter(self._refresh_click_router)
            self._refresh_click_router.deleteLater()
    except Exception:
        log.debug("Failed to remove prior refresh router (best-effort)", exc_info=True)
    chord = effective_auto_refresh_toggle_chord(self)
    modifier = chord_to_modifiers(chord)
    if modifier == Qt.NoModifier:
        modifier = Qt.ShiftModifier
        log.warning(
            "Auto-refresh modifier binding has no modifiers; falling back to Shift",
            extra={
                "operation": "capture",
                "phase": "modifier_fallback",
                "gesture_id": CAPTURE_GESTURE_AUTO_REFRESH_TOGGLE,
                "effective_chord": chord,
            },
        )
    elif log.isEnabledFor(10):  # logging.DEBUG
        log.debug(
            "Installing refresh modifier router",
            extra={
                "operation": "capture",
                "phase": "install_modifier_router",
                "gesture_id": CAPTURE_GESTURE_AUTO_REFRESH_TOGGLE,
                "effective_chord": chord,
            },
        )
    self._refresh_click_router = ModifierClickRouter(
        self._refresh_btn,
        actions=(
            ModifierClickAction(required_modifiers=modifier, callback=self._start_continuous_refresh_from_click),
            ModifierClickAction(
                required_modifiers=Qt.NoModifier,
                callback=self._refresh_once_from_click,
                exact_match=False,
            ),
        ),
        log_name="capture.refresh",
    )


def update_refresh_tooltip(self) -> None:
    chord = effective_auto_refresh_toggle_chord(self)
    mod = chord_modifier_label(chord) or "Shift"
    if self._auto_refresh_enabled and self._auto_refresh_override is not None:
        state = "ON (temporary)"
    else:
        state = "ON" if self._auto_refresh_enabled else "OFF"
    self._refresh_btn.setToolTip(
        f"Refresh devices\n"
        f"Click: refresh once\n"
        f"{mod}+Click: continuous refresh (currently {state})"
    )


def refresh_once_from_click(self) -> None:
    if self._auto_refresh_override is not None:
        prior = self._auto_refresh_override
        self._auto_refresh_override = None
        log.info(
            "Auto-refresh override cleared by normal click",
            extra={
                "operation": "capture",
                "phase": "ui_refresh_override_clear",
                "prior_override": prior,
            },
        )
        sync_auto_refresh_from_sources(self, immediate=False)

    if self._device_refresh_inflight:
        return
    log.debug("Manual device refresh requested", extra={"operation": "capture", "phase": "ui_refresh_once"})
    self._populate_devices_async(show_scanning=True, min_spin_ms=250)


def start_continuous_refresh_from_click(self) -> None:
    self._auto_refresh_override = True
    log.info(
        "Auto-refresh override enabled (modifier click)",
        extra={"operation": "capture", "phase": "ui_refresh_override_set", "enabled": True},
    )
    sync_auto_refresh_from_sources(self, immediate=True)


def set_auto_refresh(self, enabled: bool, *, immediate: bool = False) -> None:
    self._auto_refresh_enabled = bool(enabled)
    try:
        self._refresh_btn.setChecked(bool(enabled))
    except Exception:
        log.debug("Failed to update refresh button state (best-effort)", exc_info=True)
    update_refresh_tooltip(self)

    if not self._auto_refresh_enabled:
        self._device_refresh_timer.stop()
        stop_refresh_animation(self)
        return

    if self._view_active and not self._service.is_running():
        self._device_refresh_timer.start()
    if immediate and not self._device_refresh_inflight:
        self._populate_devices_async(show_scanning=False, min_spin_ms=250)


def maybe_refresh_devices(self) -> None:
    """
    Refresh the camera list when it is safe to do so.

    This provides a simple MVP "hot plug" behavior (V1-style) for webcams.
    We intentionally avoid refreshing while capture is running so we don't
    disrupt the selected device mid-stream.
    """
    if self._disposed or not self._view_active:
        return
    if not self._auto_refresh_enabled:
        return
    status = self._service.status()
    if str(status.get("status")) in {"starting", "running"}:
        return
    if self._device_refresh_inflight:
        return
    self._populate_devices_async(show_scanning=False)


def start_refresh_animation(self, *, min_spin_ms: int = 0) -> None:
    try:
        if self._refresh_animator is None:
            self._refresh_animator = RefreshAnimator(self._theme, size=18, parent=self)
        self._refresh_min_spin_ms = max(0, int(min_spin_ms))
        self._refresh_spin_started_at_s = time.monotonic()
        set_refresh_button_accent(self, scanning=True)
        self._refresh_animator.start(self._refresh_btn)
    except Exception:
        return


def stop_refresh_animation(self) -> None:
    try:
        if self._refresh_animator is not None:
            self._refresh_animator.stop()
        set_refresh_button_accent(self, scanning=False)
    except Exception:
        return


def subscribe_shortcuts(self) -> None:
    try:
        prior = self._shortcuts_unsub
        self._shortcuts_unsub = None
        if callable(prior):
            prior()
    except Exception:
        log.debug("Failed to unsubscribe prior shortcuts listener (best-effort)", exc_info=True)

    def on_changed() -> None:
        if self._disposed:
            return
        install_refresh_click_router(self)
        update_refresh_tooltip(self)

    try:
        self._shortcuts_unsub = self._app_ctx.shortcuts.subscribe_changed(on_changed)
    except Exception:
        self._shortcuts_unsub = None
        log.debug("Failed to subscribe to shortcuts changes (best-effort)", exc_info=True)


__all__ = [
    "desired_auto_refresh_enabled",
    "effective_auto_refresh_toggle_chord",
    "install_refresh_click_router",
    "maybe_refresh_devices",
    "on_preferences_changed",
    "refresh_once_from_click",
    "set_auto_refresh",
    "set_refresh_button_accent",
    "start_continuous_refresh_from_click",
    "start_refresh_animation",
    "stop_refresh_animation",
    "subscribe_preferences",
    "subscribe_shortcuts",
    "sync_auto_refresh_from_sources",
    "update_refresh_tooltip",
]

