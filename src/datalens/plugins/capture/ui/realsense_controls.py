from __future__ import annotations

import threading

from PySide6.QtWidgets import QComboBox, QLabel

from datalens.core.logging import get_logger
from datalens.ui.widgets.core import DatalensCheckBox
from datalens.ui.widgets.core.slider_option import DatalensSliderOption

from ..service import CameraDevice, CameraKind, CameraOptionSpec, RealSenseColorProfile

log = get_logger(__name__)


def on_realsense_rgb_option_changed(self, *, serial: str, option_id: str, value: object) -> None:
    try:
        self._service.set_realsense_option(serial=serial, sensor="rgb", option_id=str(option_id), value=value)  # type: ignore[arg-type]
    except Exception:
        log.debug(
            "Failed to apply RealSense option update (best-effort)",
            exc_info=True,
            extra={
                "operation": "capture",
                "phase": "rs_option_update_failed",
                "serial": str(serial),
                "option": str(option_id),
            },
        )
    self._apply_auto_option_states()


def refresh_realsense_metadata_async(self, *, serial: str) -> None:
    serial_s = str(serial or "").strip()
    if not serial_s:
        return
    if self._rs_metadata_refresh_inflight:
        return
    self._rs_metadata_refresh_inflight = True

    def work() -> tuple[tuple[RealSenseColorProfile, ...], tuple[CameraOptionSpec, ...]]:
        profiles = self._service.enumerate_realsense_color_profiles(serial=serial_s)
        options = self._service.enumerate_realsense_rgb_options(serial=serial_s)
        return profiles, options

    def apply(result: tuple[tuple[RealSenseColorProfile, ...], tuple[CameraOptionSpec, ...]]) -> None:
        self._rs_metadata_refresh_inflight = False
        try:
            current = self._device_combo.currentData()
        except Exception:
            current = None
        if not (isinstance(current, CameraDevice) and current.kind == CameraKind.REALSENSE):
            return
        if str(getattr(current, "serial", "") or "").strip() != serial_s:
            return

        profiles, options = result
        self._apply_realsense_profiles(profiles)
        self._rebuild_rgb_settings_from_specs(options, serial=serial_s)
        self._refresh_controls()

    def runner() -> None:
        try:
            result = work()
        except Exception:
            log.debug(
                "Failed to refresh RealSense metadata (best-effort)",
                exc_info=True,
                extra={"operation": "capture", "phase": "rs_metadata_error", "serial": serial_s},
            )
            result = ((), ())
        self._ui_invoke.invoke.emit(lambda: apply(result))

    threading.Thread(target=runner, name=f"CaptureRealSenseMeta({serial_s})", daemon=True).start()


def apply_realsense_profiles(self, profiles: tuple[RealSenseColorProfile, ...]) -> None:
    self._rs_profiles = tuple(profiles or ())
    by_format: dict[str, list[RealSenseColorProfile]] = {}
    lookup: dict[tuple[str, int, int, int], RealSenseColorProfile] = {}
    for p in self._rs_profiles:
        fmt = str(getattr(p, "format", "") or "").strip().lower()
        if not fmt:
            continue
        by_format.setdefault(fmt, []).append(p)
        lookup[(fmt, int(p.width), int(p.height), int(p.fps))] = p

    self._rs_profiles_by_format = {k: tuple(v) for k, v in by_format.items()}
    self._rs_profile_lookup = lookup

    # Load saved profile preference for this device (if available)
    try:
        device = self._device_combo.currentData()
        device_id = str(getattr(device, "serial", "") or "").strip()
    except Exception:
        device_id = ""

    saved_fmt, saved_res, saved_fps = None, None, None
    if device_id:
        try:
            saved_fmt, saved_res, saved_fps = self._load_realsense_profile_preference(device_id)
            if saved_fmt or saved_res or saved_fps:
                log.debug(
                    "Loaded RealSense profile preference",
                    extra={
                        "operation": "capture",
                        "phase": "load_rs_profile_pref",
                        "device_id": device_id,
                        "format": saved_fmt,
                        "resolution": saved_res,
                        "fps": saved_fps,
                    },
                )
        except Exception:
            log.debug(
                "Failed to load RealSense profile preference (best-effort)",
                exc_info=True,
                extra={"operation": "capture", "phase": "load_rs_profile_pref_error", "device_id": device_id},
            )

    # Determine target profile: prefer saved preference, fall back to smart default
    target = None
    target_fmt = None
    target_res = None
    target_fps = None

    # Try to match saved preference
    if saved_fmt and saved_res and saved_fps:
        key = (saved_fmt.lower(), saved_res[0], saved_res[1], saved_fps)
        target = lookup.get(key)
        if target:
            target_fmt = saved_fmt.lower()
            target_res = saved_res
            target_fps = saved_fps
            log.debug(
                "Using saved RealSense profile",
                extra={
                    "operation": "capture",
                    "phase": "use_saved_rs_profile",
                    "device_id": device_id,
                    "format": target_fmt,
                    "resolution": target_res,
                    "fps": target_fps,
                },
            )

    # Fall back to smart default if no saved preference or saved preference not available
    if not target:
        target = self._select_default_realsense_profile(prior=self._rs_selected_profile)
        target_fmt = str(getattr(target, "format", "") or "").strip().lower() if target is not None else ""
        target_res = (int(target.width), int(target.height)) if target is not None else None
        target_fps = int(target.fps) if target is not None else None

    formats = sorted(self._rs_profiles_by_format.keys())
    preferred_fmt = self._pick_preferred_realsense_format(formats)
    if not target_fmt:
        target_fmt = preferred_fmt

    try:
        self._rs_format_combo.blockSignals(True)
        self._rs_resolution_combo.blockSignals(True)
        self._rs_fps_combo.blockSignals(True)

        self._rs_format_combo.clear()
        if not formats:
            self._rs_format_combo.addItem("Default", "")
        else:
            for fmt in formats:
                self._rs_format_combo.addItem(str(fmt).upper(), fmt)

        # Set preferred/target format if present.
        fmt_index = 0
        for idx in range(self._rs_format_combo.count()):
            if str(self._rs_format_combo.itemData(idx) or "") == target_fmt:
                fmt_index = idx
                break
        self._rs_format_combo.setCurrentIndex(fmt_index)

        fmt = str(self._rs_format_combo.currentData() or "").strip().lower()
        self._populate_rs_resolutions(fmt, selected_resolution=target_res)
        res = self._rs_resolution_combo.currentData()
        self._populate_rs_fps(fmt, res, selected_fps=target_fps)

        self._update_selected_rs_profile()
    finally:
        self._rs_format_combo.blockSignals(False)
        self._rs_resolution_combo.blockSignals(False)
        self._rs_fps_combo.blockSignals(False)


def on_rs_format_changed(self) -> None:
    fmt = str(self._rs_format_combo.currentData() or "").strip().lower()
    self._populate_rs_resolutions(fmt, selected_resolution=None)
    self._on_rs_resolution_changed()


def on_rs_resolution_changed(self) -> None:
    fmt = str(self._rs_format_combo.currentData() or "").strip().lower()
    res = self._rs_resolution_combo.currentData()
    self._populate_rs_fps(fmt, res, selected_fps=None)
    self._on_rs_fps_changed()


def on_rs_fps_changed(self) -> None:
    self._update_selected_rs_profile()


def update_selected_rs_profile(self) -> None:
    fmt = str(self._rs_format_combo.currentData() or "").strip().lower()
    res = self._rs_resolution_combo.currentData()
    fps = self._rs_fps_combo.currentData()
    if not (isinstance(res, tuple) and len(res) == 2 and fps is not None):
        self._rs_selected_profile = None
        return
    key = (fmt, int(res[0]), int(res[1]), int(fps))
    self._rs_selected_profile = self._rs_profile_lookup.get(key)

    # Save RealSense profile preference for this device
    try:
        device = self._device_combo.currentData()
        device_id = str(getattr(device, "serial", "") or "").strip()
        if device_id and fmt and res and fps is not None:
            self._save_realsense_profile_preference(device_id, fmt, int(res[0]), int(res[1]), int(fps))
    except Exception:
        log.debug(
            "Failed to save RealSense profile preference (best-effort)",
            exc_info=True,
            extra={"operation": "capture", "phase": "save_rs_profile_pref_error"},
        )


def populate_rs_resolutions(self, fmt: str, *, selected_resolution: tuple[int, int] | None) -> None:
    fmt_s = str(fmt or "").strip().lower()
    profiles = self._rs_profiles_by_format.get(fmt_s, ())
    resolutions = sorted(
        {(int(p.width), int(p.height)) for p in profiles},
        key=lambda r: (r[0] * r[1], r[0], r[1]),
    )

    self._rs_resolution_combo.clear()
    if not resolutions:
        self._rs_resolution_combo.addItem("Default", None)
        self._rs_resolution_combo.setCurrentIndex(0)
        return

    for w, h in resolutions:
        self._rs_resolution_combo.addItem(f"{w} x {h}", (w, h))

    index = len(resolutions) - 1  # default to largest (V1 behavior)
    if selected_resolution and tuple(selected_resolution) in resolutions:
        index = resolutions.index(tuple(selected_resolution))
    self._rs_resolution_combo.setCurrentIndex(index)


def populate_rs_fps(self, fmt: str, resolution: object, *, selected_fps: int | None) -> None:
    fmt_s = str(fmt or "").strip().lower()
    res = resolution if isinstance(resolution, tuple) and len(resolution) == 2 else None
    if res is None:
        self._rs_fps_combo.clear()
        self._rs_fps_combo.addItem("Default", None)
        self._rs_fps_combo.setCurrentIndex(0)
        return

    profiles = self._rs_profiles_by_format.get(fmt_s, ())
    fps_values = sorted({int(p.fps) for p in profiles if (int(p.width), int(p.height)) == (int(res[0]), int(res[1]))})

    self._rs_fps_combo.clear()
    if not fps_values:
        self._rs_fps_combo.addItem("Default", None)
        self._rs_fps_combo.setCurrentIndex(0)
        return

    for fps in fps_values:
        self._rs_fps_combo.addItem(f"{fps} FPS", int(fps))

    index = len(fps_values) - 1  # default to highest FPS (V1 behavior)
    if selected_fps is not None and int(selected_fps) in fps_values:
        index = fps_values.index(int(selected_fps))
    self._rs_fps_combo.setCurrentIndex(index)


def pick_preferred_realsense_format(self, formats: list[str]) -> str:
    # Prefer RGB8 like V1; fall back to other common formats.
    candidates = ("rgb8", "bgr8", "rgba8", "bgra8")
    normalized = {str(f).strip().lower() for f in formats if str(f).strip()}
    for c in candidates:
        if c in normalized:
            return c
    return next(iter(normalized), "")


def select_default_realsense_profile(self, *, prior: RealSenseColorProfile | None) -> RealSenseColorProfile | None:
    if prior is not None:
        fmt = str(getattr(prior, "format", "") or "").strip().lower()
        key = (fmt, int(prior.width), int(prior.height), int(prior.fps))
        restored = self._rs_profile_lookup.get(key)
        if restored is not None:
            return restored

    formats = sorted(self._rs_profiles_by_format.keys())
    fmt = self._pick_preferred_realsense_format(formats)
    profiles = self._rs_profiles_by_format.get(fmt, ())
    if not profiles:
        return None

    # Choose the largest resolution, then highest FPS.
    resolutions = sorted({(int(p.width), int(p.height)) for p in profiles}, key=lambda r: (r[0] * r[1], r[0], r[1]))
    if not resolutions:
        return None
    best_res = resolutions[-1]
    fps_values = sorted({int(p.fps) for p in profiles if (int(p.width), int(p.height)) == best_res})
    if not fps_values:
        return None
    best_fps = fps_values[-1]
    return self._rs_profile_lookup.get((fmt, int(best_res[0]), int(best_res[1]), int(best_fps)))


def rebuild_rgb_settings_from_specs(self, specs: tuple[CameraOptionSpec, ...], *, serial: str) -> None:
    self._clear_form_layout(self._rgb_options_layout)
    self._rs_option_widgets.clear()

    entries = [s for s in (specs or ()) if isinstance(s, CameraOptionSpec) and s.sensor == "rgb"]
    if not entries:
        label = QLabel("No RGB settings reported by this device.", self._rgb_options_widget)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.70)}; font-size: 11px;")
        self._rgb_options_layout.addRow("", label)
        return

    # Organize settings: auto-related first, then manual settings (matching webcam UX)
    # Auto-related pairs: (manual_setting_id, auto_checkbox_id)
    auto_pairs: dict[str, str] = {
        "exposure": "enable_auto_exposure",
        "white_balance": "enable_auto_white_balance",
    }

    by_id: dict[str, CameraOptionSpec] = {str(s.id): s for s in entries}

    # Priority order: manual settings that have auto toggles come first
    priority_ids: list[str] = []
    for manual_id in auto_pairs.keys():
        if manual_id in by_id:
            priority_ids.append(manual_id)

    # Build ordered list: priority settings first, then remaining
    ordered: list[CameraOptionSpec] = []
    seen: set[str] = set()

    for spec_id in priority_ids:
        spec = by_id.get(spec_id)
        if spec is not None and spec_id not in seen:
            ordered.append(spec)
            seen.add(spec_id)
            # Mark the auto toggle as seen so it doesn't get added separately
            auto_id = auto_pairs.get(spec_id)
            if auto_id:
                seen.add(auto_id)

    # Add remaining settings (exclude auto toggles that were paired)
    for spec in entries:
        if str(spec.id) not in seen:
            ordered.append(spec)
            seen.add(str(spec.id))

    # Helper to wrap a manual control with an auto button (matching webcam UX)
    def _wrap_with_auto_button(manual_widget: QWidget, manual_spec: CameraOptionSpec, auto_spec: CameraOptionSpec) -> QWidget:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QHBoxLayout, QWidget
        from datalens.ui.widgets.core import create_icon_button
        from datalens.ui.widgets.icons.auto_icon import auto_icon

        row = QWidget(self._rgb_options_widget)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        row_layout.addWidget(manual_widget, 1)

        btn = create_icon_button(self._theme, row, checkable=True)
        btn.setObjectName("CaptureAutoOptionButton")

        def update_icon(checked_state: bool) -> None:
            bg = self._theme.confirm_color if checked_state else self._theme.cancel_color
            btn.setIcon(auto_icon(self._theme, size=18, background_color=bg))

        def update_tooltip(checked_state: bool) -> None:
            state = "Enabled" if checked_state else "Disabled"
            action = "disable" if checked_state else "enable"
            btn.setToolTip(f"Auto: {state}\nClick to {action} auto")

        # Set initial state from auto spec
        auto_enabled = bool(auto_spec.current) if auto_spec.current is not None else True
        btn.setChecked(auto_enabled)
        manual_widget.setEnabled(not auto_enabled)
        update_icon(auto_enabled)
        update_tooltip(auto_enabled)

        def on_toggled(checked_state: bool) -> None:
            self._on_realsense_rgb_option_changed(serial=serial, option_id=str(auto_spec.id), value=bool(checked_state))
            manual_widget.setEnabled(not checked_state)
            update_icon(checked_state)
            update_tooltip(checked_state)
            if not checked_state:
                # Re-apply the current manual value when leaving auto
                if isinstance(manual_widget, DatalensSliderOption):
                    try:
                        self._on_realsense_rgb_option_changed(
                            serial=serial, option_id=str(manual_spec.id), value=float(manual_widget.value())
                        )
                    except Exception:
                        pass

        btn.toggled.connect(on_toggled)
        row_layout.addWidget(btn, 0, alignment=Qt.AlignVCenter)

        # Store both widgets for state management
        self._rs_option_widgets[str(manual_spec.id)] = manual_widget
        self._rs_option_widgets[str(auto_spec.id)] = btn

        return row

    # Build UI rows in priority order
    for spec in ordered:
        # Check if this manual setting has an auto toggle
        auto_id = auto_pairs.get(str(spec.id))
        auto_spec = by_id.get(auto_id) if auto_id else None

        if spec.kind == "bool":
            cb = DatalensCheckBox("", self._theme, self._rgb_options_widget)
            if spec.current is not None:
                cb.setChecked(bool(spec.current))
            cb.toggled.connect(
                lambda checked, opt_id=str(spec.id): self._on_realsense_rgb_option_changed(
                    serial=serial, option_id=opt_id, value=bool(checked)
                )
            )
            self._rgb_options_layout.addRow(str(spec.label), cb)
            self._rs_option_widgets[str(spec.id)] = cb
            continue

        if spec.kind == "enum":
            combo = QComboBox(self._rgb_options_widget)
            for value, label in spec.enum_items:
                combo.addItem(str(label), int(value))
            if spec.current is not None:
                # Best-effort: select by value.
                for idx in range(combo.count()):
                    if combo.itemData(idx) == int(spec.current):
                        combo.setCurrentIndex(idx)
                        break
            combo.currentIndexChanged.connect(
                lambda _=0, opt_id=str(spec.id), w=combo: self._on_realsense_rgb_option_changed(
                    serial=serial, option_id=opt_id, value=int(w.currentData())
                )
            )
            self._rgb_options_layout.addRow(str(spec.label), combo)
            self._rs_option_widgets[str(spec.id)] = combo
            continue

        if spec.kind == "float" and spec.range is not None:
            mn, mx, step, default = spec.range
            slider = DatalensSliderOption(
                self._theme,
                self._rgb_options_widget,
                float(mn),
                float(mx),
                float(step) if float(step) != 0 else 1.0,
                default_value=float(default),
            )
            if spec.current is not None:
                slider.setValue(float(spec.current))
            slider.valueChanged.connect(
                lambda value, opt_id=str(spec.id): self._on_realsense_rgb_option_changed(
                    serial=serial, option_id=opt_id, value=float(value)
                )
            )

            # If this manual setting has an auto toggle, wrap with auto button
            if auto_spec is not None:
                wrapped = _wrap_with_auto_button(slider, spec, auto_spec)
                self._rgb_options_layout.addRow(str(spec.label), wrapped)
            else:
                self._rgb_options_layout.addRow(str(spec.label), slider)
                self._rs_option_widgets[str(spec.id)] = slider
            continue

        label = QLabel("Unsupported", self._rgb_options_widget)
        label.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.65)}; font-size: 11px;")
        self._rgb_options_layout.addRow(str(spec.label), label)

    self._apply_auto_option_states()


def apply_auto_option_states(self) -> None:
    """
    Apply auto option states to manual controls.

    Note: For manual settings with auto buttons (exposure, white_balance),
    the enable/disable logic is handled directly in the auto button wrapper.
    This function handles any remaining standalone auto checkboxes.
    """
    from PySide6.QtWidgets import QPushButton

    mapping = {
        "enable_auto_exposure": "exposure",
        "enable_auto_white_balance": "white_balance",
    }
    for auto_id, manual_id in mapping.items():
        auto_w = self._rs_option_widgets.get(auto_id)
        manual_w = self._rs_option_widgets.get(manual_id)
        if auto_w is None or manual_w is None:
            continue
        try:
            enabled = True
            # Auto button (new UI pattern)
            if isinstance(auto_w, QPushButton) and auto_w.isCheckable():
                enabled = not bool(auto_w.isChecked())
            # Auto checkbox (legacy pattern)
            elif isinstance(auto_w, DatalensCheckBox):
                enabled = not bool(auto_w.isChecked())
            manual_w.setEnabled(bool(enabled))
        except Exception:
            continue


__all__ = [
    "apply_auto_option_states",
    "apply_realsense_profiles",
    "on_realsense_rgb_option_changed",
    "on_rs_fps_changed",
    "on_rs_format_changed",
    "on_rs_resolution_changed",
    "pick_preferred_realsense_format",
    "populate_rs_fps",
    "populate_rs_resolutions",
    "rebuild_rgb_settings_from_specs",
    "refresh_realsense_metadata_async",
    "select_default_realsense_profile",
    "update_selected_rs_profile",
]
