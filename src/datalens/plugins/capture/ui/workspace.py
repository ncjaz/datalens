from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

from datalens.core.events import EventHub, StatusMessageRequested
from datalens.core.logging import get_logger
from datalens.infra.persistence_queue import PersistenceQueue
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.slider_option import DatalensSliderOption

from . import auto_refresh_controls, depth_controls, device_controls, device_preferences, realsense_controls, save_controls, webcam_controls
from .undo import CaptureSettingUndoCommand, CaptureUndoMeta
from .workspace_constants import (
    _CAPTURE_PLUGIN_ID,
    _DEFAULT_COLORMAP,
    _DEFAULT_DEPTH_ALIGNMENT,
    _DEFAULT_DEPTH_AUTO_SCALE,
    _DEFAULT_DEPTH_FAR_M,
    _DEFAULT_DEPTH_NEAR_M,
    _DEFAULT_DEPTH_PERCENTILE_HIGH,
    _DEFAULT_DEPTH_PERCENTILE_LOW,
    _DEFAULT_DEPTH_USE_PERCENTILES,
    _DEFAULT_SAVE_FORMATS,
    _DEFAULT_SCAN_MODE,
    _DEFAULT_STREAM_MODE,
    _PROJECT_OUTPUT_DIR_KEY,
    _SETTING_COLORMAP,
    _SETTING_DEPTH_ALIGNMENT,
    _SETTING_DEPTH_AUTO_SCALE,
    _SETTING_DEPTH_FAR_M,
    _SETTING_DEPTH_NEAR_M,
    _SETTING_DEPTH_PERCENTILE_HIGH,
    _SETTING_DEPTH_PERCENTILE_LOW,
    _SETTING_DEPTH_USE_PERCENTILES,
    _SETTING_RS_FPS,
    _SETTING_RS_FORMAT,
    _SETTING_RS_RESOLUTION,
    _SETTING_SAVE_FORMATS,
    _SETTING_SCAN_MODE,
    _SETTING_STREAM_MODE,
)
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
        self._undo_stack = QUndoStack(self)
        self._undo_stack.setUndoLimit(15)
        self._undo_suppressed = False
        self._setting_cache: dict[str, object] = {}
        self._project_output_snapshot: dict[str, object] | None = None
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
        self._rs_option_labels: dict[str, str] = {}
        self._camera_option_ui_setters: dict[str, object] = {}

        self.build_ui(theme=theme)
        self._project_output_queue = PersistenceQueue(
            parent=self,
            name="CaptureOutputDir",
            debounce_ms=250,
            max_pending_jobs=1,
            use_worker=False,  # project_db already handles background work
            merge_func=self._merge_output_dir_changes,
            snapshot_func=self._snapshot_output_dir,
            save_func=self._save_output_dir,
        )
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

    @property
    def undo_stack(self) -> QUndoStack:
        return self._undo_stack

    @contextmanager
    def _without_undo(self):
        prior = bool(self._undo_suppressed)
        self._undo_suppressed = True
        try:
            yield
        finally:
            self._undo_suppressed = prior

    def _cache_get(self, key: str, default: object | None = None) -> object | None:
        try:
            return self._setting_cache.get(str(key), default)
        except Exception:
            return default

    def _cache_set(self, key: str, value: object) -> None:
        try:
            self._setting_cache[str(key)] = value
        except Exception:
            return

    def _push_setting_command(
        self,
        *,
        description: str,
        old_value: object,
        new_value: object,
        apply_value,
        merge_key: str | None = None,
        meta: CaptureUndoMeta | None = None,
    ) -> None:
        if old_value == new_value:
            return
        if self._undo_suppressed:
            try:
                if callable(apply_value):
                    apply_value(new_value)
            except Exception:
                pass
            return

        cmd = CaptureSettingUndoCommand(
            str(description),
            apply_value=apply_value,  # type: ignore[arg-type]
            old_value=old_value,
            new_value=new_value,
            merge_key=merge_key,
            meta=meta,
        )
        self._undo_stack.push(cmd)

    def _coerce_stream_mode(self, mode: str) -> str:
        mode_s = str(mode or "").strip().lower()
        if mode_s not in {"rgb", "depth", "overlay"}:
            mode_s = _DEFAULT_STREAM_MODE

        if mode_s == "rgb":
            return mode_s

        allow_depth = False
        try:
            device = self._device_combo.currentData()
            depth_enabled = bool(self._rs_depth_toggle.current_id == "enabled")
            allow_depth = bool(
                isinstance(device, CameraDevice) and device.kind == CameraKind.REALSENSE and depth_enabled
            )
        except Exception:
            allow_depth = False

        return mode_s if allow_depth else "rgb"

    def _coerce_scan_mode(self, mode: str) -> str:
        mode_s = str(mode or "").strip().lower()
        if mode_s not in {"manual", "auto"}:
            mode_s = _DEFAULT_SCAN_MODE
        return mode_s

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

    def _merge_output_dir_changes(self, keys: set[object], full_refresh: bool, payloads: list[object]) -> bool:
        return bool(keys) or bool(full_refresh) or bool(payloads)

    def _snapshot_output_dir(self) -> dict[str, object] | None:
        project = getattr(self._app_ctx, "active_project", None)
        if project is None:
            return None

        abs_dir, rel_dir = self._current_output_dir_info()
        payload: dict[str, object] = {}
        if isinstance(rel_dir, str) and rel_dir:
            payload["rel"] = rel_dir
        elif abs_dir is not None:
            payload["abs"] = str(abs_dir)
        else:
            return None

        if payload == self._project_output_snapshot:
            return None
        self._project_output_snapshot = payload
        return payload

    def _save_output_dir(self, payload: dict[str, object]) -> bool:
        project = getattr(self._app_ctx, "active_project", None)
        if project is None:
            return False
        project.project_db.kv_set(_CAPTURE_PLUGIN_ID, _PROJECT_OUTPUT_DIR_KEY, payload)
        return True

    def _enqueue_output_dir_save(self) -> None:
        try:
            self._project_output_queue.enqueue(keys={"output_dir"})
        except Exception:
            pass

    def _resolve_project_output_dir(self, value: object, project_root: Path) -> str:
        if isinstance(value, dict):
            rel = value.get("rel")
            if isinstance(rel, str) and rel:
                return str(Path(project_root) / rel)
            abs_dir = value.get("abs")
            if isinstance(abs_dir, str) and abs_dir:
                return abs_dir
        if isinstance(value, str) and value:
            return value
        try:
            return str(self._default_output_dir() or "")
        except Exception:
            return ""

    def _restore_project_output_dir(self) -> None:
        project = getattr(self._app_ctx, "active_project", None)
        self._project_output_snapshot = None
        if project is None:
            with self._without_undo():
                try:
                    self._output_dir_edit.blockSignals(True)
                    self._output_dir_edit.setText("")
                finally:
                    try:
                        self._output_dir_edit.blockSignals(False)
                    except Exception:
                        pass
            self._cache_set(_PROJECT_OUTPUT_DIR_KEY, "")
            self._project_output_snapshot = None
            return

        future = project.project_db.kv_get(_CAPTURE_PLUGIN_ID, _PROJECT_OUTPUT_DIR_KEY)

        def apply(value: object | None) -> None:
            resolved = self._resolve_project_output_dir(value, project.project_root)
            with self._without_undo():
                try:
                    self._output_dir_edit.blockSignals(True)
                    self._output_dir_edit.setText(resolved)
                finally:
                    try:
                        self._output_dir_edit.blockSignals(False)
                    except Exception:
                        pass
            self._cache_set(_PROJECT_OUTPUT_DIR_KEY, resolved)
            self._refresh_controls()

        def on_done(fut) -> None:
            try:
                value = fut.result()
            except Exception:
                value = None
            QTimer.singleShot(0, lambda: apply(value))

        future.add_done_callback(on_done)

    def _subscribe_preferences(self) -> None:
        return auto_refresh_controls.subscribe_preferences(self)

    def _on_preferences_changed(self, keys: set[str]) -> None:
        auto_refresh_controls.on_preferences_changed(self, keys)
        if not keys:
            return

        depth_keys = {
            _SETTING_DEPTH_AUTO_SCALE,
            _SETTING_DEPTH_USE_PERCENTILES,
            _SETTING_DEPTH_PERCENTILE_LOW,
            _SETTING_DEPTH_PERCENTILE_HIGH,
            _SETTING_DEPTH_NEAR_M,
            _SETTING_DEPTH_FAR_M,
        }
        if not (depth_keys & set(keys)):
            return
        try:
            prefs = self._app_ctx.preferences
        except Exception:
            prefs = None
        self._load_depth_visualization_preferences(prefs)

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
        except Exception:
            prefs = None

        with self._without_undo():
            try:
                raw_scan_mode = prefs.get(_CAPTURE_PLUGIN_ID, _SETTING_SCAN_MODE, default=_DEFAULT_SCAN_MODE) if prefs else _DEFAULT_SCAN_MODE
                scan_mode = self._coerce_scan_mode(str(raw_scan_mode))
            except Exception:
                scan_mode = _DEFAULT_SCAN_MODE
            self._apply_scan_mode(scan_mode, persist=False)

            try:
                raw_formats = prefs.get(_CAPTURE_PLUGIN_ID, _SETTING_SAVE_FORMATS, default=list(_DEFAULT_SAVE_FORMATS)) if prefs else list(_DEFAULT_SAVE_FORMATS)
                formats = {str(x) for x in (raw_formats or ()) if str(x)}
            except Exception:
                formats = set(_DEFAULT_SAVE_FORMATS)

            try:
                self._save_formats.blockSignals(True)
                self._save_formats.set_checked("rgb", "rgb" in formats, emit=False)
                self._save_formats.set_checked("depth", "depth" in formats, emit=False)
            except Exception:
                pass
            finally:
                try:
                    self._save_formats.blockSignals(False)
                except Exception:
                    pass
            self._cache_set(_SETTING_SAVE_FORMATS, sorted(formats))

            try:
                raw_stream_mode = prefs.get(_CAPTURE_PLUGIN_ID, _SETTING_STREAM_MODE, default=_DEFAULT_STREAM_MODE) if prefs else _DEFAULT_STREAM_MODE
                stream_mode = self._coerce_stream_mode(str(raw_stream_mode))
            except Exception:
                stream_mode = _DEFAULT_STREAM_MODE
            self._apply_stream_mode(stream_mode)

            self._load_depth_visualization_preferences(prefs)

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

    def _set_checkbox_value(self, widget, checked: bool) -> None:
        try:
            widget.blockSignals(True)
            widget.setChecked(bool(checked))
        finally:
            try:
                widget.blockSignals(False)
            except Exception:
                pass

    def _set_spin_value(self, widget, value: float) -> None:
        try:
            widget.blockSignals(True)
            widget.setValue(float(value))
        finally:
            try:
                widget.blockSignals(False)
            except Exception:
                pass

    def _apply_scan_mode(self, mode: str, *, persist: bool = True) -> None:
        mode_s = self._coerce_scan_mode(mode)
        self._scan_mode = mode_s
        try:
            self._scan_mode_toggle.blockSignals(True)
            self._scan_mode_toggle.set_current_id(mode_s, emit=False)
        finally:
            try:
                self._scan_mode_toggle.blockSignals(False)
            except Exception:
                pass
        self._cache_set(_SETTING_SCAN_MODE, mode_s)
        if persist:
            self._save_user_preference(_SETTING_SCAN_MODE, mode_s)
        self._auto_refresh_override = None
        self._sync_auto_refresh_from_sources(immediate=False)

    def _set_scan_mode(self, mode: str, *, record_undo: bool = True) -> None:
        desired = self._coerce_scan_mode(mode)
        if not bool(record_undo) or self._undo_suppressed:
            self._apply_scan_mode(desired, persist=True)
            return

        old_value = str(self._cache_get(_SETTING_SCAN_MODE, self._scan_mode) or _DEFAULT_SCAN_MODE)
        if not old_value:
            old_value = _DEFAULT_SCAN_MODE

        def _apply(value: object) -> None:
            self._apply_scan_mode(str(value), persist=True)

        self._push_setting_command(
            description="Change scan mode",
            old_value=old_value,
            new_value=desired,
            apply_value=_apply,
            meta=CaptureUndoMeta(setting_key=_SETTING_SCAN_MODE),
        )

    def _on_scan_mode_changed(self, mode: str) -> None:
        self._set_scan_mode(mode)

    def _load_depth_visualization_preferences(self, prefs) -> None:
        def _read_bool(key: str, default: bool) -> bool:
            try:
                raw = prefs.get(_CAPTURE_PLUGIN_ID, key, default=default) if prefs else default
                return bool(raw)
            except Exception:
                return bool(default)

        def _read_float(key: str, default: float) -> float:
            try:
                raw = prefs.get(_CAPTURE_PLUGIN_ID, key, default=default) if prefs else default
                return float(raw)
            except Exception:
                return float(default)

        payload = {
            _SETTING_DEPTH_AUTO_SCALE: _read_bool(_SETTING_DEPTH_AUTO_SCALE, _DEFAULT_DEPTH_AUTO_SCALE),
            _SETTING_DEPTH_USE_PERCENTILES: _read_bool(_SETTING_DEPTH_USE_PERCENTILES, _DEFAULT_DEPTH_USE_PERCENTILES),
            _SETTING_DEPTH_PERCENTILE_LOW: _read_float(_SETTING_DEPTH_PERCENTILE_LOW, _DEFAULT_DEPTH_PERCENTILE_LOW),
            _SETTING_DEPTH_PERCENTILE_HIGH: _read_float(_SETTING_DEPTH_PERCENTILE_HIGH, _DEFAULT_DEPTH_PERCENTILE_HIGH),
            _SETTING_DEPTH_NEAR_M: _read_float(_SETTING_DEPTH_NEAR_M, _DEFAULT_DEPTH_NEAR_M),
            _SETTING_DEPTH_FAR_M: _read_float(_SETTING_DEPTH_FAR_M, _DEFAULT_DEPTH_FAR_M),
        }

        self._apply_depth_visualization_payload(payload, persist=False)

    def _apply_depth_visualization_payload(self, payload: dict[str, object], *, persist: bool) -> None:
        auto_scale = bool(payload.get(_SETTING_DEPTH_AUTO_SCALE, _DEFAULT_DEPTH_AUTO_SCALE))
        use_percentiles = bool(payload.get(_SETTING_DEPTH_USE_PERCENTILES, _DEFAULT_DEPTH_USE_PERCENTILES))
        low = float(payload.get(_SETTING_DEPTH_PERCENTILE_LOW, _DEFAULT_DEPTH_PERCENTILE_LOW))
        high = float(payload.get(_SETTING_DEPTH_PERCENTILE_HIGH, _DEFAULT_DEPTH_PERCENTILE_HIGH))
        near_m = float(payload.get(_SETTING_DEPTH_NEAR_M, _DEFAULT_DEPTH_NEAR_M))
        far_m = float(payload.get(_SETTING_DEPTH_FAR_M, _DEFAULT_DEPTH_FAR_M))

        with self._without_undo():
            self._set_checkbox_value(self._depth_auto_scale, auto_scale)
            self._set_checkbox_value(self._depth_use_percentiles, use_percentiles)
            self._set_spin_value(self._depth_percentile_low, low)
            self._set_spin_value(self._depth_percentile_high, high)
            self._set_spin_value(self._depth_manual_near_m, near_m)
            self._set_spin_value(self._depth_manual_far_m, far_m)

        self._cache_set(_SETTING_DEPTH_AUTO_SCALE, auto_scale)
        self._cache_set(_SETTING_DEPTH_USE_PERCENTILES, use_percentiles)
        self._cache_set(_SETTING_DEPTH_PERCENTILE_LOW, low)
        self._cache_set(_SETTING_DEPTH_PERCENTILE_HIGH, high)
        self._cache_set(_SETTING_DEPTH_NEAR_M, near_m)
        self._cache_set(_SETTING_DEPTH_FAR_M, far_m)

        if persist:
            self._save_user_preference(_SETTING_DEPTH_AUTO_SCALE, auto_scale)
            self._save_user_preference(_SETTING_DEPTH_USE_PERCENTILES, use_percentiles)
            self._save_user_preference(_SETTING_DEPTH_PERCENTILE_LOW, low)
            self._save_user_preference(_SETTING_DEPTH_PERCENTILE_HIGH, high)
            self._save_user_preference(_SETTING_DEPTH_NEAR_M, near_m)
            self._save_user_preference(_SETTING_DEPTH_FAR_M, far_m)

        self._sync_depth_visualization_controls()

    def _apply_depth_auto_scale(self, value: object, *, persist: bool) -> None:
        desired = bool(value)
        with self._without_undo():
            self._set_checkbox_value(self._depth_auto_scale, desired)
        self._cache_set(_SETTING_DEPTH_AUTO_SCALE, desired)
        if persist:
            self._save_user_preference(_SETTING_DEPTH_AUTO_SCALE, desired)
        self._sync_depth_visualization_controls()

    def _apply_depth_use_percentiles(self, value: object, *, persist: bool) -> None:
        desired = bool(value)
        with self._without_undo():
            self._set_checkbox_value(self._depth_use_percentiles, desired)
        self._cache_set(_SETTING_DEPTH_USE_PERCENTILES, desired)
        if persist:
            self._save_user_preference(_SETTING_DEPTH_USE_PERCENTILES, desired)
        self._sync_depth_visualization_controls()

    def _apply_depth_percentile_low(self, value: object, *, persist: bool) -> None:
        desired = float(value)
        with self._without_undo():
            self._set_spin_value(self._depth_percentile_low, desired)
        self._cache_set(_SETTING_DEPTH_PERCENTILE_LOW, desired)
        if persist:
            self._save_user_preference(_SETTING_DEPTH_PERCENTILE_LOW, desired)

    def _apply_depth_percentile_high(self, value: object, *, persist: bool) -> None:
        desired = float(value)
        with self._without_undo():
            self._set_spin_value(self._depth_percentile_high, desired)
        self._cache_set(_SETTING_DEPTH_PERCENTILE_HIGH, desired)
        if persist:
            self._save_user_preference(_SETTING_DEPTH_PERCENTILE_HIGH, desired)

    def _apply_depth_manual_near(self, value: object, *, persist: bool) -> None:
        desired = float(value)
        with self._without_undo():
            self._set_spin_value(self._depth_manual_near_m, desired)
        self._cache_set(_SETTING_DEPTH_NEAR_M, desired)
        if persist:
            self._save_user_preference(_SETTING_DEPTH_NEAR_M, desired)

    def _apply_depth_manual_far(self, value: object, *, persist: bool) -> None:
        desired = float(value)
        with self._without_undo():
            self._set_spin_value(self._depth_manual_far_m, desired)
        self._cache_set(_SETTING_DEPTH_FAR_M, desired)
        if persist:
            self._save_user_preference(_SETTING_DEPTH_FAR_M, desired)

    def _on_depth_auto_scale_toggled(self, checked: bool) -> None:
        new_value = bool(checked)
        old_value = bool(self._cache_get(_SETTING_DEPTH_AUTO_SCALE, new_value))

        def _apply(value: object) -> None:
            self._apply_depth_auto_scale(value, persist=True)

        self._push_setting_command(
            description="Toggle depth auto-scale",
            old_value=old_value,
            new_value=new_value,
            apply_value=_apply,
            meta=CaptureUndoMeta(setting_key=_SETTING_DEPTH_AUTO_SCALE),
        )

    def _on_depth_use_percentiles_toggled(self, checked: bool) -> None:
        new_value = bool(checked)
        old_value = bool(self._cache_get(_SETTING_DEPTH_USE_PERCENTILES, new_value))

        def _apply(value: object) -> None:
            self._apply_depth_use_percentiles(value, persist=True)

        self._push_setting_command(
            description="Toggle depth percentiles",
            old_value=old_value,
            new_value=new_value,
            apply_value=_apply,
            meta=CaptureUndoMeta(setting_key=_SETTING_DEPTH_USE_PERCENTILES),
        )

    def _on_depth_percentile_low_changed(self) -> None:
        new_value = float(self._depth_percentile_low.value())
        old_value = float(self._cache_get(_SETTING_DEPTH_PERCENTILE_LOW, new_value))

        def _apply(value: object) -> None:
            self._apply_depth_percentile_low(value, persist=True)

        self._push_setting_command(
            description="Change depth low percentile",
            old_value=old_value,
            new_value=new_value,
            apply_value=_apply,
            merge_key="depth_vis:percentile_low",
            meta=CaptureUndoMeta(setting_key=_SETTING_DEPTH_PERCENTILE_LOW),
        )

    def _on_depth_percentile_high_changed(self) -> None:
        new_value = float(self._depth_percentile_high.value())
        old_value = float(self._cache_get(_SETTING_DEPTH_PERCENTILE_HIGH, new_value))

        def _apply(value: object) -> None:
            self._apply_depth_percentile_high(value, persist=True)

        self._push_setting_command(
            description="Change depth high percentile",
            old_value=old_value,
            new_value=new_value,
            apply_value=_apply,
            merge_key="depth_vis:percentile_high",
            meta=CaptureUndoMeta(setting_key=_SETTING_DEPTH_PERCENTILE_HIGH),
        )

    def _on_depth_manual_near_changed(self) -> None:
        new_value = float(self._depth_manual_near_m.value())
        old_value = float(self._cache_get(_SETTING_DEPTH_NEAR_M, new_value))

        def _apply(value: object) -> None:
            self._apply_depth_manual_near(value, persist=True)

        self._push_setting_command(
            description="Change depth near range",
            old_value=old_value,
            new_value=new_value,
            apply_value=_apply,
            merge_key="depth_vis:near",
            meta=CaptureUndoMeta(setting_key=_SETTING_DEPTH_NEAR_M),
        )

    def _on_depth_manual_far_changed(self) -> None:
        new_value = float(self._depth_manual_far_m.value())
        old_value = float(self._cache_get(_SETTING_DEPTH_FAR_M, new_value))

        def _apply(value: object) -> None:
            self._apply_depth_manual_far(value, persist=True)

        self._push_setting_command(
            description="Change depth far range",
            old_value=old_value,
            new_value=new_value,
            apply_value=_apply,
            merge_key="depth_vis:far",
            meta=CaptureUndoMeta(setting_key=_SETTING_DEPTH_FAR_M),
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
        try:
            self._project_output_queue.shutdown()
        except Exception:
            log.debug("Failed to shutdown output dir persistence queue (best-effort)", exc_info=True)

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
        with self._without_undo():
            return webcam_controls.rebuild_webcam_settings_from_specs(self, specs, device=device)

    def _on_realsense_rgb_option_changed(self, *, serial: str, option_id: str, value: object) -> None:
        serial_s = str(serial or "").strip()
        opt_id = str(option_id or "").strip()
        if not serial_s or not opt_id:
            return

        setting = f"rs_rgb_option/{opt_id}"
        pref_key = device_preferences.get_device_preference_key(serial_s, setting)
        old_value = self._cache_get(pref_key, self._load_device_preference(serial_s, setting, default=value))

        label = self._rs_option_labels.get(opt_id, opt_id)
        description = f"Set {label}"

        merge_key = None
        try:
            w = self._rs_option_widgets.get(opt_id)
            if isinstance(w, DatalensSliderOption):
                merge_key = f"capture:rs:{serial_s}:{opt_id}"
        except Exception:
            merge_key = None

        def _apply(v: object) -> None:
            setter = self._camera_option_ui_setters.get(opt_id)
            if callable(setter):
                with self._without_undo():
                    try:
                        setter(v)
                    except Exception:
                        pass
            self._apply_realsense_rgb_option(serial_s, opt_id, v)

        if self._undo_suppressed:
            self._apply_realsense_rgb_option(serial_s, opt_id, value)
            return

        self._push_setting_command(
            description=description,
            old_value=old_value,
            new_value=value,
            apply_value=_apply,
            merge_key=merge_key,
            meta=CaptureUndoMeta(setting_key=pref_key, device_id=serial_s, device_kind="realsense"),
        )

    def _apply_realsense_rgb_option(self, serial: str, option_id: str, value: object) -> None:
        setting = f"rs_rgb_option/{str(option_id).strip()}"
        pref_key = device_preferences.get_device_preference_key(str(serial).strip(), setting)
        try:
            realsense_controls.on_realsense_rgb_option_changed(self, serial=str(serial), option_id=str(option_id), value=value)
        finally:
            self._save_device_preference(str(serial), setting, value)
            self._cache_set(pref_key, value)

    def _on_webcam_rgb_option_changed(self, *, device_id: str, option_id: str, value: object) -> None:
        dev_id = str(device_id or "").strip()
        opt_id = str(option_id or "").strip()
        if not dev_id or not opt_id:
            return

        setting = f"cv_rgb_option/{opt_id}"
        pref_key = device_preferences.get_device_preference_key(dev_id, setting)
        old_value = self._cache_get(pref_key, self._load_device_preference(dev_id, setting, default=value))

        label = self._rs_option_labels.get(opt_id, opt_id)
        description = f"Set {label}"

        merge_key = None
        try:
            w = self._rs_option_widgets.get(opt_id)
            if isinstance(w, DatalensSliderOption):
                merge_key = f"capture:cv:{dev_id}:{opt_id}"
        except Exception:
            merge_key = None

        def _apply(v: object) -> None:
            setter = self._camera_option_ui_setters.get(opt_id)
            if callable(setter):
                with self._without_undo():
                    try:
                        setter(v)
                    except Exception:
                        pass
            self._apply_webcam_rgb_option(dev_id, opt_id, v)

        if self._undo_suppressed:
            self._apply_webcam_rgb_option(dev_id, opt_id, value)
            return

        self._push_setting_command(
            description=description,
            old_value=old_value,
            new_value=value,
            apply_value=_apply,
            merge_key=merge_key,
            meta=CaptureUndoMeta(setting_key=pref_key, device_id=dev_id, device_kind="webcam"),
        )

    def _apply_webcam_rgb_option(self, device_id: str, option_id: str, value: object) -> None:
        dev_id = str(device_id).strip()
        opt_id = str(option_id).strip()
        setting = f"cv_rgb_option/{opt_id}"
        pref_key = device_preferences.get_device_preference_key(dev_id, setting)
        try:
            self._service.set_webcam_option(device_id=dev_id, option_id=opt_id, value=value)  # type: ignore[arg-type]
        except Exception:
            log.debug(
                "Failed to apply webcam option update (best-effort)",
                exc_info=True,
                extra={"operation": "capture", "phase": "cv_option_update_failed", "device_id": dev_id, "option": opt_id},
            )
        self._save_device_preference(dev_id, setting, value)
        self._cache_set(pref_key, value)

    def _refresh_realsense_metadata_async(self, *, serial: str) -> None:
        return realsense_controls.refresh_realsense_metadata_async(self, serial=serial)

    def _apply_realsense_profiles(self, profiles: tuple[RealSenseColorProfile, ...]) -> None:
        with self._without_undo():
            return realsense_controls.apply_realsense_profiles(self, profiles)

    def _on_rs_format_changed(self) -> None:
        return realsense_controls.on_rs_format_changed(self)

    def _on_rs_resolution_changed(self) -> None:
        return realsense_controls.on_rs_resolution_changed(self)

    def _on_rs_fps_changed(self) -> None:
        return realsense_controls.on_rs_fps_changed(self)

    def _update_selected_rs_profile(self) -> None:
        return realsense_controls.update_selected_rs_profile(self)

    def _on_realsense_profile_selected(
        self,
        *,
        device_id: str,
        fmt: str,
        resolution: tuple[int, int],
        fps: int,
    ) -> None:
        serial = str(device_id or "").strip()
        if not serial:
            return

        fmt_s = str(fmt or "").strip().lower()
        res_s = (int(resolution[0]), int(resolution[1])) if isinstance(resolution, tuple) and len(resolution) == 2 else None
        fps_i = int(fps) if fps is not None else None

        cache_key = device_preferences.get_device_preference_key(serial, "rs_profile")
        old = self._cache_get(cache_key, None)
        if not (isinstance(old, tuple) and len(old) == 3):
            try:
                old = self._load_realsense_profile_preference(serial)
            except Exception:
                old = (None, None, None)

        new = (fmt_s, res_s, fps_i)

        def _apply(value: object) -> None:
            try:
                v_fmt, v_res, v_fps = value if isinstance(value, tuple) and len(value) == 3 else (fmt_s, res_s, fps_i)
            except Exception:
                v_fmt, v_res, v_fps = (fmt_s, res_s, fps_i)

            target_fmt = str(v_fmt or "").strip().lower()
            target_res = v_res if isinstance(v_res, tuple) and len(v_res) == 2 else None
            target_fps = int(v_fps) if v_fps is not None else None

            with self._without_undo():
                try:
                    self._rs_format_combo.blockSignals(True)
                    self._rs_resolution_combo.blockSignals(True)
                    self._rs_fps_combo.blockSignals(True)

                    if target_fmt:
                        for idx in range(self._rs_format_combo.count()):
                            if str(self._rs_format_combo.itemData(idx) or "") == target_fmt:
                                self._rs_format_combo.setCurrentIndex(idx)
                                break

                    fmt_now = str(self._rs_format_combo.currentData() or target_fmt).strip().lower()
                    self._populate_rs_resolutions(fmt_now, selected_resolution=target_res)
                    res_now = self._rs_resolution_combo.currentData()
                    self._populate_rs_fps(fmt_now, res_now, selected_fps=target_fps)
                finally:
                    try:
                        self._rs_format_combo.blockSignals(False)
                        self._rs_resolution_combo.blockSignals(False)
                        self._rs_fps_combo.blockSignals(False)
                    except Exception:
                        pass

            # Update selection + persist to device preferences (best-effort).
            fmt_now = str(self._rs_format_combo.currentData() or "").strip().lower()
            res_now = self._rs_resolution_combo.currentData()
            fps_now = self._rs_fps_combo.currentData()

            selected: RealSenseColorProfile | None = None
            if isinstance(res_now, tuple) and len(res_now) == 2 and fps_now is not None:
                selected = self._rs_profile_lookup.get((fmt_now, int(res_now[0]), int(res_now[1]), int(fps_now)))
            self._rs_selected_profile = selected

            try:
                self._save_device_preference(serial, _SETTING_RS_FORMAT, fmt_now or None)
                if isinstance(res_now, tuple) and len(res_now) == 2:
                    self._save_device_preference(serial, _SETTING_RS_RESOLUTION, f"{int(res_now[0])}x{int(res_now[1])}")
                else:
                    self._save_device_preference(serial, _SETTING_RS_RESOLUTION, None)
                self._save_device_preference(serial, _SETTING_RS_FPS, int(fps_now) if fps_now is not None else None)
            except Exception:
                log.debug(
                    "Failed to save RealSense profile preference (best-effort)",
                    exc_info=True,
                    extra={"operation": "capture", "phase": "save_rs_profile_pref_error", "device_id": serial},
                )

            try:
                self._cache_set(device_preferences.get_device_preference_key(serial, _SETTING_RS_FORMAT), fmt_now)
                self._cache_set(device_preferences.get_device_preference_key(serial, _SETTING_RS_RESOLUTION), f"{int(res_now[0])}x{int(res_now[1])}" if isinstance(res_now, tuple) and len(res_now) == 2 else None)
                self._cache_set(device_preferences.get_device_preference_key(serial, _SETTING_RS_FPS), int(fps_now) if fps_now is not None else None)
                self._cache_set(cache_key, (fmt_now or None, res_now if isinstance(res_now, tuple) else None, int(fps_now) if fps_now is not None else None))
            except Exception:
                pass

        self._push_setting_command(
            description="Change RGB profile",
            old_value=old,
            new_value=new,
            apply_value=_apply,
            meta=CaptureUndoMeta(setting_key=cache_key, device_id=serial, device_kind="realsense"),
        )

    def _populate_rs_resolutions(self, fmt: str, *, selected_resolution: tuple[int, int] | None) -> None:
        return realsense_controls.populate_rs_resolutions(self, fmt, selected_resolution=selected_resolution)

    def _populate_rs_fps(self, fmt: str, resolution: object, *, selected_fps: int | None) -> None:
        return realsense_controls.populate_rs_fps(self, fmt, resolution, selected_fps=selected_fps)

    def _pick_preferred_realsense_format(self, formats: list[str]) -> str:
        return realsense_controls.pick_preferred_realsense_format(self, formats)

    def _select_default_realsense_profile(self, *, prior: RealSenseColorProfile | None) -> RealSenseColorProfile | None:
        return realsense_controls.select_default_realsense_profile(self, prior=prior)

    def _on_depth_stream_toggled(self) -> None:
        try:
            device = self._device_combo.currentData()
            serial = str(getattr(device, "serial", "") or "").strip()
        except Exception:
            serial = ""
        if not serial:
            depth_controls.on_depth_stream_toggled(self)
            return

        new_value = str(self._rs_depth_toggle.current_id or "disabled")
        setting = "rs_depth_enabled"
        pref_key = device_preferences.get_device_preference_key(serial, setting)
        old_value = str(self._cache_get(pref_key, "disabled") or "disabled")

        def _apply(value: object) -> None:
            desired = str(value or "disabled")
            with self._without_undo():
                try:
                    self._rs_depth_toggle.blockSignals(True)
                    self._rs_depth_toggle.set_current_id(desired, emit=False)
                finally:
                    try:
                        self._rs_depth_toggle.blockSignals(False)
                    except Exception:
                        pass
            depth_controls.on_depth_stream_toggled(self)
            actual = str(self._rs_depth_toggle.current_id or "disabled")
            self._save_device_preference(serial, setting, actual)
            self._cache_set(pref_key, actual)

        self._push_setting_command(
            description="Toggle depth stream",
            old_value=old_value,
            new_value=new_value,
            apply_value=_apply,
            meta=CaptureUndoMeta(setting_key=pref_key, device_id=serial, device_kind="realsense"),
        )

    def _on_colormap_changed(self) -> None:
        try:
            device = self._device_combo.currentData()
            serial = str(getattr(device, "serial", "") or "").strip()
        except Exception:
            serial = ""
        if not serial:
            return

        new_value = str(self._depth_colormap_combo.currentData() or _DEFAULT_COLORMAP)
        pref_key = device_preferences.get_device_preference_key(serial, _SETTING_COLORMAP)
        old_value = str(self._cache_get(pref_key, self._load_colormap_preference(serial)) or _DEFAULT_COLORMAP)

        def _apply(value: object) -> None:
            colormap = str(value or _DEFAULT_COLORMAP)
            with self._without_undo():
                try:
                    self._depth_colormap_combo.blockSignals(True)
                    for idx in range(self._depth_colormap_combo.count()):
                        if str(self._depth_colormap_combo.itemData(idx) or "") == colormap:
                            self._depth_colormap_combo.setCurrentIndex(idx)
                            break
                finally:
                    try:
                        self._depth_colormap_combo.blockSignals(False)
                    except Exception:
                        pass
            self._save_colormap_preference(serial, colormap)
            self._cache_set(pref_key, colormap)

        self._push_setting_command(
            description="Change depth colormap",
            old_value=old_value,
            new_value=new_value,
            apply_value=_apply,
            meta=CaptureUndoMeta(setting_key=pref_key, device_id=serial, device_kind="realsense"),
        )

    def _on_depth_alignment_changed(self) -> None:
        try:
            device = self._device_combo.currentData()
            serial = str(getattr(device, "serial", "") or "").strip()
        except Exception:
            serial = ""
        if not serial:
            return

        new_value = str(self._rs_depth_align_toggle.current_id or _DEFAULT_DEPTH_ALIGNMENT)
        pref_key = device_preferences.get_device_preference_key(serial, _SETTING_DEPTH_ALIGNMENT)
        old_value = str(self._cache_get(pref_key, self._load_depth_alignment_preference(serial)) or _DEFAULT_DEPTH_ALIGNMENT)

        def _apply(value: object) -> None:
            alignment = str(value or _DEFAULT_DEPTH_ALIGNMENT)
            with self._without_undo():
                try:
                    self._rs_depth_align_toggle.blockSignals(True)
                    self._rs_depth_align_toggle.set_current_id(alignment, emit=False)
                finally:
                    try:
                        self._rs_depth_align_toggle.blockSignals(False)
                    except Exception:
                        pass
            self._save_depth_alignment_preference(serial, alignment)
            self._cache_set(pref_key, alignment)

        self._push_setting_command(
            description="Change depth alignment",
            old_value=old_value,
            new_value=new_value,
            apply_value=_apply,
            meta=CaptureUndoMeta(setting_key=pref_key, device_id=serial, device_kind="realsense"),
        )

    def _set_stream_mode(self, mode: str, *, record_undo: bool = True) -> None:
        coerced = self._coerce_stream_mode(mode)
        self._apply_stream_mode(coerced)

    def _apply_stream_mode(self, mode: str) -> None:
        coerced = self._coerce_stream_mode(mode)
        with self._without_undo():
            try:
                self._stream_mode_toggle.blockSignals(True)
                self._stream_mode_toggle.set_current_id(coerced, emit=False)
            finally:
                try:
                    self._stream_mode_toggle.blockSignals(False)
                except Exception:
                    pass
        depth_controls.set_stream_mode(self, coerced)
        self._cache_set(_SETTING_STREAM_MODE, coerced)
        self._save_user_preference(_SETTING_STREAM_MODE, coerced)

    def _on_output_dir_changed(self) -> None:
        new_value = str(self._output_dir_edit.text()).strip()
        old_raw = self._cache_get(_PROJECT_OUTPUT_DIR_KEY, "")
        old_value = str(old_raw) if old_raw is not None else ""

        def _apply(value: object) -> None:
            desired = str(value or "").strip()
            with self._without_undo():
                try:
                    self._output_dir_edit.blockSignals(True)
                    self._output_dir_edit.setText(desired)
                finally:
                    try:
                        self._output_dir_edit.blockSignals(False)
                    except Exception:
                        pass
            self._cache_set(_PROJECT_OUTPUT_DIR_KEY, desired)
            self._enqueue_output_dir_save()
            self._refresh_controls()

        self._push_setting_command(
            description="Change output folder",
            old_value=old_value,
            new_value=new_value,
            apply_value=_apply,
            meta=CaptureUndoMeta(setting_key=f"project:{_PROJECT_OUTPUT_DIR_KEY}"),
        )

    def _on_save_format_toggled(self, option_id: str, checked: bool) -> None:
        opt = str(option_id or "").strip().lower()
        if opt not in {"rgb", "depth"}:
            return

        label = "RGB" if opt == "rgb" else "Depth"
        description = f"{'Enable' if checked else 'Disable'} saving {label}"

        old_raw = self._cache_get(_SETTING_SAVE_FORMATS, list(_DEFAULT_SAVE_FORMATS))
        old_set = {str(x) for x in (old_raw or ()) if str(x)}
        try:
            new_set = {str(x) for x in self._save_formats.checked_ids}
        except Exception:
            new_set = set(old_set)

        def _apply(value: object) -> None:
            desired = {str(x) for x in (value or ()) if str(x)}
            with self._without_undo():
                try:
                    self._save_formats.blockSignals(True)
                    self._save_formats.set_checked("rgb", "rgb" in desired, emit=False)
                    self._save_formats.set_checked("depth", "depth" in desired, emit=False)
                finally:
                    try:
                        self._save_formats.blockSignals(False)
                    except Exception:
                        pass
            stored = sorted(desired)
            self._cache_set(_SETTING_SAVE_FORMATS, stored)
            self._save_user_preference(_SETTING_SAVE_FORMATS, stored)
            self._refresh_controls()

        self._push_setting_command(
            description=description,
            old_value=sorted(old_set),
            new_value=sorted(new_set),
            apply_value=_apply,
            meta=CaptureUndoMeta(setting_key=_SETTING_SAVE_FORMATS),
        )

    def _clear_form_layout(self, layout: QFormLayout) -> None:
        while layout.rowCount() > 0:
            layout.removeRow(0)

    def _rebuild_rgb_settings_placeholder(self) -> None:
        self._clear_form_layout(self._rgb_options_layout)
        self._rs_option_widgets.clear()
        self._rs_option_labels.clear()
        self._camera_option_ui_setters.clear()

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
        with self._without_undo():
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
