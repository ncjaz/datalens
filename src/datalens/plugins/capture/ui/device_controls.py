from __future__ import annotations

import os
import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap

from datalens.core.logging import get_logger
from datalens.ui.widgets.core.buttons import ButtonVariant

from ..service import CameraDevice, CameraKind

log = get_logger(__name__)


def populate_devices_async(self, *, show_scanning: bool, min_spin_ms: int = 0) -> None:
    """
    Populate the camera list without blocking the UI thread.

    OpenCV device probing can be slow on some systems/backends, so do it in
    a short-lived background thread and apply results on the UI thread.
    """
    if show_scanning:
        try:
            self._device_combo.clear()
            self._device_combo.addItem("Scanning for cameras...", None)
            self._device_combo.setEnabled(False)
        except Exception:
            pass

    def work() -> list[object]:
        try:
            raw = os.environ.get("DATALENS_CAPTURE_MAX_INDICES", "1")
            try:
                max_indices = int(raw)
            except Exception:
                max_indices = 1
            max_indices = max(1, min(16, int(max_indices)))
            return list(self._service.enumerate_devices(max_indices=max_indices))
        except Exception:
            log.debug("Device enumeration failed (best-effort)", exc_info=True)
            return []

    def apply(devices: list[object]) -> None:
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
                        "device_ids": list(device_ids),
                    },
                )
            if not devices or any(not x for x in device_ids):
                if not show_scanning and self._device_ids and self._device_combo.count() > 0:
                    self._device_combo.setEnabled(True)
                    return
                self._device_combo.clear()
                self._device_ids = ()
                self._device_combo.addItem("No cameras found", None)
                self._device_combo.setEnabled(False)
                return

            if (not show_scanning) and device_ids == self._device_ids and self._device_combo.count() > 0:
                self._device_combo.setEnabled(True)
                return

            prior = self._device_combo.currentData()
            prior_id = str(getattr(prior, "device_id", "")) if prior is not None else ""

            self._device_combo.clear()
            self._device_ids = device_ids
            self._device_combo.setEnabled(True)
            count = len(devices)
            self._device_combo.addItem(f"{count} camera(s) found", None)
            for d in devices:
                self._device_combo.addItem(getattr(d, "display_name", "Camera"), d)
            if prior_id and prior_id in device_ids:
                self._device_combo.setCurrentIndex(1 + device_ids.index(prior_id))
            else:
                self._device_combo.setCurrentIndex(0)
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
        devices = work()
        self._ui_invoke.invoke.emit(lambda: apply(devices))

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
        try:
            enable_depth = bool(self._rs_depth_checkbox.isChecked())
        except Exception:
            enable_depth = False
        ok = self._service.start_async(
            device=device,
            realsense_profile=self._rs_selected_profile,
            enable_depth=enable_depth,
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
        self._rs_depth_checkbox,
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
            self._rs_depth_checkbox.blockSignals(True)
            self._rs_depth_checkbox.setChecked(False)
        finally:
            self._rs_depth_checkbox.blockSignals(False)

        self._rebuild_rgb_settings_placeholder()
        if getattr(self, "_stream_mode", "rgb") == "depth":
            self._stream_mode_toggle.set_current_id("rgb", emit=False)
            self._set_stream_mode("rgb")
        return

    try:
        self._settings_group.setTitle("RGB Settings")
    except Exception:
        pass

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
            self._output_dir_edit.setEnabled(True)
            self._browse_output_btn.setEnabled(bool(not starting and not running))
        except Exception:
            pass

        self._capture_btn.setEnabled(bool(has_frame and running and (want_rgb or want_depth) and valid_out))

        if error:
            msg = str(status.get("error") or "Camera error.")
            self._preview_label.setText(msg)

        try:
            device = self._device_combo.currentData()
            supports_depth = bool(isinstance(device, CameraDevice) and getattr(device, "kind", None) == CameraKind.REALSENSE)
        except Exception:
            supports_depth = False

        try:
            supports_depth = bool(supports_depth and self._rs_depth_checkbox.isChecked())
        except Exception:
            supports_depth = False
        self._save_formats.set_option_enabled("depth", bool(supports_depth))
        if not supports_depth and want_depth:
            self._save_formats.set_checked("depth", False, emit=False)

        depth_stream_enabled = False
        try:
            depth_stream_enabled = bool(supports_depth and self._rs_depth_checkbox.isChecked())
        except Exception:
            depth_stream_enabled = False
        try:
            self._stream_mode_toggle.set_option_enabled("depth", bool(depth_stream_enabled))
            if not depth_stream_enabled and getattr(self, "_stream_mode", "rgb") == "depth":
                self._stream_mode_toggle.set_current_id("rgb", emit=False)
                self._set_stream_mode("rgb")
        except Exception:
            pass

        rs_controls_enabled = bool(supports_depth and not starting and not running)
        try:
            for w in (self._rs_format_combo, self._rs_resolution_combo, self._rs_fps_combo, self._rs_depth_checkbox):
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
    status = self._service.status()
    running = status.get("status") == "running"
    has_frame = bool(status.get("has_frame"))

    if not running or not has_frame:
        border = self._theme.cancel_border
    else:
        border = self._theme.confirm_border

    self._preview_frame.setStyleSheet(
        f"""
        QFrame#CapturePreviewFrame {{
            border: 2px solid {border};
            border-radius: 10px;
            background-color: {self._theme.settings.background_color};
        }}
        """
    )


def refresh_preview(self) -> None:
    if not self._view_active:
        return
    frame = self._service.get_latest()
    if frame is None:
        return

    mode = getattr(self, "_stream_mode", "rgb")
    if mode != "depth":
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

        rgb = self._render_depth_to_rgb(d)
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        bytes_per_line = int(rgb.strides[0])
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
        pix = QPixmap.fromImage(qimg)
        self._preview_label.setPixmap(pix.scaled(self._preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
    except Exception:
        log.debug("Failed to update depth preview (best-effort)", exc_info=True)


__all__ = [
    "on_device_selected",
    "on_start_stop_clicked",
    "populate_devices_async",
    "refresh_border",
    "refresh_controls",
    "refresh_preview",
]
