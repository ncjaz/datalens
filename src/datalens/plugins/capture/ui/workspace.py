from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

from datalens.core.events import EventHub, StatusMessageRequested
from datalens.core.logging import get_logger
from datalens.ui.theme.app_theme import AppTheme

from . import auto_refresh_controls, depth_controls, device_controls, device_preferences, realsense_controls, save_controls, webcam_controls
from .workspace_constants import _CAPTURE_PLUGIN_ID, _DEFAULT_SCAN_MODE, _SETTING_SCAN_MODE
from .workspace_ui import CaptureWorkspaceUi

from ..service import CameraDevice, CameraKind, CameraOptionSpec, CaptureService, RealSenseColorProfile

log = get_logger(__name__)

class _UiInvoke(QObject):
    invoke = Signal(object)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.invoke.connect(self._on_invoke)

    @Slot(object)
    def _on_invoke(self, fn: object) -> None:
        if callable(fn):
            fn()


class CaptureWorkspaceWidget(CaptureWorkspaceUi):
    """
    Capture workspace UI (webcam MVP).

    Preview is rate-limited and runs only while this workspace is active (focused).
    Saving uses IoWriter + media index registration (requires open project).
    """

    def __init__(self, parent: QWidget, *, theme: AppTheme, app_ctx, service: CaptureService) -> None:
        super().__init__(parent)
        self._theme = theme
        self._app_ctx = app_ctx
        self._service = service
        self._view_active = True
        self._controls_error_logged = False
        self._device_refresh_inflight = False
        self._device_ids: tuple[str, ...] = ()
        self._auto_refresh_enabled = False  # Start in manual mode (one-shot scanning)
        self._scan_mode = _DEFAULT_SCAN_MODE
        self._auto_refresh_override: bool | None = None
        self._refresh_animator: RefreshAnimator | None = None
        self._refresh_min_spin_ms = 0
        self._refresh_spin_started_at_s = 0.0
        self._refresh_click_router: ModifierClickRouter | None = None
        self._disposed = False
        self._last_project_root_seen: str | None = None
        self.destroyed.connect(lambda *_: self._dispose())
        self._ui_invoke = _UiInvoke(self)
        self._prefs_unsub: Callable[[], None] | None = None
        self._shortcuts_unsub: Callable[[], None] | None = None

        # ------------------------------------------------------------------
        # UI (built in `workspace_ui.py` to keep this controller small)
        # ------------------------------------------------------------------

        self._rs_profiles: tuple[RealSenseColorProfile, ...] = ()
        self._rs_profiles_by_format: dict[str, tuple[RealSenseColorProfile, ...]] = {}
        self._rs_profile_lookup: dict[tuple[str, int, int, int], RealSenseColorProfile] = {}
        self._rs_selected_profile: RealSenseColorProfile | None = None
        self._rs_metadata_refresh_inflight = False

        self.build_ui(theme=theme)
        self._build_depth_visualization_controls()
        self._rebuild_rgb_settings_placeholder()

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(100)  # ~10 fps UI update
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._preview_timer.start()

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(250)
        self._status_timer.timeout.connect(self._refresh_controls)
        self._status_timer.start()

        # Device hot-plug refresh (best-effort). This is intentionally slow and
        # only runs when the workspace is visible and capture isn't running.
        self._device_refresh_timer = QTimer(self)
        self._device_refresh_timer.setInterval(2500)
        self._device_refresh_timer.timeout.connect(self._maybe_refresh_devices)
        self._device_refresh_timer.start()

        self._load_user_preferences()
        self._subscribe_shortcuts()
        self._install_refresh_click_router()
        self._sync_auto_refresh_from_sources(immediate=False)
        self._subscribe_preferences()

        self._populate_devices_async(show_scanning=True)
        self._refresh_controls()
        self._refresh_border()

    def _set_refresh_button_accent(self, *, scanning: bool) -> None:
        return auto_refresh_controls.set_refresh_button_accent(self, scanning=scanning)

    def _default_output_dir(self) -> Path | None:
        return save_controls.default_output_dir(self)

    def _current_output_dir_abs(self) -> Path | None:
        return save_controls.current_output_dir_abs(self)

    def _current_output_dir_rel(self) -> str | None:
        return save_controls.current_output_dir_rel(self)

    def _current_output_dir_info(self) -> tuple[Path | None, str | None]:
        return save_controls.current_output_dir_info(self)

    def _browse_output_dir(self) -> None:
        return save_controls.browse_output_dir(self)

    def _subscribe_preferences(self) -> None:
        return auto_refresh_controls.subscribe_preferences(self)

    def _on_preferences_changed(self, keys: set[str]) -> None:
        return auto_refresh_controls.on_preferences_changed(self, keys)

    def set_view_active(self, active: bool) -> None:
        self._view_active = bool(active)
        if self._view_active:
            self._preview_timer.start()
            self._sync_auto_refresh_from_sources(immediate=False)
        else:
            self._preview_timer.stop()
            self._device_refresh_timer.stop()

    def _load_user_preferences(self) -> None:
        try:
            prefs = self._app_ctx.preferences
            raw_scan_mode = prefs.get(_CAPTURE_PLUGIN_ID, _SETTING_SCAN_MODE, default=_DEFAULT_SCAN_MODE)
            self._scan_mode = str(raw_scan_mode) if raw_scan_mode in ("manual", "auto") else _DEFAULT_SCAN_MODE
        except Exception:
            log.debug("Failed to load capture plugin settings (best-effort)", exc_info=True)

    def _desired_auto_refresh_enabled(self) -> bool:
        return auto_refresh_controls.desired_auto_refresh_enabled(self)

    def _sync_auto_refresh_from_sources(self, *, immediate: bool) -> None:
        return auto_refresh_controls.sync_auto_refresh_from_sources(self, immediate=immediate)

    def _save_user_preference(self, key: str, value: object) -> None:
        try:
            self._app_ctx.preferences.set(_CAPTURE_PLUGIN_ID, str(key), value)
        except Exception:
            log.warning(
                "Failed to persist capture preference (best-effort)",
                exc_info=True,
                extra={"operation": "capture", "phase": "prefs_set_error", "key": str(key)},
            )

    # Device-specific preference helpers
    def _save_device_preference(self, device_id: str, setting: str, value: object) -> None:
        return device_preferences.save_device_preference(self, device_id, setting, value)

    def _load_device_preference(self, device_id: str, setting: str, default: object = None) -> object:
        return device_preferences.load_device_preference(self, device_id, setting, default)

    def _save_colormap_preference(self, device_id: str, colormap: str) -> None:
        return device_preferences.save_colormap_preference(self, device_id, colormap)

    def _load_colormap_preference(self, device_id: str) -> str:
        return device_preferences.load_colormap_preference(self, device_id)

    def _save_depth_alignment_preference(self, device_id: str, alignment: str) -> None:
        return device_preferences.save_depth_alignment_preference(self, device_id, alignment)

    def _load_depth_alignment_preference(self, device_id: str) -> str:
        return device_preferences.load_depth_alignment_preference(self, device_id)

    def _save_realsense_profile_preference(self, device_id: str, format_str: str, width: int, height: int, fps: int) -> None:
        return device_preferences.save_realsense_profile_preference(self, device_id, format_str, width, height, fps)

    def _load_realsense_profile_preference(self, device_id: str) -> tuple:
        return device_preferences.load_realsense_profile_preference(self, device_id)

    def _dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        try:
            prior = self._prefs_unsub
            self._prefs_unsub = None
            if callable(prior):
                prior()
        except Exception:
            log.debug("Failed to dispose capture preferences subscription (best-effort)", exc_info=True)
        try:
            prior = self._shortcuts_unsub
            self._shortcuts_unsub = None
            if callable(prior):
                prior()
        except Exception:
            log.debug("Failed to dispose capture shortcuts subscription (best-effort)", exc_info=True)

    def _subscribe_shortcuts(self) -> None:
        return auto_refresh_controls.subscribe_shortcuts(self)

    def _effective_auto_refresh_toggle_chord(self) -> str:
        return auto_refresh_controls.effective_auto_refresh_toggle_chord(self)

    def _install_refresh_click_router(self) -> None:
        return auto_refresh_controls.install_refresh_click_router(self)

    def _update_refresh_tooltip(self) -> None:
        return auto_refresh_controls.update_refresh_tooltip(self)

    def _refresh_once_from_click(self) -> None:
        return auto_refresh_controls.refresh_once_from_click(self)

    def _start_continuous_refresh_from_click(self) -> None:
        return auto_refresh_controls.start_continuous_refresh_from_click(self)

    def _set_auto_refresh(self, enabled: bool, *, immediate: bool = False) -> None:
        return auto_refresh_controls.set_auto_refresh(self, enabled, immediate=immediate)

    def _maybe_refresh_devices(self) -> None:
        return auto_refresh_controls.maybe_refresh_devices(self)

    def _start_refresh_animation(self, *, min_spin_ms: int = 0) -> None:
        return auto_refresh_controls.start_refresh_animation(self, min_spin_ms=min_spin_ms)

    def _stop_refresh_animation(self) -> None:
        return auto_refresh_controls.stop_refresh_animation(self)

    def _populate_devices_async(self, *, show_scanning: bool, min_spin_ms: int = 0) -> None:
        return device_controls.populate_devices_async(self, show_scanning=show_scanning, min_spin_ms=min_spin_ms)

    def _on_start_stop_clicked(self) -> None:
        return device_controls.on_start_stop_clicked(self)

    def _on_capture_clicked(self) -> None:
        return save_controls.on_capture_clicked(self)

    def on_capture_saved(self, *, relative_path: str) -> None:
        """
        Hook invoked after a capture file has been written to disk.

        Reserved for future use (e.g. syncing/transfer hooks). Keep it fast.
        """
        return

    # ------------------------------------------------------------------
    # Device + settings UI (V1-style RealSense controls)
    # ------------------------------------------------------------------

    def _on_device_selected(self) -> None:
        return device_controls.on_device_selected(self)

    def _show_webcam_settings(self, *, device: CameraDevice) -> None:
        return webcam_controls.show_webcam_settings(self, device=device)

    def _refresh_webcam_metadata_async(self, *, device: CameraDevice) -> None:
        return webcam_controls.refresh_webcam_metadata_async(self, device=device)

    def _rebuild_webcam_settings_from_specs(self, specs: tuple[CameraOptionSpec, ...], *, device: CameraDevice) -> None:
        return webcam_controls.rebuild_webcam_settings_from_specs(self, specs, device=device)

    def _on_realsense_rgb_option_changed(self, *, serial: str, option_id: str, value: object) -> None:
        return realsense_controls.on_realsense_rgb_option_changed(self, serial=serial, option_id=option_id, value=value)

    def _refresh_realsense_metadata_async(self, *, serial: str) -> None:
        return realsense_controls.refresh_realsense_metadata_async(self, serial=serial)

    def _apply_realsense_profiles(self, profiles: tuple[RealSenseColorProfile, ...]) -> None:
        return realsense_controls.apply_realsense_profiles(self, profiles)

    def _on_rs_format_changed(self) -> None:
        return realsense_controls.on_rs_format_changed(self)

    def _on_rs_resolution_changed(self) -> None:
        return realsense_controls.on_rs_resolution_changed(self)

    def _on_rs_fps_changed(self) -> None:
        return realsense_controls.on_rs_fps_changed(self)

    def _update_selected_rs_profile(self) -> None:
        return realsense_controls.update_selected_rs_profile(self)

    def _populate_rs_resolutions(self, fmt: str, *, selected_resolution: tuple[int, int] | None) -> None:
        return realsense_controls.populate_rs_resolutions(self, fmt, selected_resolution=selected_resolution)

    def _populate_rs_fps(self, fmt: str, resolution: object, *, selected_fps: int | None) -> None:
        return realsense_controls.populate_rs_fps(self, fmt, resolution, selected_fps=selected_fps)

    def _pick_preferred_realsense_format(self, formats: list[str]) -> str:
        return realsense_controls.pick_preferred_realsense_format(self, formats)

    def _select_default_realsense_profile(self, *, prior: RealSenseColorProfile | None) -> RealSenseColorProfile | None:
        return realsense_controls.select_default_realsense_profile(self, prior=prior)

    def _on_depth_stream_toggled(self) -> None:
        return depth_controls.on_depth_stream_toggled(self)

    def _set_stream_mode(self, mode: str) -> None:
        return depth_controls.set_stream_mode(self, mode)

    def _clear_form_layout(self, layout: QFormLayout) -> None:
        while layout.rowCount() > 0:
            layout.removeRow(0)

    def _rebuild_rgb_settings_placeholder(self) -> None:
        self._clear_form_layout(self._rgb_options_layout)
        self._rs_option_widgets.clear()

        try:
            device = self._device_combo.currentData()
        except Exception:
            device = None

        if isinstance(device, CameraDevice) and device.kind == CameraKind.REALSENSE:
            msg = "Scanning device options…"
        else:
            msg = "No camera settings available for this device."

        label = QLabel(msg, self._rgb_options_widget)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.70)}; font-size: 11px;")
        self._rgb_options_layout.addRow("", label)

    def _rebuild_rgb_settings_from_specs(self, specs: tuple[CameraOptionSpec, ...], *, serial: str) -> None:
        return realsense_controls.rebuild_rgb_settings_from_specs(self, specs, serial=serial)

    def _apply_auto_option_states(self) -> None:
        return realsense_controls.apply_auto_option_states(self)

    def _build_depth_visualization_controls(self) -> None:
        return depth_controls.build_depth_visualization_controls(self)

    def _sync_depth_visualization_controls(self) -> None:
        return depth_controls.sync_depth_visualization_controls(self)

    def _render_depth_to_rgb(self, depth_u16) -> object:
        return depth_controls.render_depth_to_rgb(self, depth_u16)

    def _refresh_controls(self) -> None:
        return device_controls.refresh_controls(self)

    def _refresh_border(self) -> None:
        return device_controls.refresh_border(self)

    def _refresh_preview(self) -> None:
        return device_controls.refresh_preview(self)

    def _publish_status(self, text: str) -> None:
        try:
            self._app_ctx.events.publish(
                EventHub.STATUS_MESSAGE_REQUESTED,
                StatusMessageRequested(text=str(text), timeout_ms=3000),
            )
        except Exception:
            pass


__all__ = ["CaptureWorkspaceWidget"]
