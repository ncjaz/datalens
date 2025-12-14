from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class _IoTask:
    fn: Callable[[], Any]
    future: Future[Any]


class IoWriter:
    """
    Simple async file writer.

    Intended for small/medium writes that must not block the UI thread:
    - JSON metadata
    - exported manifests
    - small caches/configs inside a project

    This is not intended for high-rate media capture (frames/video).
    """

    def __init__(self) -> None:
        self._tasks: queue.Queue[_IoTask | None] = queue.Queue()
        self._closed = False
        self._lock = threading.Lock()

        self._thread = threading.Thread(target=self._run, name="IoWriter", daemon=True)
        self._thread.start()

    def submit(self, fn: Callable[[], T]) -> Future[T]:
        with self._lock:
            if self._closed:
                future: Future[T] = Future()
                future.set_exception(RuntimeError("IoWriter is closed"))
                return future
        future: Future[T] = Future()
        self._tasks.put(_IoTask(fn=fn, future=future))
        return future

    def write_text_atomic(self, path: Path, text: str, *, encoding: str = "utf-8") -> Future[None]:
        p = Path(path)
        content = str(text)

        def write() -> None:
            _atomic_write_text(p, content, encoding=encoding)

        return self.submit(write)

    def write_bytes_atomic(self, path: Path, data: bytes) -> Future[None]:
        p = Path(path)
        payload = bytes(data)

        def write() -> None:
            _atomic_write_bytes(p, payload)

        return self.submit(write)

    def write_json_atomic(
        self,
        path: Path,
        payload: object,
        *,
        indent: int = 2,
        sort_keys: bool = True,
    ) -> Future[None]:
        p = Path(path)
        data = json.dumps(payload, indent=indent, sort_keys=sort_keys)
        return self.write_text_atomic(p, data + "\n", encoding="utf-8")

    def flush(self) -> Future[None]:
        """
        Barrier operation: completes after all previously queued tasks complete.

        Note: do not call `future.result()` on the UI thread. Use the loader or
        a background stage to wait.
        """

        def barrier() -> None:
            return None

        future: Future[None] = self.submit(barrier)
        return future

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._tasks.put(None)
        self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while True:
            task = self._tasks.get()
            if task is None:
                return
            if task.future.cancelled():
                continue
            try:
                result = task.fn()
                task.future.set_result(result)
            except Exception as exc:
                task.future.set_exception(exc)


_DEFAULT_IO_WRITER: Optional[IoWriter] = None
_DEFAULT_IO_WRITER_LOCK = threading.Lock()


def default_io_writer() -> IoWriter:
    global _DEFAULT_IO_WRITER
    with _DEFAULT_IO_WRITER_LOCK:
        if _DEFAULT_IO_WRITER is None:
            _DEFAULT_IO_WRITER = IoWriter()
        return _DEFAULT_IO_WRITER


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    tmp.replace(path)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
