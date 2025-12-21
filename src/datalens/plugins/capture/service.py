from __future__ import annotations

import threading
import time
from dataclasses import dataclass
import queue
import sys
import os
from typing import Any, Callable, Literal
from enum import Enum

from datalens.core.logging import get_logger
from datalens.domain.system.frames import CameraIntrinsics, FrameBundle

log = get_logger(__name__)


class CameraKind(str, Enum):
    WEBCAM = "webcam"
    REALSENSE = "realsense"


@dataclass(frozen=True, slots=True)
class CameraDevice:
    device_id: str
    display_name: str
    kind: CameraKind
    device_index: int | None = None
    serial: str | None = None


@dataclass(frozen=True, slots=True)
class RealSenseColorProfile:
    width: int
    height: int
    fps: int
    format: str

    @property
    def key(self) -> str:
        return f"{int(self.width)}x{int(self.height)}@{int(self.fps)}:{str(self.format)}"

    @property
    def label(self) -> str:
        fmt = str(self.format).upper()
        return f"{int(self.width)} x {int(self.height)} @ {int(self.fps)} FPS ({fmt})"


@dataclass(frozen=True, slots=True)
class CameraOptionSpec:
    """
    Device option metadata for UI rendering.

    `id` is a stable identifier (e.g. "exposure", "enable_auto_exposure").
    `kind` controls the UI widget type.
    """

    id: str
    label: str
    sensor: Literal["rgb", "depth"]
    kind: Literal["float", "bool", "enum"]
    range: tuple[float, float, float, float] | None = None  # min, max, step, default
    enum_items: tuple[tuple[float, str], ...] = ()
    current: float | bool | None = None


class CaptureService:
    """
    Webcam capture runtime (MVP).

    - `start_async` never blocks the UI thread.
    - A background thread opens the device and reads frames into a "latest" slot.
    - UI should poll `get_latest()` on its own timer (rate-limited).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._status: str = "stopped"  # stopped|starting|running|error
        self._error: str | None = None
        self._device: CameraDevice | None = None
        self._latest: FrameBundle | None = None
        self._realsense_profile: RealSenseColorProfile | None = None
        self._realsense_enable_depth: bool = False
        self._rs_option_updates: "queue.Queue[tuple[str, str, float]]" = queue.Queue()
        self._rs_pending_options: dict[str, dict[str, float]] = {}
        self._rs_profiles_cache: dict[str, tuple[RealSenseColorProfile, ...]] = {}
        self._cv_option_updates: "queue.Queue[tuple[int, float]]" = queue.Queue()
        self._cv_pending_options: dict[str, dict[int, float]] = {}
        self._cv_options_cache: dict[str, tuple[CameraOptionSpec, ...]] = {}

    def _opencv_option_map(self) -> dict[str, int]:
        """
        Mapping of option ids to cv2 CAP_PROP_* ids.

        This is intentionally conservative; not all backends implement all props.
        """
        try:
            import cv2  # type: ignore
        except Exception:
            return {}

        def _prop(name: str) -> int | None:
            v = getattr(cv2, name, None)
            return int(v) if isinstance(v, int) else None

        candidates = {
            "brightness": _prop("CAP_PROP_BRIGHTNESS"),
            "contrast": _prop("CAP_PROP_CONTRAST"),
            "saturation": _prop("CAP_PROP_SATURATION"),
            "hue": _prop("CAP_PROP_HUE"),
            "gamma": _prop("CAP_PROP_GAMMA"),
            "sharpness": _prop("CAP_PROP_SHARPNESS"),
            "exposure": _prop("CAP_PROP_EXPOSURE"),
            "auto_exposure": _prop("CAP_PROP_AUTO_EXPOSURE"),
            "gain": _prop("CAP_PROP_GAIN"),
            "auto_wb": _prop("CAP_PROP_AUTO_WB"),
            "wb_blue_u": _prop("CAP_PROP_WHITE_BALANCE_BLUE_U"),
            "focus": _prop("CAP_PROP_FOCUS"),
            "autofocus": _prop("CAP_PROP_AUTOFOCUS"),
        }

        return {k: v for k, v in candidates.items() if isinstance(v, int)}

    def peek_webcam_options_cache(self, *, device_id: str) -> tuple[CameraOptionSpec, ...] | None:
        cached = self._cv_options_cache.get(str(device_id or ""))
        return cached if cached is not None else None

    def probe_webcam_options(
        self,
        *,
        device: CameraDevice,
        log_message: "Callable[[str], None] | None" = None,
        set_progress: "Callable[[float], None] | None" = None,
        is_cancel_requested: "Callable[[], bool] | None" = None,
    ) -> tuple[CameraOptionSpec, ...]:
        """
        Best-effort OpenCV webcam option probing.

        Returns only options that appear to be writable and produce a meaningful
        readback change. Results are cached by device_id.
        """
        if not isinstance(device, CameraDevice) or device.kind is not CameraKind.WEBCAM:
            return ()

        device_id = str(device.device_id or "")
        cached = self._cv_options_cache.get(device_id)
        if cached is not None:
            if callable(log_message):
                try:
                    log_message("Using cached webcam settings.")
                except Exception:
                    pass
            return cached

        try:
            import cv2  # type: ignore
        except Exception:
            return ()

        idx = int(device.device_index or 0)
        if callable(log_message):
            try:
                log_message(f"Opening {device.display_name}…")
            except Exception:
                pass
        cap = self._open_capture(device_index=idx)
        if cap is None or not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            return ()

        option_map = self._opencv_option_map()
        if not option_map:
            try:
                cap.release()
            except Exception:
                pass
            return ()

        def _safe_get(pid: int) -> float | None:
            try:
                v = cap.get(int(pid))
            except Exception:
                return None
            try:
                return float(v)
            except Exception:
                return None

        out: list[CameraOptionSpec] = []
        try:
            auto_exposure_id = "auto_exposure"
            boolish = {"auto_wb", "autofocus"}
            items = list(option_map.items())
            total = max(1, len(items))
            for index, (opt_id, pid) in enumerate(items, start=1):
                if callable(is_cancel_requested) and bool(is_cancel_requested()):
                    # Cooperative cancellation: avoid caching partial results.
                    return ()
                if callable(set_progress):
                    try:
                        set_progress(float(index - 1) / float(total))
                    except Exception:
                        pass
                if callable(log_message):
                    try:
                        log_message(f"Testing {opt_id}…")
                    except Exception:
                        pass
                baseline = _safe_get(pid)
                if baseline is None:
                    if callable(log_message):
                        try:
                            log_message(f"{opt_id}: not supported.")
                        except Exception:
                            pass
                    continue

                label = str(opt_id).replace("_", " ").title()

                # Non-invasive probing: do not call cap.set() here.
                # Many webcam drivers treat *any* set() call as switching into a
                # manual mode, and those changes can persist across handles.
                #
                # Instead, we:
                # - always expose auto toggles (default ON)
                # - expose manual sliders with conservative generic ranges
                #   (actual support is applied best-effort when the user changes a control).
                if opt_id in boolish:
                    out.append(
                        CameraOptionSpec(
                            id=str(opt_id),
                            label=label,
                            sensor="rgb",
                            kind="bool",
                            range=(0.0, 1.0, 1.0, 1.0),
                            current=bool(round(float(baseline))) if float(baseline) in (0.0, 1.0) else True,
                        )
                    )
                    if callable(log_message):
                        try:
                            log_message(f"{opt_id}: available (auto default ON).")
                        except Exception:
                            pass
                    continue

                if opt_id == auto_exposure_id:
                    # DirectShow commonly uses 0.25 (manual) / 0.75 (auto).
                    if abs(float(baseline) - 0.25) <= 0.02 or abs(float(baseline) - 0.75) <= 0.02:
                        out.append(
                            CameraOptionSpec(
                                id=str(opt_id),
                                label=label,
                                sensor="rgb",
                                kind="enum",
                                enum_items=((0.25, "Manual"), (0.75, "Auto")),
                                current=float(baseline),
                            )
                        )
                        if callable(log_message):
                            try:
                                log_message(f"{opt_id}: available (choice).")
                            except Exception:
                                pass
                        continue
                    out.append(
                        CameraOptionSpec(
                            id=str(opt_id),
                            label=label,
                            sensor="rgb",
                            kind="bool",
                            range=(0.0, 1.0, 1.0, 1.0),
                            current=True,
                        )
                    )
                    if callable(log_message):
                        try:
                            log_message(f"{opt_id}: available (auto default ON).")
                        except Exception:
                            pass
                    continue

                # Manual sliders: choose a conservative range based on the
                # driver-reported baseline, without mutating device state.
                b = float(baseline)
                if 0.0 <= b <= 1.0:
                    rng = (0.0, 1.0, 0.01, b)
                elif 0.0 <= b <= 255.0:
                    rng = (0.0, 255.0, 1.0, b)
                elif -20.0 <= b <= 20.0:
                    rng = (-20.0, 20.0, 0.1, b)
                else:
                    rng = (0.0, 1.0, 0.01, 0.5)

                out.append(
                    CameraOptionSpec(
                        id=str(opt_id),
                        label=label,
                        sensor="rgb",
                        kind="float",
                        range=rng,
                        current=b,
                    )
                )
                if callable(log_message):
                    try:
                        log_message(f"{opt_id}: available (best-effort).")
                    except Exception:
                        pass

            specs = tuple(out)
            self._cv_options_cache[device_id] = specs
            if callable(set_progress):
                try:
                    set_progress(1.0)
                except Exception:
                    pass
            return specs
        finally:
            try:
                cap.release()
            except Exception:
                pass

    def set_webcam_option(self, *, device_id: str, option_id: str, value: float | bool | int) -> None:
        """
        Store + (if streaming) apply an OpenCV webcam option update.

        Uses best-effort queued delivery so callers never block on the capture thread.
        """
        device_id_s = str(device_id or "").strip()
        if not device_id_s:
            return
        opt = str(option_id or "").strip()
        if not opt:
            return

        pid = self._opencv_option_map().get(opt)
        if pid is None:
            return

        v = float(1.0 if isinstance(value, bool) and value else 0.0) if isinstance(value, bool) else float(value)

        with self._lock:
            pending = self._cv_pending_options.setdefault(device_id_s, {})
            pending[int(pid)] = float(v)
            current = self._device
            running = self._status == "running"
            is_match = bool(running and current is not None and current.kind is CameraKind.WEBCAM and current.device_id == device_id_s)

        if is_match:
            self._cv_option_updates.put((int(pid), float(v)))

    def peek_webcam_option_override(self, *, device_id: str, option_id: str) -> float | None:
        """
        Return the pending override value for a webcam option if present.

        This reflects user-driven adjustments (not driver defaults) and is used
        by the UI to keep toggles consistent when reselecting a device.
        """
        device_id_s = str(device_id or "").strip()
        opt = str(option_id or "").strip()
        if not device_id_s or not opt:
            return None
        pid = self._opencv_option_map().get(opt)
        if pid is None:
            return None
        try:
            pending = self._cv_pending_options.get(device_id_s, {})
        except Exception:
            return None
        v = pending.get(int(pid))
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    def _ensure_webcam_auto_defaults(self, *, cap: Any, device_id: str) -> None:
        """
        Best-effort: keep webcams usable by forcing auto controls ON by default.

        Notes:
        - OpenCV doesn't have a portable "defaults" concept; drivers choose.
        - Some drivers treat *any* manual control set as disabling auto.
        - We only enforce autos when the user hasn't explicitly overridden them.
        """
        try:
            pending = self._cv_pending_options.get(str(device_id or ""), {})
        except Exception:
            pending = {}

        option_map = self._opencv_option_map()

        def _has_override(opt: str) -> bool:
            pid = option_map.get(opt)
            return bool(pid is not None and int(pid) in pending)

        def _set(pid: int, value: float) -> None:
            try:
                cap.set(int(pid), float(value))
            except Exception:
                return

        # Auto exposure (backend-specific numeric conventions).
        pid = option_map.get("auto_exposure")
        if pid is not None and not _has_override("auto_exposure"):
            # Windows (DirectShow): 0.75=auto, 0.25=manual. Other backends may
            # interpret 1/0; we try a couple of common "auto" values.
            for v in (0.75, 1.0):
                _set(int(pid), float(v))

        pid = option_map.get("auto_wb")
        if pid is not None and not _has_override("auto_wb"):
            _set(int(pid), 1.0)

        pid = option_map.get("autofocus")
        if pid is not None and not _has_override("autofocus"):
            _set(int(pid), 1.0)

    def _select_opencv_backend(self) -> int | None:
        """
        Pick a backend that tends to open devices quickly on the current platform.

        OpenCV device probing can hang for some backends on Windows/macOS when no
        camera is present or permissions are denied, so we bias toward:
        - Windows: DirectShow (CAP_DSHOW), then MSMF (CAP_MSMF)
        - macOS: AVFoundation (CAP_AVFOUNDATION)
        - Linux: V4L2 (CAP_V4L2)
        """
        try:
            import cv2  # type: ignore
        except Exception:
            return None

        def _cv2_const(name: str) -> int | None:
            value = getattr(cv2, name, None)
            return int(value) if isinstance(value, int) else None

        # Optional override: allow operators/devs to force a backend without
        # hard-coding platform behavior. Accepts:
        # - empty/undefined: use default heuristics
        # - "ANY": let OpenCV pick
        # - "CAP_MSMF" / "MSMF" / "CAP_DSHOW" / "DSHOW" / etc.
        override = os.environ.get("DATALENS_CAPTURE_OPENCV_BACKEND", "").strip()
        if override:
            normalized = override.upper().strip()
            if normalized == "ANY":
                return None
            if not normalized.startswith("CAP_"):
                normalized = f"CAP_{normalized}"
            forced = _cv2_const(normalized)
            if forced is not None:
                return forced
            log.debug(
                "Unknown OpenCV backend override (ignored)",
                extra={"operation": "capture", "phase": "backend_override", "value": override},
            )

        if sys.platform.startswith("win"):
            # Prefer DirectShow on Windows: it tends to open by index quickly and
            # matches "quick script" behavior; MSMF can be slow and noisy.
            return _cv2_const("CAP_DSHOW") or _cv2_const("CAP_MSMF")
        if sys.platform == "darwin":
            return _cv2_const("CAP_AVFOUNDATION")
        return _cv2_const("CAP_V4L2")

    def _fallback_backends(self) -> tuple[int, ...]:
        """
        Candidate backends to try after the preferred backend fails.
        """
        try:
            import cv2  # type: ignore
        except Exception:
            return ()

        override = os.environ.get("DATALENS_CAPTURE_OPENCV_BACKEND_FALLBACKS", "").strip()
        if override:
            out: list[int] = []
            for raw in override.split(","):
                name = raw.strip()
                if not name:
                    continue
                normalized = name.upper()
                if normalized == "ANY":
                    continue
                if not normalized.startswith("CAP_"):
                    normalized = f"CAP_{normalized}"
                v = getattr(cv2, normalized, None)
                if isinstance(v, int):
                    out.append(int(v))
            return tuple(dict.fromkeys(out))

        if sys.platform.startswith("win"):
            cands: list[int] = []
            for name in ("CAP_DSHOW", "CAP_MSMF"):
                v = getattr(cv2, name, None)
                if isinstance(v, int):
                    cands.append(int(v))
            return tuple(dict.fromkeys(cands))  # preserve order, unique
        return ()

    def _open_capture(self, *, device_index: int):
        """
        Best-effort helper to open a capture device with a reasonable backend.
        """
        import cv2  # type: ignore

        idx = int(device_index)
        preferred = self._select_opencv_backend()

        # First try: explicit backend (preferred) for speed and predictability.
        cap = cv2.VideoCapture(idx, int(preferred)) if preferred is not None else cv2.VideoCapture(idx)
        if cap is not None and cap.isOpened():
            return cap
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass

        # Second try: other backend hints (platform-biased), then fallbacks.
        candidates: list[int] = []
        if preferred is not None:
            candidates.append(int(preferred))
        candidates.extend(int(x) for x in self._fallback_backends())

        seen: set[int] = set()
        for backend in candidates:
            if int(backend) in seen:
                continue
            seen.add(int(backend))
            cap2 = cv2.VideoCapture(idx, int(backend))
            if cap2 is not None and cap2.isOpened():
                return cap2
            try:
                if cap2 is not None:
                    cap2.release()
            except Exception:
                pass

        # Last resort: let OpenCV pick the backend.
        cap3 = cv2.VideoCapture(idx)
        if cap3 is not None and cap3.isOpened():
            return cap3
        try:
            if cap3 is not None:
                cap3.release()
        except Exception:
            pass

        return None

    def _probe_device_index(self, *, device_index: int, timeout_s: float) -> bool:
        """
        Probe `device_index` with a short timeout to avoid hanging enumeration.
        """
        result_queue: queue.Queue[bool] = queue.Queue(maxsize=1)

        def _worker() -> None:
            cap = None
            try:
                import cv2  # type: ignore

                # Reduce OpenCV warning spam during probing; restore after.
                old_level: int | None = None
                try:
                    silence = os.environ.get("DATALENS_CAPTURE_OPENCV_SILENCE_PROBE_LOGS", "1").strip()
                    if silence not in {"0", "false", "False"}:
                        # Silence OpenCV backend spam during probing. This is
                        # global, so we restore immediately after the probe.
                        old_level = int(getattr(cv2, "getLogLevel", lambda: 0)())
                        if hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
                            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
                        elif hasattr(cv2, "setLogLevel"):
                            cv2.setLogLevel(0)
                except Exception:
                    old_level = None

                cap = self._open_capture(device_index=int(device_index))
                ok = bool(cap is not None and cap.isOpened())
                result_queue.put(ok)
            except Exception:
                result_queue.put(False)
            finally:
                try:
                    if old_level is not None:
                        if hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
                            cv2.utils.logging.setLogLevel(int(old_level))
                        elif hasattr(cv2, "setLogLevel"):
                            cv2.setLogLevel(int(old_level))
                except Exception:
                    pass
                try:
                    if cap is not None:
                        cap.release()
                except Exception:
                    pass

        t = threading.Thread(target=_worker, name=f"CaptureProbe({device_index})", daemon=True)
        t.start()
        t.join(timeout=max(0.0, float(timeout_s)))
        if t.is_alive():
            log.debug(
                "Webcam probe timed out (best-effort)",
                extra={"operation": "capture", "phase": "probe_timeout", "device_index": int(device_index)},
            )
            return False
        try:
            return bool(result_queue.get_nowait())
        except Exception:
            return False

    def enumerate_devices(self, *, max_indices: int = 8) -> list[CameraDevice]:
        """
        Best-effort device enumeration.

        OpenCV doesn't provide robust cross-platform enumeration for all backends.

        Important: on some systems (notably Windows + MSMF) opening a camera
        device by index can take several seconds. A "probe by opening" approach
        is therefore:
        - slow for the user (0..N probes can take tens of seconds)
        - brittle if we add timeouts (false negatives + orphaned probe threads)

        Default behaviour: return a small list of candidate indices (0..N-1)
        without probing. The user selects an index and we try to start capture.

        Optional: set `DATALENS_CAPTURE_ENUMERATION_MODE=probe` to enable the
        slower open-based probing mode for diagnostics.
        """
        out: list[CameraDevice] = []

        # RealSense devices (optional dependency).
        try:
            import pyrealsense2 as rs  # type: ignore

            ctx = rs.context()
            for dev in ctx.query_devices():
                serial = dev.get_info(rs.camera_info.serial_number)
                name = dev.get_info(rs.camera_info.name)
                device_id = f"rs_{serial}"
                out.append(
                    CameraDevice(
                        device_id=device_id,
                        display_name=f"[RS] {name} ({serial})",
                        kind=CameraKind.REALSENSE,
                        serial=str(serial),
                    )
                )
        except Exception:
            # pyrealsense2 not installed or enumeration failed.
            pass

        # Default to "indices": list candidate webcam indices without opening
        # devices. Probing by opening can be slow/noisy and can blink device LEDs.
        mode = os.environ.get("DATALENS_CAPTURE_ENUMERATION_MODE", "indices").strip().lower()
        if mode != "probe":
            # Webcams via candidate indices (no probing).
            for idx in range(max(0, int(max_indices))):
                out.append(
                    CameraDevice(
                        device_id=f"cv_{idx}",
                        display_name=f"[CV] Webcam {idx}",
                        kind=CameraKind.WEBCAM,
                        device_index=int(idx),
                    )
                )
            log.debug(
                "Camera enumeration completed",
                extra={
                    "operation": "capture",
                    "phase": "enumerate",
                    "mode": mode,
                    "count": len(out),
                    "max_indices": int(max_indices),
                },
            )
            return out

        # Probe mode: best-effort open tests (requires OpenCV).
        try:
            import cv2  # type: ignore  # noqa: F401
        except Exception:
            log.debug(
                "OpenCV not available; skipping webcam probe mode",
                extra={"operation": "capture", "phase": "enumerate", "mode": mode},
            )
            return out

        try:
            timeout_s = float(os.environ.get("DATALENS_CAPTURE_PROBE_TIMEOUT_S", "3.0"))
        except Exception:
            timeout_s = 3.0

        for idx in range(max(0, int(max_indices))):
            if self._probe_device_index(device_index=idx, timeout_s=timeout_s):
                out.append(
                    CameraDevice(
                        device_id=f"cv_{idx}",
                        display_name=f"[CV] Webcam {idx}",
                        kind=CameraKind.WEBCAM,
                        device_index=int(idx),
                    )
                )
        log.debug(
            "Camera enumeration completed",
            extra={
                "operation": "capture",
                "phase": "enumerate",
                "mode": mode,
                "count": len(out),
                "max_indices": int(max_indices),
            },
        )
        return out

    def enumerate_realsense_color_profiles(self, *, serial: str) -> tuple[RealSenseColorProfile, ...]:
        """
        Return the available RealSense color stream profiles for `serial`.

        This is best-effort and returns an empty tuple if pyrealsense2 is missing
        or the device cannot be queried.
        """
        serial_s = str(serial or "").strip()
        if not serial_s:
            return ()
        cached = self._rs_profiles_cache.get(serial_s)
        if cached is not None:
            return cached

        try:
            import pyrealsense2 as rs  # type: ignore
        except Exception:
            return ()

        try:
            ctx = rs.context()
            target = None
            for dev in ctx.query_devices():
                try:
                    if str(dev.get_info(rs.camera_info.serial_number)) == serial_s:
                        target = dev
                        break
                except Exception:
                    continue
            if target is None:
                return ()

            profiles: dict[str, RealSenseColorProfile] = {}
            for sensor in getattr(target, "sensors", []):
                try:
                    sp = sensor.get_stream_profiles()
                except Exception:
                    continue
                for profile in sp:
                    try:
                        video_profile = profile.as_video_stream_profile()
                    except Exception:
                        continue
                    try:
                        if video_profile.stream_type() != rs.stream.color:
                            continue
                    except Exception:
                        continue

                    try:
                        fmt = video_profile.format()
                    except Exception:
                        continue
                    # Keep a small set of common viewer formats.
                    if fmt not in (rs.format.rgb8, rs.format.bgr8, rs.format.rgba8, rs.format.bgra8):
                        continue

                    try:
                        w = int(video_profile.width())
                        h = int(video_profile.height())
                        fps = int(video_profile.fps())
                        fmt_name = str(fmt).split(".")[-1]
                    except Exception:
                        continue
                    p = RealSenseColorProfile(width=w, height=h, fps=fps, format=fmt_name)
                    profiles[p.key] = p

            out = tuple(sorted(profiles.values(), key=lambda p: (p.width, p.height, p.fps, p.format)))
            self._rs_profiles_cache[serial_s] = out
            return out
        except Exception:
            log.debug(
                "RealSense profile enumeration failed (best-effort)",
                exc_info=True,
                extra={"operation": "capture", "phase": "rs_profiles_error", "serial": serial_s},
            )
            return ()

    def enumerate_realsense_rgb_options(self, *, serial: str) -> tuple[CameraOptionSpec, ...]:
        """
        Return V1-style RealSense color sensor options for UI.

        This does not require streaming and is best-effort.
        """
        serial_s = str(serial or "").strip()
        if not serial_s:
            return ()

        try:
            import pyrealsense2 as rs  # type: ignore
        except Exception:
            return ()

        power_line_items = (
            (0, "Disabled"),
            (1, "50 Hz"),
            (2, "60 Hz"),
            (3, "Auto"),
        )

        rgb_option_list = (
            "brightness",
            "contrast",
            "saturation",
            "sharpness",
            "gamma",
            "hue",
            "white_balance",
            "enable_auto_white_balance",
            "exposure",
            "enable_auto_exposure",
            "gain",
            "backlight_compensation",
            "power_line_frequency",
        )

        try:
            ctx = rs.context()
            target = None
            for dev in ctx.query_devices():
                try:
                    if str(dev.get_info(rs.camera_info.serial_number)) == serial_s:
                        target = dev
                        break
                except Exception:
                    continue
            if target is None:
                return ()

            color_sensor = None
            for sensor in getattr(target, "sensors", []):
                try:
                    sp = sensor.get_stream_profiles()
                except Exception:
                    continue
                for profile in sp:
                    try:
                        if profile.as_video_stream_profile().stream_type() == rs.stream.color:
                            color_sensor = sensor
                            break
                    except Exception:
                        continue
                if color_sensor is not None:
                    break

            if color_sensor is None:
                return ()

            out: list[CameraOptionSpec] = []
            for option_name in rgb_option_list:
                opt = getattr(rs.option, option_name, None)
                if opt is None:
                    continue
                try:
                    if not color_sensor.supports(opt):
                        continue
                except Exception:
                    continue

                label = str(option_name).replace("_", " ").title()

                if option_name == "power_line_frequency":
                    try:
                        current = color_sensor.get_option(opt)
                    except Exception:
                        current = None
                    out.append(
                        CameraOptionSpec(
                            id=option_name,
                            label=label,
                            sensor="rgb",
                            kind="enum",
                            enum_items=power_line_items,
                            current=(int(round(float(current))) if current is not None else None),
                        )
                    )
                    continue

                try:
                    r = color_sensor.get_option_range(opt)
                    rng = (float(r.min), float(r.max), float(r.step), float(r.default))
                except Exception:
                    rng = None

                try:
                    current = color_sensor.get_option(opt)
                except Exception:
                    current = None

                if rng is not None:
                    min_v, max_v, step, default = rng
                    if step == 1 and min_v in (0.0, 1.0) and max_v in (0.0, 1.0):
                        out.append(
                            CameraOptionSpec(
                                id=option_name,
                                label=label,
                                sensor="rgb",
                                kind="bool",
                                range=rng,
                                current=(bool(round(float(current))) if current is not None else None),
                            )
                        )
                        continue

                out.append(
                    CameraOptionSpec(
                        id=option_name,
                        label=label,
                        sensor="rgb",
                        kind="float",
                        range=rng,
                        current=(float(current) if current is not None else None),
                    )
                )

            return tuple(out)
        except Exception:
            log.debug(
                "RealSense option enumeration failed (best-effort)",
                exc_info=True,
                extra={"operation": "capture", "phase": "rs_options_error", "serial": serial_s},
            )
            return ()

    def set_realsense_option(self, *, serial: str, sensor: Literal["rgb", "depth"], option_id: str, value: float | bool | int) -> None:
        """
        Store + (if streaming) apply a RealSense option update.

        This is non-blocking; when streaming it is applied by the capture thread.
        When not streaming, it is applied on next start (best-effort).
        """
        serial_s = str(serial or "").strip()
        if not serial_s:
            return
        option_s = str(option_id or "").strip()
        if not option_s:
            return
        v = float(1.0 if isinstance(value, bool) and value else 0.0) if isinstance(value, bool) else float(value)

        with self._lock:
            pending = self._rs_pending_options.setdefault(serial_s, {})
            pending[f"{sensor}:{option_s}"] = float(v)
            current = self._device
            running = self._status == "running"
            is_match = bool(
                running
                and current is not None
                and current.kind is CameraKind.REALSENSE
                and str(getattr(current, "serial", "") or "") == serial_s
            )

        if is_match:
            self._rs_option_updates.put((str(sensor), option_s, float(v)))

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "status": self._status,
                "error": self._error,
                "device_id": (self._device.device_id if self._device is not None else None),
                "device_kind": (self._device.kind.value if self._device is not None else None),
                "has_frame": self._latest is not None,
            }

    def is_running(self) -> bool:
        with self._lock:
            return self._status == "running"

    def get_latest(self) -> FrameBundle | None:
        with self._lock:
            return self._latest

    def start_async(
        self,
        *,
        device: CameraDevice | None,
        realsense_profile: RealSenseColorProfile | None = None,
        enable_depth: bool = False,
    ) -> bool:
        """
        Start capture from `device` in a background thread.

        Returns False if already running/starting.
        """
        with self._lock:
            if self._status in {"starting", "running"}:
                return False
            self._status = "starting"
            self._error = None
            self._device = device
            self._latest = None
            self._stop.clear()
            self._realsense_profile = realsense_profile
            self._realsense_enable_depth = bool(enable_depth)

            thread = threading.Thread(
                target=self._run,
                name=f"CaptureService({self._device.device_id if self._device else 'none'})",
                daemon=True,
            )
            self._thread = thread
            thread.start()

        log.info(
            "Capture start requested",
            extra={
                "operation": "capture",
                "phase": "start",
                "device_id": (self._device.device_id if self._device else None),
                "device_kind": (self._device.kind.value if self._device else None),
                "rs_profile": (self._realsense_profile.key if self._realsense_profile else None),
                "rs_depth": bool(self._realsense_enable_depth),
            },
        )
        return True

    def stop_async(self) -> None:
        with self._lock:
            self._stop.set()
            thread = self._thread
            self._thread = None
            self._status = "stopped"
            # Drop the last frame so UIs don't keep showing stale imagery after
            # stop is requested.
            self._latest = None

        if thread is not None:
            # Join in the background so UI isn't blocked.
            threading.Thread(target=lambda: thread.join(timeout=2.0), daemon=True).start()

        log.info("Capture stop requested", extra={"operation": "capture", "phase": "stop"})

    def _run(self) -> None:
        with self._lock:
            device = self._device
            rs_profile = self._realsense_profile
            rs_depth = bool(self._realsense_enable_depth)
        if device is None:
            device = CameraDevice(device_id="cv_0", display_name="[CV] Webcam 0", kind=CameraKind.WEBCAM, device_index=0)

        if device.kind is CameraKind.REALSENSE:
            self._run_realsense(device=device, profile=rs_profile, enable_depth=rs_depth)
            return

        try:
            import cv2  # type: ignore
        except Exception as exc:
            with self._lock:
                self._status = "error"
                self._error = f"OpenCV not available: {exc}"
            log.warning(
                "Capture failed: OpenCV not available",
                exc_info=True,
                extra={"operation": "capture", "phase": "error", "device_kind": "webcam"},
            )
            return

        idx = int(device.device_index or 0)
        cap = self._open_capture(device_index=idx)
        if cap is None or not cap.isOpened():
            with self._lock:
                self._status = "error"
                self._error = f"Failed to open webcam index {idx}"
            log.warning(
                "Failed to open webcam",
                extra={"operation": "capture", "phase": "open_failed", "device_index": idx},
            )
            try:
                cap.release()
            except Exception:
                pass
            return

        # Apply any cached per-device properties (best-effort).
        try:
            # Keep auto controls enabled by default unless user overrode them.
            self._ensure_webcam_auto_defaults(cap=cap, device_id=str(device.device_id or ""))

            pending = self._cv_pending_options.get(str(device.device_id or ""), {})
            for pid, v in list(pending.items()):
                try:
                    cap.set(int(pid), float(v))
                except Exception:
                    log.debug(
                        "Webcam option apply failed (best-effort)",
                        exc_info=True,
                        extra={"operation": "capture", "phase": "cv_apply_option_error", "pid": int(pid), "device_id": device.device_id},
                    )
        except Exception:
            log.debug(
                "Webcam pending option application failed (best-effort)",
                exc_info=True,
                extra={"operation": "capture", "phase": "cv_apply_pending_error", "device_id": device.device_id},
            )

        with self._lock:
            self._status = "running"
            self._error = None

        log.info(
            "Capture started",
            extra={"operation": "capture", "phase": "running", "device_index": idx, "device_id": device.device_id},
        )

        last_log = 0.0
        try:
            while not self._stop.is_set():
                # Apply queued webcam option updates (non-blocking).
                while True:
                    try:
                        pid, v = self._cv_option_updates.get_nowait()
                    except Exception:
                        break
                    try:
                        cap.set(int(pid), float(v))
                    except Exception:
                        log.debug(
                            "Webcam option update failed (best-effort)",
                            exc_info=True,
                            extra={"operation": "capture", "phase": "cv_option_update_error", "pid": int(pid), "device_id": device.device_id},
                        )

                ok, frame_bgr = cap.read()
                if not ok or frame_bgr is None:
                    time.sleep(0.01)
                    continue

                # Convert BGR -> RGB for the canonical frame payload.
                rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                bundle = FrameBundle(
                    rgb=rgb,
                    depth=None,
                    intrinsics=None,
                    timestamp_s=time.time(),
                    source_id=f"webcam:{idx}",
                )
                with self._lock:
                    self._latest = bundle

                # Avoid per-frame logging; emit a heartbeat at debug occasionally.
                now = time.monotonic()
                if now - last_log > 5.0 and log.logger.isEnabledFor(10):  # debug
                    last_log = now
                    log.debug(
                        "Capture heartbeat",
                        extra={"operation": "capture", "phase": "heartbeat", "device_index": idx},
                    )
        except Exception:
            log.exception("Capture loop failed", extra={"operation": "capture", "phase": "loop_error"})
            with self._lock:
                self._status = "error"
                self._error = "Capture loop failed (see logs)."
        finally:
            try:
                cap.release()
            except Exception:
                pass
            log.info(
                "Capture stopped",
                extra={"operation": "capture", "phase": "stopped", "device_index": idx, "device_id": device.device_id},
            )

    def _run_realsense(self, *, device: CameraDevice, profile: RealSenseColorProfile | None, enable_depth: bool) -> None:
        try:
            import numpy as np  # type: ignore
            import pyrealsense2 as rs  # type: ignore
        except Exception as exc:
            with self._lock:
                self._status = "error"
                self._error = f"RealSense dependency not available: {exc}"
            log.warning(
                "RealSense capture failed: dependency missing",
                exc_info=True,
                extra={"operation": "capture", "phase": "rs_dependency_missing"},
            )
            return

        serial = str(getattr(device, "serial", "") or "").strip()
        if not serial:
            with self._lock:
                self._status = "error"
                self._error = "RealSense device is missing a serial number."
            log.warning(
                "RealSense capture failed: missing serial",
                extra={"operation": "capture", "phase": "rs_missing_serial", "device_id": device.device_id},
            )
            return

        pipeline = rs.pipeline()
        config = rs.config()
        try:
            config.enable_device(serial)
        except Exception as exc:
            with self._lock:
                self._status = "error"
                self._error = f"Failed to select RealSense device {serial}: {exc}"
            log.warning(
                "RealSense config enable_device failed",
                exc_info=True,
                extra={"operation": "capture", "phase": "rs_enable_device_error", "serial": serial},
            )
            return

        fmt_name = str(getattr(profile, "format", "") or "rgb8").strip().lower()
        fmt = getattr(rs.format, fmt_name, None)
        if fmt is None:
            fmt = rs.format.rgb8

        if profile is not None:
            try:
                config.enable_stream(rs.stream.color, int(profile.width), int(profile.height), fmt, int(profile.fps))
            except Exception:
                log.info(
                    "RealSense color profile enable failed; falling back to default",
                    extra={"operation": "capture", "phase": "rs_profile_fallback", "serial": serial, "profile": profile.key},
                )
                try:
                    config.enable_stream(rs.stream.color)
                except Exception:
                    pass
        else:
            try:
                config.enable_stream(rs.stream.color)
            except Exception:
                # If default stream enabling fails, attempt a common baseline.
                try:
                    config.enable_stream(rs.stream.color, 640, 480, rs.format.rgb8, 30)
                except Exception:
                    pass

        depth_enabled = bool(enable_depth)
        if depth_enabled:
            try:
                config.enable_stream(rs.stream.depth)
            except Exception:
                depth_enabled = False
                log.info(
                    "RealSense depth stream enable failed (best-effort)",
                    extra={"operation": "capture", "phase": "rs_depth_enable_failed", "serial": serial},
                )

        try:
            pipeline_profile = pipeline.start(config)
        except Exception as exc:
            with self._lock:
                self._status = "error"
                self._error = f"Failed to start RealSense pipeline: {exc}"
            log.warning(
                "RealSense pipeline start failed",
                exc_info=True,
                extra={"operation": "capture", "phase": "rs_start_error", "serial": serial},
            )
            return

        color_sensor = None
        try:
            for sensor in pipeline_profile.get_device().sensors:
                try:
                    for p in sensor.get_stream_profiles():
                        if p.as_video_stream_profile().stream_type() == rs.stream.color:
                            color_sensor = sensor
                            break
                except Exception:
                    continue
                if color_sensor is not None:
                    break
        except Exception:
            color_sensor = None

        with self._lock:
            self._status = "running"
            self._error = None

        log.info(
            "RealSense capture started",
            extra={
                "operation": "capture",
                "phase": "running",
                "device_id": device.device_id,
                "serial": serial,
                "depth_enabled": bool(depth_enabled),
            },
        )

        # Apply any pending options (best-effort).
        try:
            pending = self._rs_pending_options.get(serial, {})
            if color_sensor is not None and pending:
                for k, v in list(pending.items()):
                    if not k.startswith("rgb:"):
                        continue
                    opt_name = k.split(":", 1)[1]
                    opt = getattr(rs.option, opt_name, None)
                    if opt is None:
                        continue
                    try:
                        if not color_sensor.supports(opt):
                            continue
                    except Exception:
                        continue
                    try:
                        color_sensor.set_option(opt, float(v))
                    except Exception:
                        log.debug(
                            "RealSense option apply failed (best-effort)",
                            exc_info=True,
                            extra={"operation": "capture", "phase": "rs_apply_option_error", "serial": serial, "option": opt_name},
                        )
        except Exception:
            log.debug(
                "RealSense pending option application failed (best-effort)",
                exc_info=True,
                extra={"operation": "capture", "phase": "rs_apply_pending_error", "serial": serial},
            )

        last_log = 0.0
        try:
            while not self._stop.is_set():
                # Apply queued option updates without blocking the capture loop.
                if color_sensor is not None:
                    while True:
                        try:
                            sensor_id, opt_name, v = self._rs_option_updates.get_nowait()
                        except Exception:
                            break
                        if str(sensor_id) != "rgb":
                            continue
                        opt = getattr(rs.option, str(opt_name), None)
                        if opt is None:
                            continue
                        try:
                            if not color_sensor.supports(opt):
                                continue
                        except Exception:
                            continue
                        try:
                            color_sensor.set_option(opt, float(v))
                        except Exception:
                            log.debug(
                                "RealSense option update failed (best-effort)",
                                exc_info=True,
                                extra={"operation": "capture", "phase": "rs_option_update_error", "serial": serial, "option": str(opt_name)},
                            )

                try:
                    frames = pipeline.wait_for_frames(timeout_ms=5000)
                except Exception:
                    continue

                color_frame = frames.get_color_frame()
                if not color_frame:
                    continue

                try:
                    raw = np.asanyarray(color_frame.get_data())
                except Exception:
                    continue

                # Ensure RGB888 payload for FrameBundle.
                rgb: Any
                if raw.ndim == 3 and raw.shape[2] == 3:
                    # Assume raw is already RGB or BGR depending on configured format.
                    if fmt_name.startswith("bgr"):
                        rgb = raw[..., ::-1].copy()
                    else:
                        rgb = raw.copy()
                elif raw.ndim == 3 and raw.shape[2] == 4:
                    if fmt_name.startswith("bgra"):
                        rgb = raw[..., :3][..., ::-1].copy()
                    else:
                        rgb = raw[..., :3].copy()
                else:
                    # Unexpected; try to coerce.
                    try:
                        rgb = raw.astype(np.uint8, copy=False)
                    except Exception:
                        continue

                depth = None
                if depth_enabled:
                    try:
                        dframe = frames.get_depth_frame()
                    except Exception:
                        dframe = None
                    if dframe:
                        try:
                            depth = np.asanyarray(dframe.get_data()).copy()
                        except Exception:
                            depth = None

                intr = None
                try:
                    vsp = color_frame.profile.as_video_stream_profile()
                    i = vsp.get_intrinsics()
                    intr = CameraIntrinsics(
                        width=int(i.width),
                        height=int(i.height),
                        fx=float(i.fx),
                        fy=float(i.fy),
                        cx=float(i.ppx),
                        cy=float(i.ppy),
                        distortion_model=str(getattr(i, "model", "")) or None,
                        distortion_coeffs=tuple(float(x) for x in getattr(i, "coeffs", []) or ()),
                    )
                except Exception:
                    intr = None

                bundle = FrameBundle(
                    rgb=rgb,
                    depth=depth,
                    intrinsics=intr,
                    timestamp_s=time.time(),
                    source_id=f"realsense:{serial}",
                )
                with self._lock:
                    self._latest = bundle

                now = time.monotonic()
                if now - last_log > 5.0 and log.logger.isEnabledFor(10):
                    last_log = now
                    log.debug(
                        "RealSense capture heartbeat",
                        extra={"operation": "capture", "phase": "heartbeat", "serial": serial, "depth_enabled": bool(depth_enabled)},
                    )
        except Exception:
            log.exception("RealSense capture loop failed", extra={"operation": "capture", "phase": "rs_loop_error", "serial": serial})
            with self._lock:
                self._status = "error"
                self._error = "RealSense capture loop failed (see logs)."
        finally:
            try:
                pipeline.stop()
            except Exception:
                pass
            log.info(
                "RealSense capture stopped",
                extra={"operation": "capture", "phase": "stopped", "serial": serial, "device_id": device.device_id},
            )


class LiveFramesProvider:
    """
    Capability provider for `capture.live_frames.v0`.

    Consumers should treat this as best-effort and pull at their own pace.
    """

    def __init__(self, service: CaptureService) -> None:
        self._service = service

    def get_latest(self) -> FrameBundle | None:
        return self._service.get_latest()

    def status(self) -> dict[str, object]:
        return self._service.status()


__all__ = [
    "CameraDevice",
    "CameraKind",
    "CameraOptionSpec",
    "CaptureService",
    "LiveFramesProvider",
    "RealSenseColorProfile",
]
