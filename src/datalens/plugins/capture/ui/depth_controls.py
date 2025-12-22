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
    if mode_s not in {"rgb", "depth", "overlay"}:
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

    # Depth and Overlay modes require depth sensor to be enabled
    if mode_s in ("depth", "overlay") and not allow_depth:
        mode_s = "rgb"
        self._stream_mode_toggle.set_current_id("rgb", emit=False)

    self._stream_mode = mode_s
    try:
        # Update settings panel visibility (depth first, then RGB)
        if mode_s == "rgb":
            # RGB mode: show only RGB settings
            self._depth_settings_group.setVisible(False)
            self._rgb_settings_group.setVisible(True)
        elif mode_s == "depth":
            # Depth mode: show only depth settings
            self._depth_settings_group.setVisible(True)
            self._rgb_settings_group.setVisible(False)
        elif mode_s == "overlay":
            # Overlay mode: show both (depth first, then RGB)
            self._depth_settings_group.setVisible(True)
            self._rgb_settings_group.setVisible(True)
    except Exception:
        log.debug(
            "Failed to update settings panel visibility (best-effort)",
            exc_info=True,
            extra={"operation": "capture", "phase": "stream_mode_ui_error", "mode": str(mode_s)},
        )


def build_depth_visualization_controls(self) -> None:
    self._clear_form_layout(self._depth_options_layout)

    from PySide6.QtWidgets import QComboBox

    self._depth_colormap_combo = QComboBox(self._depth_options_widget)
    self._depth_colormap_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    self._depth_colormap_combo.addItem("Grayscale", "grayscale")
    self._depth_colormap_combo.addItem("Jet", "jet")
    self._depth_colormap_combo.addItem("Viridis", "viridis")
    self._depth_colormap_combo.addItem("Plasma", "plasma")
    self._depth_colormap_combo.addItem("Turbo", "turbo")
    self._depth_colormap_combo.addItem("Inferno", "inferno")
    self._depth_colormap_combo.setToolTip(
        "Select color map for depth visualization.\n"
        "Grayscale: Black (near) to white (far)\n"
        "Jet: Blue (near) → Cyan → Green → Yellow → Red (far)\n"
        "Viridis/Plasma/Inferno: Perceptually uniform scientific colormaps\n"
        "Turbo: Improved rainbow colormap with better contrast"
    )
    self._depth_options_layout.addRow("Colormap", self._depth_colormap_combo)

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


def apply_colormap(normalized_u8, colormap: str, valid_mask) -> object:
    """
    Apply a colormap to normalized uint8 depth values.

    Args:
        normalized_u8: uint8 HxW array (0-255)
        colormap: colormap name ("grayscale", "jet", "viridis", etc.)
        valid_mask: boolean HxW array indicating valid depth pixels

    Returns:
        uint8 HxWx3 RGB array
    """
    import numpy as np

    h, w = int(normalized_u8.shape[0]), int(normalized_u8.shape[1])

    if colormap == "grayscale":
        # Grayscale: replicate to 3 channels
        rgb = np.repeat(normalized_u8[:, :, None], 3, axis=2)
    elif colormap == "jet":
        # Jet colormap: blue → cyan → green → yellow → red
        rgb = apply_jet_colormap(normalized_u8)
    elif colormap == "viridis":
        rgb = apply_viridis_colormap(normalized_u8)
    elif colormap == "plasma":
        rgb = apply_plasma_colormap(normalized_u8)
    elif colormap == "inferno":
        rgb = apply_inferno_colormap(normalized_u8)
    elif colormap == "turbo":
        rgb = apply_turbo_colormap(normalized_u8)
    else:
        # Fallback to grayscale
        rgb = np.repeat(normalized_u8[:, :, None], 3, axis=2)

    # Set invalid pixels to black
    rgb[~valid_mask] = 0

    return rgb


def apply_jet_colormap(u8) -> object:
    """Apply Jet colormap: blue → cyan → green → yellow → red"""
    import numpy as np

    # Normalize to [0, 1]
    norm = u8.astype(np.float32) / 255.0

    r = np.clip(1.5 - np.abs(2.0 * norm - 1.0) * 4.0, 0, 1)
    g = np.clip(1.5 - np.abs(2.0 * norm - 0.5) * 4.0, 0, 1)
    b = np.clip(1.5 - np.abs(2.0 * norm) * 4.0, 0, 1)

    rgb = np.stack([r, g, b], axis=2)
    return (rgb * 255.0).astype(np.uint8)


def apply_viridis_colormap(u8) -> object:
    """Apply Viridis colormap (perceptually uniform)"""
    import numpy as np

    # Simplified Viridis approximation
    norm = u8.astype(np.float32) / 255.0

    # Viridis: purple → blue → green → yellow
    r = np.clip(np.where(norm < 0.5, 0.28 * norm, 0.14 + 1.72 * (norm - 0.5)), 0, 1)
    g = np.clip(np.where(norm < 0.5, 1.6 * norm, 0.8 + 0.4 * (norm - 0.5)), 0, 1)
    b = np.clip(np.where(norm < 0.5, 0.5 + 1.0 * norm, 1.0 - 1.4 * (norm - 0.5)), 0, 1)

    rgb = np.stack([r, g, b], axis=2)
    return (rgb * 255.0).astype(np.uint8)


def apply_plasma_colormap(u8) -> object:
    """Apply Plasma colormap (perceptually uniform)"""
    import numpy as np

    # Simplified Plasma approximation
    norm = u8.astype(np.float32) / 255.0

    # Plasma: dark blue → purple → orange → yellow
    r = np.clip(np.where(norm < 0.5, 1.6 * norm, 0.8 + 0.4 * (norm - 0.5)), 0, 1)
    g = np.clip(np.where(norm < 0.5, 0.2 * norm, 0.1 + 1.8 * (norm - 0.5)), 0, 1)
    b = np.clip(np.where(norm < 0.5, 0.8 + 0.4 * norm, 1.0 - 2.0 * (norm - 0.5)), 0, 1)

    rgb = np.stack([r, g, b], axis=2)
    return (rgb * 255.0).astype(np.uint8)


def apply_inferno_colormap(u8) -> object:
    """Apply Inferno colormap (perceptually uniform)"""
    import numpy as np

    # Simplified Inferno approximation
    norm = u8.astype(np.float32) / 255.0

    # Inferno: black → purple → red → orange → yellow
    r = np.clip(np.where(norm < 0.5, 2.0 * norm, 1.0), 0, 1)
    g = np.clip(np.where(norm < 0.5, 0.0, 2.0 * (norm - 0.5)), 0, 1)
    b = np.clip(np.where(norm < 0.3, norm / 0.3, 1.0 - 2.0 * (norm - 0.3)), 0, 1)

    rgb = np.stack([r, g, b], axis=2)
    return (rgb * 255.0).astype(np.uint8)


def apply_turbo_colormap(u8) -> object:
    """Apply Turbo colormap (improved rainbow)"""
    import numpy as np

    # Simplified Turbo approximation (improved Jet)
    norm = u8.astype(np.float32) / 255.0

    # Turbo: blue → cyan → green → yellow → orange → red
    r = np.clip(np.where(norm < 0.5, 0.13 + 1.74 * norm, 1.0), 0, 1)
    g = np.clip(np.where(norm < 0.5, 1.6 * norm, 1.0 - 1.4 * (norm - 0.5)), 0, 1)
    b = np.clip(np.where(norm < 0.5, 0.9 - 1.8 * norm, 0.0), 0, 1)

    rgb = np.stack([r, g, b], axis=2)
    return (rgb * 255.0).astype(np.uint8)


def render_depth_to_rgb(self, depth_u16) -> object:
    """
    Convert a depth frame (uint16 mm) into an RGB888 preview image with selected colormap.

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

    # Apply colormap
    colormap = str(self._depth_colormap_combo.currentData() or "grayscale")
    return apply_colormap(u8, colormap, valid)


__all__ = [
    "apply_colormap",
    "apply_inferno_colormap",
    "apply_jet_colormap",
    "apply_plasma_colormap",
    "apply_turbo_colormap",
    "apply_viridis_colormap",
    "build_depth_visualization_controls",
    "on_depth_stream_toggled",
    "render_depth_to_rgb",
    "set_stream_mode",
    "sync_depth_visualization_controls",
]

