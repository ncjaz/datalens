from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Event

import numpy as np

from datalens.domain.system.frames import FrameBundle
from datalens.plugins.capture.ui import save_controls


@dataclass
class _FakeSaveFormats:
    rgb: bool = True
    depth: bool = False

    def is_checked(self, key: str) -> bool:
        if key == "rgb":
            return bool(self.rgb)
        if key == "depth":
            return bool(self.depth)
        return False


class _FakeEdit:
    def __init__(self, value: str) -> None:
        self._value = value

    def text(self) -> str:
        return self._value


class _FakeDeviceCombo:
    def currentData(self):  # noqa: ANN001 - Qt-like
        return None


class _FakeService:
    def __init__(self, frame: FrameBundle) -> None:
        self._frame = frame

    def get_latest(self) -> FrameBundle | None:
        return self._frame


class _FakeCommands:
    def dispatch(self, *args, **kwargs):  # noqa: ANN001 - best-effort stub
        raise AssertionError("dispatch() should not be called without a project")


class _FakeIo:
    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1)

    def submit(self, fn):  # noqa: ANN001 - matches IoWriter minimal surface
        return self._pool.submit(fn)

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=False)


class _FakeInvoker:
    def __init__(self, done: Event) -> None:
        self.invoke = self
        self._done = done

    def emit(self, fn):  # noqa: ANN001 - Qt-like signal
        try:
            fn()
        finally:
            self._done.set()


class _FakeCaptureUi:
    def __init__(self, *, output_dir: Path, frame: FrameBundle) -> None:
        self._app_ctx = type(
            "_AppCtx",
            (),
            {
                "has_project": False,
                "project_root": None,
                "io": _FakeIo(),
                "commands": _FakeCommands(),
            },
        )()
        self._service = _FakeService(frame)
        self._save_formats = _FakeSaveFormats(rgb=True, depth=False)
        self._output_dir_edit = _FakeEdit(str(output_dir))
        self._device_combo = _FakeDeviceCombo()
        self._status: list[str] = []
        self._done = Event()
        self._ui_invoke = _FakeInvoker(self._done)

    def _publish_status(self, msg: str) -> None:
        self._status.append(str(msg))

    def _refresh_controls(self) -> None:
        return

    def on_capture_saved(self, *, relative_path: str) -> None:
        self._status.append(f"HOOK:{relative_path}")

    def close(self) -> None:
        self._app_ctx.io.close()


def test_capture_saves_without_project(tmp_path: Path) -> None:
    rgb = np.zeros((32, 32, 3), dtype=np.uint8)
    rgb[:, :, 0] = 255
    frame = FrameBundle(rgb=rgb, timestamp_s=1.0, source_id="test")

    ui = _FakeCaptureUi(output_dir=tmp_path, frame=frame)
    try:
        save_controls.on_capture_clicked(ui)
        assert ui._done.wait(5.0), "capture write callback did not complete"

        # Expect a file under <output>/<camera>/rgb/*.jpg (camera defaults to "camera").
        jpgs = list((tmp_path / "camera" / "rgb").glob("camera_*.jpg"))
        assert jpgs, f"expected capture jpg in {tmp_path}"

        # No project => no media registration, but hook should still run with a stable rel path.
        assert any(s.startswith("HOOK:") for s in ui._status), ui._status
        assert any("Saved:" in s for s in ui._status), ui._status
    finally:
        ui.close()

