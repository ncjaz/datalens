from __future__ import annotations

from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QWidget

from datalens.core.logging import get_logger
from datalens.ui.widgets.core.checkboxes import DatalensCheckBox

from ..service import CameraDevice, CameraKind

log = get_logger(__name__)


def on_depth_stream_toggled(self) -> None:
    # RealSense depth requires stream reconfiguration; keep the interaction
    # explicit by gating it to "stopped" state.
    try:
        status = self._service.status()
        if str(status.get("status")) in {"starting", "running"}:
            try:
                self._rs_depth_toggle.blockSignals(True)
                self._rs_depth_toggle.set_current_id("disabled", emit=False)
            finally:
                self._rs_depth_toggle.blockSignals(False)
            self._publish_status("Stop the camera to toggle the depth stream.")
            return
    except Exception:
        log.debug(
            "Failed to read capture status while toggling depth stream (best-effort)",
            exc_info=True,
            extra={"operation": "capture", "phase": "rs_depth_toggle_status_error"},
        )

    depth_enabled = bool(self._rs_depth_toggle.current_id == "enabled")
    if not depth_enabled and getattr(self, "_stream_mode", "rgb") == "depth":
        self._stream_mode_toggle.set_current_id("rgb", emit=False)
        set_stream_mode(self, "rgb")

    self._refresh_controls()


def set_stream_mode(self, mode: str) -> None:
    mode_s = str(mode or "").strip().lower()
    if mode_s not in {"rgb", "depth"}:
        mode_s = "rgb"

    allow_depth = False
    try:
        device = self._device_combo.currentData()
        depth_enabled = bool(self._rs_depth_toggle.current_id == "enabled")
        allow_depth = bool(
            isinstance(device, CameraDevice) and device.kind == CameraKind.REALSENSE and depth_enabled
        )
    except Exception:
        allow_depth = False

    if mode_s == "depth" and not allow_depth:
        mode_s = "rgb"
        self._stream_mode_toggle.set_current_id("rgb", emit=False)

    self._stream_mode = mode_s
    try:
        self._settings_group.setTitle("Depth Settings" if mode_s == "depth" else "RGB Settings")
        self._rgb_options_scroll.setVisible(mode_s != "depth")
        self._depth_options_scroll.setVisible(mode_s == "depth")
    except Exception:
        log.debug(
            "Failed to update settings panel visibility (best-effort)",
            exc_info=True,
            extra={"operation": "capture", "phase": "stream_mode_ui_error", "mode": str(mode_s)},
        )


def build_depth_visualization_controls(self) -> None:
    self._clear_form_layout(self._depth_options_layout)

    self._depth_auto_scale = DatalensCheckBox("Auto-scale depth range", self._theme, self._depth_options_widget)
    self._depth_auto_scale.setChecked(True)
    self._depth_auto_scale.setToolTip(
        "Automatically adjust depth range for visualization.\n"
        "When enabled, uses either percentile or min/max values from the current frame.\n"
        "When disabled, uses fixed near/far distances."
    )
    self._depth_auto_scale.toggled.connect(lambda *_: sync_depth_visualization_controls(self))
    self._depth_options_layout.addRow("", self._depth_auto_scale)

    self._depth_use_percentiles = DatalensCheckBox("Use percentiles for auto-scale", self._theme, self._depth_options_widget)
    self._depth_use_percentiles.setChecked(True)
    self._depth_use_percentiles.setToolTip(
        "Use percentile-based range calculation instead of min/max.\n"
        "Percentiles (default 1% to 99%) filter out outliers for better visualization.\n"
        "Disabled: uses absolute minimum and maximum depth values in the frame."
    )
    self._depth_use_percentiles.toggled.connect(lambda *_: sync_depth_visualization_controls(self))
    self._depth_options_layout.addRow("", self._depth_use_percentiles)

    perc_row = QWidget(self._depth_options_widget)
    perc_layout = QHBoxLayout(perc_row)
    perc_layout.setContentsMargins(0, 0, 0, 0)
    perc_layout.setSpacing(8)

    self._depth_percentile_low = QDoubleSpinBox(perc_row)
    self._depth_percentile_low.setRange(0.0, 100.0)
    self._depth_percentile_low.setSingleStep(0.5)
    self._depth_percentile_low.setValue(1.0)
    self._depth_percentile_low.setSuffix("%")
    self._depth_percentile_low.setToolTip(
        "Lower percentile threshold (default 1%).\n"
        "Depth values below this percentile are clamped to black in visualization.\n"
        "Higher values increase contrast by ignoring closer objects."
    )

    self._depth_percentile_high = QDoubleSpinBox(perc_row)
    self._depth_percentile_high.setRange(0.0, 100.0)
    self._depth_percentile_high.setSingleStep(0.5)
    self._depth_percentile_high.setValue(99.0)
    self._depth_percentile_high.setSuffix("%")
    self._depth_percentile_high.setToolTip(
        "Upper percentile threshold (default 99%).\n"
        "Depth values above this percentile are clamped to white in visualization.\n"
        "Lower values increase contrast by ignoring farther objects."
    )

    perc_layout.addWidget(self._depth_percentile_low, 1)
    perc_layout.addWidget(self._depth_percentile_high, 1)
    self._depth_options_layout.addRow("Percentiles", perc_row)

    self._depth_manual_near_m = QDoubleSpinBox(self._depth_options_widget)
    self._depth_manual_near_m.setRange(0.0, 20.0)
    self._depth_manual_near_m.setSingleStep(0.05)
    self._depth_manual_near_m.setValue(0.2)
    self._depth_manual_near_m.setSuffix(" m")
    self._depth_manual_near_m.setToolTip(
        "Closest distance for manual range (default 0.2 m).\n"
        "Objects at or closer than this distance appear black.\n"
        "Only used when auto-scale is disabled."
    )
    self._depth_options_layout.addRow("Near", self._depth_manual_near_m)

    self._depth_manual_far_m = QDoubleSpinBox(self._depth_options_widget)
    self._depth_manual_far_m.setRange(0.0, 20.0)
    self._depth_manual_far_m.setSingleStep(0.05)
    self._depth_manual_far_m.setValue(2.0)
    self._depth_manual_far_m.setSuffix(" m")
    self._depth_manual_far_m.setToolTip(
        "Farthest distance for manual range (default 2.0 m).\n"
        "Objects at or farther than this distance appear white.\n"
        "Only used when auto-scale is disabled."
    )
    self._depth_options_layout.addRow("Far", self._depth_manual_far_m)

    sync_depth_visualization_controls(self)


def sync_depth_visualization_controls(self) -> None:
    auto = bool(self._depth_auto_scale.isChecked())
    try:
        self._depth_use_percentiles.setEnabled(bool(auto))
        self._depth_percentile_low.setEnabled(bool(auto and self._depth_use_percentiles.isChecked()))
        self._depth_percentile_high.setEnabled(bool(auto and self._depth_use_percentiles.isChecked()))
        self._depth_manual_near_m.setEnabled(bool(not auto))
        self._depth_manual_far_m.setEnabled(bool(not auto))
    except Exception:
        log.debug(
            "Failed to sync depth visualization controls (best-effort)",
            exc_info=True,
            extra={"operation": "capture", "phase": "depth_vis_sync_error"},
        )


def render_depth_to_rgb(self, depth_u16) -> object:
    """
    Convert a depth frame (uint16 mm) into an RGB888 preview image (grayscale).

    Best-effort; returns a uint8 HxWx3 array-like object.
    """
    import numpy as np

    d = np.asarray(depth_u16)
    h, w = int(d.shape[0]), int(d.shape[1])
    if h <= 0 or w <= 0:
        return np.zeros((1, 1, 3), dtype=np.uint8)

    valid = d > 0
    if not bool(valid.any()):
        return np.zeros((h, w, 3), dtype=np.uint8)

    if bool(self._depth_auto_scale.isChecked()):
        vals = d[valid].astype(np.float32, copy=False)
        if bool(self._depth_use_percentiles.isChecked()):
            lo_p = float(self._depth_percentile_low.value())
            hi_p = float(self._depth_percentile_high.value())
            lo = float(np.percentile(vals, lo_p))
            hi = float(np.percentile(vals, hi_p))
        else:
            lo = float(vals.min())
            hi = float(vals.max())
    else:
        lo = float(self._depth_manual_near_m.value()) * 1000.0
        hi = float(self._depth_manual_far_m.value()) * 1000.0

    if hi <= lo:
        hi = lo + 1.0

    df = d.astype(np.float32, copy=False)
    norm = (df - lo) / (hi - lo)
    norm = np.clip(norm, 0.0, 1.0)
    u8 = (norm * 255.0).astype(np.uint8)
    u8[~valid] = 0
    return np.repeat(u8[:, :, None], 3, axis=2)


__all__ = [
    "build_depth_visualization_controls",
    "on_depth_stream_toggled",
    "render_depth_to_rgb",
    "set_stream_mode",
    "sync_depth_visualization_controls",
]

