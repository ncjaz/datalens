from __future__ import annotations

import os
import threading
import time

from PySide6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QImage, QPixmap

from datalens.core.logging import get_logger
from datalens.ui.widgets.core.buttons import ButtonVariant
from datalens.ui.widgets.color_picker import ColorValue

from ..service import CameraDevice, CameraKind
from .workspace_constants import (
    _CAPTURE_PLUGIN_ID,
    _SETTING_PREVIEW_BORDER_CAPTURE_COLOR,
    _SETTING_PREVIEW_BORDER_CAPTURE_FADE_MS,
    _SETTING_PREVIEW_BORDER_OFF_COLOR,
    _SETTING_PREVIEW_BORDER_ON_COLOR,
    _SETTING_SAVE_DEPTH,
)

log = get_logger(__name__)


def populate_devices_async(self, *, show_scanning: bool, min_spin_ms: int = 0) -> None:
    """
    Populate the camera list without blocking the UI thread.

    OpenCV device probing can be slow on some systems/backends, so do it in
    a short-lived background thread and apply results on the UI thread.
    """
    prior = None
    prior_id = ""
    try:
        prior = self._device_combo.currentData()
        prior_id = str(getattr(prior, "device_id", "")) if prior is not None else ""
    except Exception:
        prior = None
        prior_id = ""

    if show_scanning:
        try:
            if self._device_combo.count() <= 0:
                self._device_combo.addItem("Scanning for cameras...", None)
            else:
                self._device_combo.setItemText(0, "Scanning for cameras...")
            self._device_combo.setCurrentIndex(0)
            self._device_combo.setEnabled(False)
        except Exception:
            pass

    def work() -> tuple[str, list[object]]:
        try:
            raw = os.environ.get("DATALENS_CAPTURE_MAX_INDICES", "8")
            try:
                max_indices = int(raw)
            except Exception:
                max_indices = 8
            max_indices = max(1, min(32, int(max_indices)))

            # Default policy:
            # - initial population: "indices" (fast, no LED blinking)
            # - explicit refresh (button click): "probe" (try to find real devices)
            # - continuous auto-refresh: "probe" (user opted in)
            had_prior = bool(getattr(self, "_device_ids", ()))
            default_mode = "probe" if (getattr(self, "_auto_refresh_enabled", False) or (show_scanning and had_prior)) else "indices"
            mode = os.environ.get("DATALENS_CAPTURE_ENUMERATION_MODE", default_mode).strip().lower() or default_mode
            timeout_raw = os.environ.get("DATALENS_CAPTURE_PROBE_TIMEOUT_S", "0.75")
            try:
                probe_timeout_s = float(timeout_raw)
            except Exception:
                probe_timeout_s = 0.75
            probe_timeout_s = max(0.05, min(3.0, probe_timeout_s))

            devices = list(
                self._service.enumerate_devices(
                    max_indices=max_indices,
                    mode=mode,  # "probe" by default (no phantom devices)
                    probe_timeout_s=probe_timeout_s,
                )
            )
            return str(mode), devices
        except Exception:
            log.debug("Device enumeration failed (best-effort)", exc_info=True)
            return "error", []

    def apply(mode: str, devices: list[object]) -> None:
        if self._disposed:
            return
        try:
            self._device_refresh_inflight = False

            elapsed_ms = int((time.monotonic() - float(self._refresh_spin_started_at_s)) * 1000.0)
            remaining_ms = max(0, int(self._refresh_min_spin_ms) - elapsed_ms)

            if not self._auto_refresh_enabled:
                if remaining_ms > 0:
                    QTimer.singleShot(remaining_ms, self._stop_refresh_animation)
                else:
                    self._stop_refresh_animation()

            device_ids = tuple(str(getattr(d, "device_id", "")) for d in devices)
            if show_scanning:
                log.info(
                    "Device scan results",
                    extra={
                        "operation": "capture",
                        "phase": "scan_results",
                        "count": len(devices),
                        "mode": str(mode),
                        "device_ids": list(device_ids),
                    },
                )

            have_valid_devices = bool(devices) and not any(not x for x in device_ids)
            if not have_valid_devices:
                # Avoid wiping a previously good list if a probe fails transiently.
                if self._device_ids and self._device_combo.count() > 0:
                    try:
                        if str(mode) == "probe" and show_scanning and all(str(x).startswith("cv_") for x in self._device_ids):
                            self._device_combo.setItemText(0, f"{len(self._device_ids)} camera index(es) available")
                        else:
                            self._device_combo.setItemText(0, f"{len(self._device_ids)} camera(s) found")
                        if prior_id and prior_id in self._device_ids:
                            self._device_combo.setCurrentIndex(1 + self._device_ids.index(prior_id))
                        else:
                            self._device_combo.setCurrentIndex(1 if self._device_combo.count() > 1 else 0)
                        self._device_combo.setEnabled(True)
                    except Exception:
                        pass
                    if show_scanning:
                        if str(mode) == "probe":
                            self._publish_status("No cameras detected by probe; keeping previous list.")
                        else:
                            self._publish_status("No cameras found on refresh; keeping previous list.")
                    return

                self._device_combo.clear()
                self._device_ids = ()
                self._device_combo.addItem("No cameras found", None)
                self._device_combo.setEnabled(False)
                return

            if (not show_scanning) and device_ids == self._device_ids and self._device_combo.count() > 0:
                self._device_combo.setEnabled(True)
                return

            self._device_combo.clear()
            self._device_ids = device_ids
            self._device_combo.setEnabled(True)
            count = len(devices)
            if str(mode) == "indices":
                self._device_combo.addItem(f"{count} camera index(es) available", None)
            else:
                self._device_combo.addItem(f"{count} camera(s) found", None)
            for d in devices:
                self._device_combo.addItem(getattr(d, "display_name", "Camera"), d)
            if prior_id and prior_id in device_ids:
                self._device_combo.setCurrentIndex(1 + device_ids.index(prior_id))
            else:
                self._device_combo.setCurrentIndex(1 if count > 0 else 0)
        except Exception:
            self._device_refresh_inflight = False
            self._stop_refresh_animation()
            try:
                self._device_combo.clear()
                self._device_combo.addItem("Camera scan failed (see logs)", None)
                self._device_combo.setEnabled(False)
            except Exception:
                pass
            log.warning(
                "Failed to apply device list",
                exc_info=True,
                extra={"operation": "capture", "phase": "apply_devices_error"},
            )

    def runner() -> None:
        mode, devices = work()
        self._ui_invoke.invoke.emit(lambda: apply(mode, devices))

    self._device_refresh_inflight = True
    self._start_refresh_animation(min_spin_ms=min_spin_ms)
    threading.Thread(target=runner, name="CaptureDeviceEnumerate", daemon=True).start()


def on_start_stop_clicked(self) -> None:
    try:
        if self._service.status().get("status") == "starting":
            self._publish_status("Camera is starting...")
            return
    except Exception:
        pass

    if self._service.is_running():
        self._service.stop_async()
        try:
            self._preview_label.setPixmap(QPixmap())
            self._preview_label.setText("No camera connected")
        except Exception:
            pass
        self._publish_status("Stopping camera...")
        return

    current = self._device_combo.currentData()
    device = current if isinstance(current, CameraDevice) else None
    if device is None:
        self._publish_status("No camera available.")
        return
    log.info(
        "Start requested from UI",
        extra={
            "operation": "capture",
            "phase": "ui_start",
            "device_id": getattr(device, "device_id", None),
            "device_kind": getattr(device, "kind", None).value if getattr(device, "kind", None) else None,
            "device_label": str(self._device_combo.currentText()),
        },
    )
    if self._auto_refresh_enabled:
        self._set_auto_refresh(False, immediate=False)
    if getattr(device, "kind", None) == CameraKind.REALSENSE:
        enable_depth = False
        align_depth = False
        try:
            enable_depth = bool(self._rs_depth_toggle.current_id == "enabled")
            align_depth = bool(self._rs_depth_align_toggle.current_id == "aligned")
        except Exception:
            enable_depth = False
            align_depth = False
        ok = self._service.start_async(
            device=device,
            realsense_profile=self._rs_selected_profile,
            enable_depth=enable_depth,
            align_depth_to_color=align_depth,
        )
    else:
        ok = self._service.start_async(device=device)
    if ok:
        self._publish_status("Starting camera...")
    else:
        self._publish_status("Camera is already starting/running.")


def on_device_selected(self) -> None:
    try:
        device = self._device_combo.currentData()
    except Exception:
        device = None

    if isinstance(device, CameraDevice) and getattr(device, "kind", None) == CameraKind.WEBCAM:
        self._show_webcam_settings(device=device)
        return

    is_rs = bool(isinstance(device, CameraDevice) and getattr(device, "kind", None) == CameraKind.REALSENSE)
    serial = str(getattr(device, "serial", "") or "").strip() if is_rs else ""

    for w in (
        self._rs_format_label,
        self._rs_format_combo,
        self._rs_resolution_label,
        self._rs_resolution_combo,
        self._rs_fps_label,
        self._rs_fps_combo,
        self._rs_depth_label,
        self._rs_depth_toggle,
        self._rs_depth_align_label,
        self._rs_depth_align_toggle,
    ):
        w.setVisible(bool(is_rs))

    if not is_rs:
        self._rs_selected_profile = None
        self._rs_profiles = ()
        self._rs_profiles_by_format = {}
        self._rs_profile_lookup = {}
        try:
            self._rs_format_combo.blockSignals(True)
            self._rs_resolution_combo.blockSignals(True)
            self._rs_fps_combo.blockSignals(True)
            self._rs_format_combo.clear()
            self._rs_resolution_combo.clear()
            self._rs_fps_combo.clear()
        finally:
            self._rs_format_combo.blockSignals(False)
            self._rs_resolution_combo.blockSignals(False)
            self._rs_fps_combo.blockSignals(False)

        try:
            self._rs_depth_toggle.blockSignals(True)
            self._rs_depth_toggle.set_current_id("disabled", emit=False)
        finally:
            self._rs_depth_toggle.blockSignals(False)

        self._rebuild_rgb_settings_placeholder()
        current_mode = getattr(self, "_stream_mode", "rgb")
        if current_mode in ("depth", "overlay"):
            self._stream_mode_toggle.set_current_id("rgb", emit=False)
            self._set_stream_mode("rgb")
        return

    # Load saved colormap and depth alignment preferences for this device
    if serial:
        try:
            # Load colormap preference
            saved_colormap = self._load_colormap_preference(serial)
            try:
                self._depth_colormap_combo.blockSignals(True)
                for idx in range(self._depth_colormap_combo.count()):
                    if str(self._depth_colormap_combo.itemData(idx) or "") == saved_colormap:
                        self._depth_colormap_combo.setCurrentIndex(idx)
                        log.debug(
                            "Loaded colormap preference",
                            extra={
                                "operation": "capture",
                                "phase": "load_colormap_pref",
                                "device_id": serial,
                                "colormap": saved_colormap,
                            },
                        )
                        break
            finally:
                self._depth_colormap_combo.blockSignals(False)

            # Load depth alignment preference
            saved_alignment = self._load_depth_alignment_preference(serial)
            try:
                self._rs_depth_align_toggle.blockSignals(True)
                self._rs_depth_align_toggle.set_current_id(saved_alignment, emit=False)
                log.debug(
                    "Loaded depth alignment preference",
                    extra={
                        "operation": "capture",
                        "phase": "load_depth_alignment_pref",
                        "device_id": serial,
                        "alignment": saved_alignment,
                    },
                )
            finally:
                self._rs_depth_align_toggle.blockSignals(False)
        except Exception:
            log.debug(
                "Failed to load device preferences (best-effort)",
                exc_info=True,
                extra={"operation": "capture", "phase": "load_device_prefs_error", "device_id": serial},
            )

    self._rebuild_rgb_settings_placeholder()
    self._refresh_realsense_metadata_async(serial=serial)


def refresh_controls(self) -> None:
    try:
        status = self._service.status()
        running = status.get("status") == "running"
        starting = status.get("status") == "starting"
        error = status.get("status") == "error"
        has_project = bool(self._app_ctx.has_project)
        has_frame = bool(status.get("has_frame"))
        want_rgb = bool(self._save_formats.is_checked("rgb"))
        want_depth = bool(self._save_formats.is_checked("depth"))

        try:
            device = self._device_combo.currentData()
            supports_depth = bool(isinstance(device, CameraDevice) and getattr(device, "kind", None) == CameraKind.REALSENSE)
        except Exception:
            device = None
            supports_depth = False

        try:
            depth_enabled = bool(self._rs_depth_toggle.current_id == "enabled")
            supports_depth = bool(supports_depth and depth_enabled)
        except Exception:
            supports_depth = False

        self._save_formats.set_option_enabled("depth", bool(supports_depth))
        if supports_depth:
            if (not getattr(self, "_save_depth_pref_present", False)) and (not self._save_formats.is_checked("depth")):
                self._save_formats.set_checked("depth", True, emit=False)
                self._save_depth_pref_present = True
                try:
                    self._save_user_preference(_SETTING_SAVE_DEPTH, True)
                except Exception:
                    pass
                log.info(
                    "Defaulted Save Depth to enabled",
                    extra={
                        "operation": "capture",
                        "phase": "save_depth_default",
                        "device_id": str(getattr(device, "device_id", "")) if device is not None else "",
                    },
                )
        else:
            if want_depth:
                self._save_formats.set_checked("depth", False, emit=False)

        want_depth = bool(self._save_formats.is_checked("depth"))

        if running:
            if self._start_stop.text() != "Stop":
                self._start_stop.setText("Stop")
            if self._start_stop_variant is not ButtonVariant.CANCEL:
                self._start_stop.set_variant(ButtonVariant.CANCEL)
                self._start_stop_variant = ButtonVariant.CANCEL
        elif starting:
            if self._start_stop.text() != "Starting…":
                self._start_stop.setText("Starting…")
            if self._start_stop_variant is not ButtonVariant.CONFIRM:
                self._start_stop.set_variant(ButtonVariant.CONFIRM)
                self._start_stop_variant = ButtonVariant.CONFIRM
        else:
            if self._start_stop.text() != "Start":
                self._start_stop.setText("Start")
            if self._start_stop_variant is not ButtonVariant.CONFIRM:
                self._start_stop.set_variant(ButtonVariant.CONFIRM)
                self._start_stop_variant = ButtonVariant.CONFIRM

        if running or starting:
            self._start_stop.setEnabled(True)
        else:
            try:
                selected = self._device_combo.currentData()
                has_selection = isinstance(selected, CameraDevice)
            except Exception:
                has_selection = False
            self._start_stop.setEnabled(bool(self._device_combo.isEnabled() and has_selection))
        try:
            self._refresh_btn.setEnabled(bool(not starting and not running))
        except Exception:
            pass
        if not starting and not running:
            self._sync_auto_refresh_from_sources(immediate=False)

        try:
            project_root = str(self._app_ctx.project_root) if has_project else None
        except Exception:
            project_root = None
        if project_root and project_root != self._last_project_root_seen:
            self._last_project_root_seen = project_root
            try:
                self._output_dir_edit.setText(str(self._default_output_dir() or ""))
            except Exception:
                pass

        out_rel = self._current_output_dir_rel() if has_project else None
        abs_out = self._current_output_dir_abs()
        valid_out = bool(abs_out) if abs_out is not None and str(abs_out).strip() else bool(out_rel)
        try:
            # Allow changing save directory while streaming.
            self._output_dir_edit.setEnabled(True)
            self._browse_output_btn.setEnabled(bool(not starting))
        except Exception:
            pass

        self._capture_btn.setEnabled(bool(has_frame and running and (want_rgb or want_depth) and valid_out))

        if error:
            msg = str(status.get("error") or "Camera error.")
            self._preview_label.setText(msg)

        depth_stream_enabled = bool(supports_depth)
        try:
            self._stream_mode_toggle.set_option_enabled("depth", bool(depth_stream_enabled))
            self._stream_mode_toggle.set_option_enabled("overlay", bool(depth_stream_enabled))
            current_mode = getattr(self, "_stream_mode", "rgb")
            if not depth_stream_enabled and current_mode in ("depth", "overlay"):
                self._stream_mode_toggle.set_current_id("rgb", emit=False)
                self._set_stream_mode("rgb")
        except Exception:
            pass

        rs_controls_enabled = bool(not starting and not running)
        try:
            for w in (self._rs_format_combo, self._rs_resolution_combo, self._rs_fps_combo, self._rs_depth_toggle, self._rs_depth_align_toggle):
                w.setEnabled(bool(rs_controls_enabled))
        except Exception:
            pass

        refresh_border(self)
    except Exception:
        if not self._controls_error_logged:
            self._controls_error_logged = True
            log.exception("Capture UI control refresh failed; stopping status timer")
        try:
            self._status_timer.stop()
        except Exception:
            pass


def refresh_border(self) -> None:
    def _stop_anim() -> None:
        anim = getattr(self, "_preview_border_fade_anim", None)
        if anim is None:
            return
        try:
            self._preview_border_fade_anim = None
        except Exception:
            pass
        try:
            anim.stop()
        except Exception:
            pass
        try:
            anim.deleteLater()
        except Exception:
            pass

    def _rgba(c: QColor) -> str:
        return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"

    def _resolve_color_pref(key: str, *, fallback_hex: str, fallback_opacity: float) -> QColor:
        try:
            raw = self._app_ctx.preferences.get(_CAPTURE_PLUGIN_ID, key, default=None)
        except Exception:
            raw = None

        if isinstance(raw, dict):
            try:
                value = ColorValue.from_dict(raw)
                base = QColor(value.color)
                if value.theme_reference:
                    ref = str(value.theme_reference).strip()
                    try:
                        resolved_hex = getattr(self._theme, ref)
                    except Exception:
                        resolved_hex = None
                    if isinstance(resolved_hex, str) and resolved_hex.strip():
                        base = QColor(resolved_hex.strip())
                base.setAlphaF(max(0.0, min(1.0, float(value.opacity))))
                return base
            except Exception:
                pass

        base = QColor(str(fallback_hex))
        base.setAlphaF(max(0.0, min(1.0, float(fallback_opacity))))
        return base

    status = self._service.status()
    running = status.get("status") == "running"
    has_frame = bool(status.get("has_frame"))
    stream_on = bool(running and has_frame)

    if not stream_on:
        _stop_anim()
        try:
            self._preview_border_override_color = None
        except Exception:
            pass
        border_color = _resolve_color_pref(_SETTING_PREVIEW_BORDER_OFF_COLOR, fallback_hex=self._theme.cancel_border, fallback_opacity=1.0)
    else:
        override = getattr(self, "_preview_border_override_color", None)
        if isinstance(override, QColor):
            border_color = QColor(override)
        else:
            border_color = _resolve_color_pref(_SETTING_PREVIEW_BORDER_ON_COLOR, fallback_hex=self._theme.confirm_border, fallback_opacity=0.25)

    self._preview_frame.setStyleSheet(
        f"""
        QFrame#CapturePreviewFrame {{
            border: 2px solid {_rgba(border_color)};
            border-radius: 10px;
            background-color: {self._theme.settings.background_color};
        }}
        """
    )


def flash_capture_border(self) -> None:
    """
    Flash the preview border after a capture, then fade back to the streaming border.

    This mirrors the V1 capture feedback pattern, but is preference-driven.
    """
    status = self._service.status()
    running = status.get("status") == "running"
    has_frame = bool(status.get("has_frame"))
    if not (running and has_frame):
        return

    try:
        raw_ms = self._app_ctx.preferences.get(_CAPTURE_PLUGIN_ID, _SETTING_PREVIEW_BORDER_CAPTURE_FADE_MS, default=1000)
        duration_ms = int(raw_ms) if isinstance(raw_ms, (int, float, str)) else 1000
    except Exception:
        duration_ms = 1000
    duration_ms = max(0, min(5000, int(duration_ms)))

    def _resolve_color_pref(key: str, *, fallback_hex: str, fallback_opacity: float) -> QColor:
        try:
            raw = self._app_ctx.preferences.get(_CAPTURE_PLUGIN_ID, key, default=None)
        except Exception:
            raw = None

        if isinstance(raw, dict):
            try:
                value = ColorValue.from_dict(raw)
                base = QColor(value.color)
                if value.theme_reference:
                    ref = str(value.theme_reference).strip()
                    try:
                        resolved_hex = getattr(self._theme, ref)
                    except Exception:
                        resolved_hex = None
                    if isinstance(resolved_hex, str) and resolved_hex.strip():
                        base = QColor(resolved_hex.strip())
                base.setAlphaF(max(0.0, min(1.0, float(value.opacity))))
                return base
            except Exception:
                pass

        base = QColor(str(fallback_hex))
        base.setAlphaF(max(0.0, min(1.0, float(fallback_opacity))))
        return base

    capture = _resolve_color_pref(_SETTING_PREVIEW_BORDER_CAPTURE_COLOR, fallback_hex=self._theme.confirm_border, fallback_opacity=1.0)
    target = _resolve_color_pref(_SETTING_PREVIEW_BORDER_ON_COLOR, fallback_hex=self._theme.confirm_border, fallback_opacity=0.25)

    try:
        prior = getattr(self, "_preview_border_fade_anim", None)
        if prior is not None:
            prior.stop()
            prior.deleteLater()
    except Exception:
        pass
    try:
        self._preview_border_fade_anim = None
    except Exception:
        pass

    if duration_ms <= 0:
        try:
            self._preview_border_override_color = None
        except Exception:
            pass
        refresh_border(self)
        return

    start = QColor(capture)
    end = QColor(target)

    def _lerp_byte(a: int, b: int, t: float) -> int:
        return int(round(a + (b - a) * t))

    def _blend(t: float) -> QColor:
        t = max(0.0, min(1.0, float(t)))
        out = QColor(
            _lerp_byte(start.red(), end.red(), t),
            _lerp_byte(start.green(), end.green(), t),
            _lerp_byte(start.blue(), end.blue(), t),
            _lerp_byte(start.alpha(), end.alpha(), t),
        )
        return out

    try:
        self._preview_border_override_color = QColor(start)
    except Exception:
        pass
    refresh_border(self)

    anim = QVariantAnimation(self)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(int(duration_ms))
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def _on_value_changed(v: object) -> None:
        try:
            t = float(v)
        except Exception:
            t = 0.0
        try:
            self._preview_border_override_color = _blend(t)
        except Exception:
            pass
        refresh_border(self)

    def _on_finished() -> None:
        try:
            self._preview_border_override_color = None
        except Exception:
            pass
        refresh_border(self)
        try:
            anim.deleteLater()
        except Exception:
            pass

    anim.valueChanged.connect(_on_value_changed)
    anim.finished.connect(_on_finished)
    try:
        self._preview_border_fade_anim = anim
    except Exception:
        pass
    anim.start()


def blend_rgb_depth_overlay(rgb_frame, depth_colorized):
    """
    Blend RGB and colorized depth frames with alpha compositing.

    IMPORTANT: When using RealSense "Aligned to RGB" mode, depth and RGB frames
    should already be the same resolution. This function will NOT resize aligned
    frames - mismatched sizes indicate a configuration issue.

    Args:
        rgb_frame: HxWx3 uint8 RGB array (original camera frame)
        depth_colorized: HxWx3 uint8 RGB array (colorized depth)

    Returns:
        HxWx3 uint8 RGB array (blended overlay)
    """
    import numpy as np

    # Verify both frames are same size (required for correct overlay)
    if rgb_frame.shape != depth_colorized.shape:
        # This should NOT happen when using RealSense aligned mode
        log.warning(
            "RGB and depth frame size mismatch in overlay mode",
            extra={
                "operation": "capture",
                "phase": "overlay_blend_size_mismatch",
                "rgb_shape": rgb_frame.shape,
                "depth_shape": depth_colorized.shape,
            },
        )
        # Fallback: return RGB only (do NOT resize, as it would create incorrect overlay)
        return rgb_frame

    # Alpha blend: overlay = rgb * (1 - alpha) + depth * alpha
    # Use 50% opacity for depth overlay (adjustable in future)
    alpha = 0.5

    rgb_f = rgb_frame.astype(np.float32)
    depth_f = depth_colorized.astype(np.float32)

    blended = rgb_f * (1.0 - alpha) + depth_f * alpha
    return blended.astype(np.uint8)


def refresh_preview(self) -> None:
    if not self._view_active:
        return
    frame = self._service.get_latest()
    if frame is None:
        return

    mode = getattr(self, "_stream_mode", "rgb")

    # RGB mode: show color frame only
    if mode == "rgb":
        try:
            rgb = frame.rgb
            h, w = int(rgb.shape[0]), int(rgb.shape[1])
            bytes_per_line = int(rgb.strides[0])
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
            pix = QPixmap.fromImage(qimg)
            self._preview_label.setPixmap(pix.scaled(self._preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            log.debug("Failed to update preview (best-effort)", exc_info=True)
        return

    # Depth and Overlay modes require depth data
    try:
        depth = getattr(frame, "depth", None)
        if depth is None:
            self._preview_label.setPixmap(QPixmap())
            self._preview_label.setText("Depth stream not available")
            return

        import numpy as np

        d = np.asarray(depth)
        if d.ndim != 2:
            self._preview_label.setText("Depth frame unsupported")
            return

        # Render depth with selected colormap
        depth_rgb = self._render_depth_to_rgb(d)

        # Depth mode: show colorized depth only
        if mode == "depth":
            h, w = int(depth_rgb.shape[0]), int(depth_rgb.shape[1])
            bytes_per_line = int(depth_rgb.strides[0])
            qimg = QImage(depth_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
            pix = QPixmap.fromImage(qimg)
            self._preview_label.setPixmap(pix.scaled(self._preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            return

        # Overlay mode: blend RGB and colorized depth
        if mode == "overlay":
            try:
                rgb = frame.rgb
                overlay = blend_rgb_depth_overlay(rgb, depth_rgb)
                h, w = int(overlay.shape[0]), int(overlay.shape[1])
                bytes_per_line = int(overlay.strides[0])
                qimg = QImage(overlay.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
                pix = QPixmap.fromImage(qimg)
                self._preview_label.setPixmap(pix.scaled(self._preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception:
                log.debug("Failed to update overlay preview (best-effort)", exc_info=True)
            return

    except Exception:
        log.debug("Failed to update depth/overlay preview (best-effort)", exc_info=True)


__all__ = [
    "blend_rgb_depth_overlay",
    "flash_capture_border",
    "on_device_selected",
    "on_start_stop_clicked",
    "populate_devices_async",
    "refresh_border",
    "refresh_controls",
    "refresh_preview",
]
