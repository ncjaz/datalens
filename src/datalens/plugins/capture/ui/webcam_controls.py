from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from datalens.core.logging import get_logger
from datalens.infra.background.loader_context import LoaderCancelled
from datalens.infra.background.loader_runner import run_with_loader
from datalens.ui.widgets.core import DatalensCheckBox, create_icon_button
from datalens.ui.widgets.core.slider_option import DatalensSliderOption
from datalens.ui.widgets.icons.auto_icon import auto_icon

from ..service import CameraDevice, CameraKind, CameraOptionSpec

log = get_logger(__name__)


def show_webcam_settings(self, *, device: CameraDevice) -> None:
    # Hide RealSense-only selectors.
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
        w.setVisible(False)

    # Depth stream controls are not relevant for webcams.
    try:
        self._stream_mode_toggle.set_option_enabled("depth", False)
        self._stream_mode_toggle.set_option_enabled("overlay", False)
        current_mode = getattr(self, "_stream_mode", "rgb")
        if current_mode in ("depth", "overlay"):
            self._stream_mode_toggle.set_current_id("rgb", emit=False)
            self._set_stream_mode("rgb", record_undo=False)
    except Exception:
        pass

    refresh_webcam_metadata_async(self, device=device)


def refresh_webcam_metadata_async(self, *, device: CameraDevice) -> None:
    if getattr(self, "_webcam_metadata_refresh_inflight", False):
        return

    # Fast path: if we've already probed this device, avoid UI churn and
    # don't show a loader dialog again.
    cached = None
    try:
        cached = self._service.peek_webcam_options_cache(device_id=str(device.device_id))
    except Exception:
        cached = None
    if cached is not None:
        rebuild_webcam_settings_from_specs(self, cached, device=device)
        self._refresh_controls()
        return

    self._webcam_metadata_refresh_inflight = True
    self._rebuild_rgb_settings_placeholder()

    def task(ctx) -> tuple[CameraOptionSpec, ...]:
        ctx.log(f"Camera: {device.display_name}")
        specs = self._service.probe_webcam_options(
            device=device,
            log_message=ctx.log,
            set_progress=ctx.set_progress,
            is_cancel_requested=ctx.is_cancel_requested,
        )
        if ctx.is_cancel_requested():
            raise LoaderCancelled()
        return specs

    def on_done(specs: tuple[CameraOptionSpec, ...]) -> None:
        self._webcam_metadata_refresh_inflight = False
        try:
            current = self._device_combo.currentData()
        except Exception:
            current = None
        if not (
            isinstance(current, CameraDevice)
            and current.kind == CameraKind.WEBCAM
            and current.device_id == device.device_id
        ):
            return

        rebuild_webcam_settings_from_specs(self, specs, device=device)
        self._refresh_controls()

    def on_cancelled() -> None:
        self._webcam_metadata_refresh_inflight = False

    def on_error(exc: Exception) -> None:
        self._webcam_metadata_refresh_inflight = False
        log.debug(
            "Webcam option probe failed",
            exc_info=True,
            extra={"operation": "capture", "phase": "cv_probe_error", "device_id": device.device_id},
        )
        try:
            current = self._device_combo.currentData()
        except Exception:
            current = None
        if isinstance(current, CameraDevice) and current.kind == CameraKind.WEBCAM and current.device_id == device.device_id:
            self._clear_form_layout(self._rgb_options_layout)
            label = QLabel("Camera settings probe failed (see logs).", self._rgb_options_widget)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.70)}; font-size: 11px;")
            self._rgb_options_layout.addRow("", label)

    run_with_loader(
        self,
        "Probing webcam controls…",
        task,
        on_result=on_done,
        on_error=on_error,
        on_cancelled=on_cancelled,
        dialog_options={
            "max_messages": 8,
            "cancelable": True,
            "log_context": {"operation": "capture", "phase": "cv_probe", "device_id": device.device_id},
        },
    )


def rebuild_webcam_settings_from_specs(self, specs: tuple[CameraOptionSpec, ...], *, device: CameraDevice) -> None:
    self._clear_form_layout(self._rgb_options_layout)
    self._rs_option_widgets.clear()
    try:
        self._rs_option_labels.clear()
    except Exception:
        pass
    try:
        self._camera_option_ui_setters.clear()
    except Exception:
        pass

    entries = [s for s in (specs or ()) if isinstance(s, CameraOptionSpec) and s.sensor == "rgb"]
    if not entries:
        label = QLabel("No camera settings reported by this webcam.", self._rgb_options_widget)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.70)}; font-size: 11px;")
        self._rgb_options_layout.addRow("", label)
        return

    by_id: dict[str, CameraOptionSpec] = {str(s.id): s for s in entries}

    def _register_ui(opt_id: str, label: str, setter) -> None:
        try:
            self._rs_option_labels[str(opt_id)] = str(label)
        except Exception:
            pass
        try:
            self._camera_option_ui_setters[str(opt_id)] = setter
        except Exception:
            pass

    auto_pairs: dict[str, tuple[str, float, float]] = {
        "exposure": ("auto_exposure", 0.75, 0.25),
        "focus": ("autofocus", 1.0, 0.0),
        "wb_blue_u": ("auto_wb", 1.0, 0.0),
    }
    for gain_auto_id in ("auto_gain", "gain_auto", "autogain"):
        if gain_auto_id in by_id:
            auto_pairs["gain"] = (gain_auto_id, 1.0, 0.0)
            break

    def _auto_checked(auto_id: str) -> bool:
        # Prefer user overrides if present.
        try:
            override = self._service.peek_webcam_option_override(device_id=str(device.device_id), option_id=str(auto_id))
        except Exception:
            override = None
        if override is not None:
            if str(auto_id) == "auto_exposure":
                return float(override) >= 0.5
            return bool(float(override) >= 0.5)

        spec = by_id.get(str(auto_id))
        if spec is None:
            return True
        if spec.kind == "bool":
            return bool(spec.current) if spec.current is not None else True
        if spec.kind == "enum":
            try:
                v = float(spec.current) if spec.current is not None else 0.75
            except Exception:
                v = 0.75
            return v >= 0.5
        return True

    def _build_slider(spec: CameraOptionSpec) -> DatalensSliderOption | None:
        if spec.kind != "float" or spec.range is None:
            return None
        mn, mx, step, default = spec.range
        slider = DatalensSliderOption(
            self._theme,
            self._rgb_options_widget,
            float(mn),
            float(mx),
            float(step) if float(step) != 0 else 0.01,
            default_value=float(default),
        )
        opt_id = str(spec.id)
        setting = f"cv_rgb_option/{opt_id}"
        stored = None
        try:
            stored = self._load_device_preference(str(device.device_id), setting, default=None)
        except Exception:
            stored = None
        initial = None
        try:
            initial = float(stored) if stored is not None else (float(spec.current) if spec.current is not None else None)
        except Exception:
            initial = None
        if initial is not None:
            try:
                slider.setValue(float(initial))
            except Exception:
                pass
        slider.valueChanged.connect(
            lambda value, oid=opt_id: self._on_webcam_rgb_option_changed(device_id=str(device.device_id), option_id=oid, value=float(value))
        )
        try:
            self._rs_option_widgets[opt_id] = slider
        except Exception:
            pass

        def _setter(v: object, w=slider) -> None:
            try:
                fv = float(v)
            except Exception:
                return
            try:
                w.blockSignals(True)
                w.setValue(float(fv))
            finally:
                w.blockSignals(False)

        _register_ui(opt_id, str(spec.label), _setter)
        try:
            if initial is not None:
                pref_key = f"devices/{str(device.device_id)}/{setting}"
                self._cache_set(pref_key, float(initial))
        except Exception:
            pass
        return slider

    def _wrap_with_auto(
        *,
        manual_spec: CameraOptionSpec,
        manual_widget: QWidget,
        auto_id: str,
        auto_on: float,
        auto_off: float,
    ) -> QWidget:
        row = QWidget(self._rgb_options_widget)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        row_layout.addWidget(manual_widget, 1)

        btn = create_icon_button(
            self._theme,
            row,
            checkable=True,
        )
        btn.setObjectName("CaptureAutoOptionButton")
        def update_icon(checked_state: bool) -> None:
            bg = self._theme.confirm_color if checked_state else self._theme.cancel_color
            btn.setIcon(auto_icon(self._theme, size=18, background_color=bg))

        def update_tooltip(checked_state: bool) -> None:
            state = "Enabled" if checked_state else "Disabled"
            action = "disable" if checked_state else "enable"
            btn.setToolTip(f"Auto: {state}\nClick to {action} auto")

        setting = f"cv_rgb_option/{str(auto_id)}"
        stored_auto = None
        try:
            stored_auto = self._load_device_preference(str(device.device_id), setting, default=None)
        except Exception:
            stored_auto = None
        checked = bool(float(stored_auto) >= 0.5) if stored_auto is not None else _auto_checked(auto_id)
        btn.setChecked(bool(checked))
        manual_widget.setEnabled(bool(not checked))
        update_icon(bool(checked))
        update_tooltip(bool(checked))

        def on_toggled(checked_state: bool) -> None:
            v = float(auto_on if checked_state else auto_off)
            from PySide6.QtGui import QUndoStack

            stack = getattr(self, "undo_stack", None)
            if not checked_state and isinstance(stack, QUndoStack):
                stack.beginMacro(f"Disable auto {manual_spec.label}")
                try:
                    self._on_webcam_rgb_option_changed(device_id=str(device.device_id), option_id=str(auto_id), value=v)
                    if isinstance(manual_widget, DatalensSliderOption):
                        try:
                            self._on_webcam_rgb_option_changed(
                                device_id=str(device.device_id),
                                option_id=str(manual_spec.id),
                                value=float(manual_widget.value()),
                            )
                        except Exception:
                            pass
                finally:
                    stack.endMacro()
            else:
                self._on_webcam_rgb_option_changed(device_id=str(device.device_id), option_id=str(auto_id), value=v)
            manual_widget.setEnabled(bool(not checked_state))
            update_icon(bool(checked_state))
            update_tooltip(bool(checked_state))

        btn.toggled.connect(on_toggled)
        row_layout.addWidget(btn, 0, alignment=Qt.AlignVCenter)

        manual_id = str(manual_spec.id)
        auto_id_s = str(auto_id)
        try:
            self._rs_option_widgets[auto_id_s] = btn
        except Exception:
            pass

        def _auto_setter(v: object, w=btn, manual=manual_widget) -> None:
            checked_state = bool(float(v) >= 0.5) if not isinstance(v, bool) else bool(v)
            try:
                w.blockSignals(True)
                w.setChecked(bool(checked_state))
            finally:
                w.blockSignals(False)
            manual.setEnabled(bool(not checked_state))
            update_icon(bool(checked_state))
            update_tooltip(bool(checked_state))

        _register_ui(auto_id_s, str(auto_id_s), _auto_setter)
        try:
            pref_key = f"devices/{str(device.device_id)}/cv_rgb_option/{auto_id_s}"
            stored_value = float(auto_on if checked else auto_off)
            self._cache_set(pref_key, stored_value)
        except Exception:
            pass
        return row

    # Order: auto-related settings first (V1-ish UX).
    # If gain doesn't have an auto toggle, keep it below brightness (more intuitive
    # grouping with the other "image look" controls).
    priority: tuple[str, ...] = ("exposure", "focus", "wb_blue_u")
    if "gain" in auto_pairs:
        priority = ("exposure", "gain", "focus", "wb_blue_u")
    ordered: list[CameraOptionSpec] = []
    seen: set[str] = set()
    for key in priority:
        spec = by_id.get(key)
        if spec is not None:
            ordered.append(spec)
            seen.add(key)

    # Remaining manual settings (exclude auto toggles because they are wired into the rows above).
    skip_auto = {str(auto_id) for auto_id, _, _ in auto_pairs.values()}
    deferred_gain: CameraOptionSpec | None = None
    for spec in entries:
        sid = str(spec.id)
        if sid in seen or sid in skip_auto:
            continue
        if sid == "gain" and "gain" not in auto_pairs and "brightness" in by_id:
            deferred_gain = spec
            continue
        ordered.append(spec)
        seen.add(sid)
    if deferred_gain is not None:
        ordered.append(deferred_gain)
        seen.add("gain")

    for spec in ordered:
        sid = str(spec.id)
        if sid in auto_pairs:
            auto_id, auto_on, auto_off = auto_pairs[sid]
            slider = _build_slider(spec)
            if slider is None:
                continue
            if str(auto_id) in by_id:
                row = _wrap_with_auto(
                    manual_spec=spec,
                    manual_widget=slider,
                    auto_id=auto_id,
                    auto_on=float(auto_on),
                    auto_off=float(auto_off),
                )
                self._rgb_options_layout.addRow(str(spec.label), row)
            else:
                self._rgb_options_layout.addRow(str(spec.label), slider)
            continue

        if spec.kind == "float" and spec.range is not None:
            slider = _build_slider(spec)
            if slider is not None:
                self._rgb_options_layout.addRow(str(spec.label), slider)
                continue

        if spec.kind == "bool":
            opt_id = str(spec.id)
            setting = f"cv_rgb_option/{opt_id}"
            stored = None
            try:
                stored = self._load_device_preference(str(device.device_id), setting, default=None)
            except Exception:
                stored = None
            cb = DatalensCheckBox("", self._theme, self._rgb_options_widget)
            initial = bool(stored) if stored is not None else (bool(spec.current) if spec.current is not None else True)
            cb.setChecked(bool(initial))
            cb.toggled.connect(
                lambda checked, oid=opt_id: self._on_webcam_rgb_option_changed(device_id=str(device.device_id), option_id=oid, value=bool(checked))
            )
            self._rgb_options_layout.addRow(str(spec.label), cb)
            try:
                self._rs_option_widgets[opt_id] = cb
            except Exception:
                pass

            def _setter(v: object, w=cb) -> None:
                try:
                    w.blockSignals(True)
                    w.setChecked(bool(v))
                finally:
                    w.blockSignals(False)

            _register_ui(opt_id, str(spec.label), _setter)
            try:
                pref_key = f"devices/{str(device.device_id)}/{setting}"
                self._cache_set(pref_key, bool(initial))
            except Exception:
                pass
            continue

        if spec.kind == "enum":
            opt_id = str(spec.id)
            setting = f"cv_rgb_option/{opt_id}"
            stored = None
            try:
                stored = self._load_device_preference(str(device.device_id), setting, default=None)
            except Exception:
                stored = None
            combo = QComboBox(self._rgb_options_widget)
            for value, label in spec.enum_items:
                combo.addItem(str(label), float(value))
            try:
                current_v = float(stored) if stored is not None else (float(spec.current) if spec.current is not None else None)
            except Exception:
                current_v = None
            if current_v is not None:
                best = None
                best_idx = 0
                for idx in range(combo.count()):
                    v = combo.itemData(idx)
                    try:
                        dv = abs(float(v) - float(current_v))
                    except Exception:
                        continue
                    if best is None or dv < best:
                        best = dv
                        best_idx = idx
                combo.setCurrentIndex(best_idx)
            combo.currentIndexChanged.connect(
                lambda _=0, oid=opt_id, w=combo: self._on_webcam_rgb_option_changed(device_id=str(device.device_id), option_id=oid, value=float(w.currentData()))
            )
            self._rgb_options_layout.addRow(str(spec.label), combo)
            try:
                self._rs_option_widgets[opt_id] = combo
            except Exception:
                pass

            def _setter(v: object, w=combo) -> None:
                try:
                    target = float(v)
                except Exception:
                    return
                try:
                    w.blockSignals(True)
                    best = None
                    best_idx = 0
                    for idx in range(w.count()):
                        d = w.itemData(idx)
                        try:
                            dv = abs(float(d) - float(target))
                        except Exception:
                            continue
                        if best is None or dv < best:
                            best = dv
                            best_idx = idx
                    w.setCurrentIndex(best_idx)
                finally:
                    w.blockSignals(False)

            _register_ui(opt_id, str(spec.label), _setter)
            try:
                if current_v is not None:
                    pref_key = f"devices/{str(device.device_id)}/{setting}"
                    self._cache_set(pref_key, float(current_v))
            except Exception:
                pass
            continue

        label = QLabel("Unsupported", self._rgb_options_widget)
        label.setStyleSheet(f"color: {self._theme.with_alpha_hex(self._theme.text_color, 0.65)}; font-size: 11px;")
        self._rgb_options_layout.addRow(str(spec.label), label)


__all__ = ["show_webcam_settings", "refresh_webcam_metadata_async", "rebuild_webcam_settings_from_specs"]
