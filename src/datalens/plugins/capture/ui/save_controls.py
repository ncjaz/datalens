from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from datalens.api.sharing import CMD_MEDIA_REGISTER
from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.extensions.images import encode_jpeg

log = get_logger(__name__)


def default_output_dir(self) -> Path | None:
    if not bool(self._app_ctx.has_project):
        return None
    try:
        root = Path(self._app_ctx.project_root)  # type: ignore[arg-type]
    except Exception:
        return None
    return root / "capture"


def current_output_dir_abs(self) -> Path | None:
    raw = ""
    try:
        raw = str(self._output_dir_edit.text()).strip()
    except Exception:
        raw = ""
    if not raw:
        return default_output_dir(self)
    return Path(raw)


def current_output_dir_rel(self) -> str | None:
    if not bool(self._app_ctx.has_project):
        return None
    base = current_output_dir_abs(self)
    if base is None:
        return None
    try:
        project_root = Path(self._app_ctx.project_root).resolve()  # type: ignore[arg-type]
        rel = base.resolve().relative_to(project_root)
        rel_s = rel.as_posix().strip("/")
        return rel_s or "capture"
    except Exception:
        return None


def current_output_dir_info(self) -> tuple[Path | None, str | None]:
    """
    Return (absolute_output_dir, project_relative_root_or_none).

    If the chosen folder is inside the project root, a project-relative path
    is returned for media index registration.
    """
    abs_dir = current_output_dir_abs(self)
    if abs_dir is None:
        return None, None
    rel = current_output_dir_rel(self)
    return abs_dir, rel


def browse_output_dir(self) -> None:
    start = ""
    try:
        if bool(self._app_ctx.has_project):
            start = str(default_output_dir(self) or Path(self._app_ctx.project_root))  # type: ignore[arg-type]
    except Exception:
        start = ""
    if not start:
        start = str(Path.cwd())

    chosen = QFileDialog.getExistingDirectory(self, "Select capture folder", start)
    if not chosen:
        return
    self._output_dir_edit.setText(str(chosen))
    self._refresh_controls()


def on_capture_clicked(self) -> None:
    frame = self._service.get_latest()
    if frame is None:
        self._publish_status("No frame available yet.")
        return

    want_rgb = bool(self._save_formats.is_checked("rgb"))
    want_depth = bool(self._save_formats.is_checked("depth"))
    if not (want_rgb or want_depth):
        self._publish_status("Enable RGB and/or Depth to capture.")
        return

    abs_root, rel_root = current_output_dir_info(self)
    if abs_root is None:
        if bool(self._app_ctx.has_project):
            abs_root = default_output_dir(self)
            rel_root = current_output_dir_rel(self)
    if abs_root is None:
        self._publish_status("Choose a capture folder first.")
        return

    if want_depth and getattr(frame, "depth", None) is None:
        self._publish_status("Depth frame not available.")
        want_depth = False
        if not want_rgb:
            return

    if want_rgb:
        try:
            rgb = frame.rgb.copy()
        except Exception:
            rgb = frame.rgb
    else:
        rgb = None

    if want_depth:
        try:
            depth = frame.depth.copy() if getattr(frame, "depth", None) is not None else None
        except Exception:
            depth = getattr(frame, "depth", None)
    else:
        depth = None

    ts = time.time()
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(ts))
    stem = f"{stamp}_{int(ts*1000)%1000:03d}"

    rgb_abs = (Path(abs_root) / "rgb" / f"{stem}.jpg") if rgb is not None else None
    depth_abs = (Path(abs_root) / "depth" / f"{stem}.png") if depth is not None else None

    log.info(
        "Capturing image",
        extra={
            "operation": "capture",
            "phase": "save_request",
            "output_dir": str(abs_root),
            "save_rgb": bool(rgb_abs is not None),
            "save_depth": bool(depth_abs is not None),
        },
    )
    self._publish_status("Capturing image…")

    def encode_and_write() -> None:
        if rgb_abs is not None:
            data = encode_jpeg(rgb, quality=92, color_order="rgb")  # type: ignore[arg-type]
            rgb_abs.parent.mkdir(parents=True, exist_ok=True)
            tmp = rgb_abs.with_suffix(rgb_abs.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(rgb_abs)

        if depth_abs is not None:
            import numpy as np
            from PIL import Image

            d = np.asarray(depth)
            if d.dtype != np.uint16:
                d = d.astype(np.uint16, copy=False)
            img = Image.fromarray(d, mode="I;16")
            depth_abs.parent.mkdir(parents=True, exist_ok=True)
            tmp = depth_abs.with_suffix(depth_abs.suffix + ".tmp")
            img.save(tmp, format="PNG")
            tmp.replace(depth_abs)

    fut = self._app_ctx.io.submit(encode_and_write)

    def on_written(_f) -> None:
        try:
            _f.result()
        except Exception as exc:
            log.exception("Failed to save capture", extra={"operation": "capture", "phase": "save_error"})
            self._publish_status(f"Save failed: {exc}")
            return

        if bool(rel_root) and bool(self._app_ctx.has_project):
            try:
                project_root = Path(self._app_ctx.project_root).resolve()  # type: ignore[arg-type]
            except Exception:
                project_root = None

            def _register(abs_path: Path) -> None:
                if project_root is None:
                    return
                try:
                    rel = abs_path.resolve().relative_to(project_root).as_posix()
                except Exception:
                    return
                try:
                    cmd_fut = self._app_ctx.commands.dispatch(
                        CMD_MEDIA_REGISTER,
                        {"relative_path": rel, "source_kind": "capture"},
                        caller_plugin_id=PluginId("capture"),
                    )
                    cmd_fut.add_done_callback(lambda *_: None)
                except Exception:
                    log.debug("Failed to dispatch CMD_MEDIA_REGISTER (best-effort)", exc_info=True)

            if rgb_abs is not None:
                _register(rgb_abs)
            if depth_abs is not None:
                _register(depth_abs)

        if rgb_abs is not None and depth_abs is not None:
            self._publish_status(f"Saved: rgb + depth ({stem})")
        elif rgb_abs is not None:
            self._publish_status(f"Saved: rgb ({stem})")
        elif depth_abs is not None:
            self._publish_status(f"Saved: depth ({stem})")
        else:
            self._publish_status("Saved.")

        if bool(rel_root) and bool(self._app_ctx.has_project):
            if rgb_abs is not None:
                try:
                    project_root = Path(self._app_ctx.project_root).resolve()  # type: ignore[arg-type]
                    rel = rgb_abs.resolve().relative_to(project_root).as_posix()
                    self.on_capture_saved(relative_path=rel)
                except Exception:
                    pass

    fut.add_done_callback(lambda f: self._ui_invoke.invoke.emit(lambda: on_written(f)))


__all__ = [
    "browse_output_dir",
    "current_output_dir_abs",
    "current_output_dir_info",
    "current_output_dir_rel",
    "default_output_dir",
    "on_capture_clicked",
]
