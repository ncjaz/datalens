"""Reusable background persistence queue for debounced saves (V2).

This is a generalized version of the V1 persistence queue pattern:

1) merge (UI thread)
2) snapshot (UI thread)
3) save (background worker)

It is intentionally generic so it can be reused for SQLite-backed and file-backed
persists (e.g. annotations, indexes, derived project metadata).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Deque, Hashable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from datalens.core.logging import get_logger


MergeCallback = Callable[[set[Hashable], bool, Sequence[Any]], bool]
SnapshotCallback = Callable[[], Any]
SaveCallback = Callable[[Any], Optional[bool]]


class PersistenceQueue(QObject):
    """Manage debounced diffs and serialize saves on a dedicated worker thread.

    Callbacks:

    - `merge_func(keys, full_refresh, payloads) -> bool`:
      Runs on the UI thread after the debounce timer fires. Returns True if a
      snapshot should be taken.
    - `snapshot_func() -> payload | None`:
      Runs on the UI thread immediately after a successful merge. Must return an
      immutable payload suitable for background work.
    - `save_func(payload) -> bool|None`:
      Runs on the background worker and performs I/O.

    Controls:
    - `max_pending_jobs`: bound queued snapshots while a worker is busy.
    - `drop_oldest_pending`: choose which snapshots to drop when trimming.
    """

    jobFinished = Signal(object)
    jobFailed = Signal(object, object)

    def __init__(
        self,
        *,
        parent: QObject | None = None,
        merge_func: MergeCallback,
        snapshot_func: SnapshotCallback,
        save_func: SaveCallback,
        debounce_ms: int = 250,
        name: str = "PersistenceQueue",
        use_worker: bool = True,
        max_pending_jobs: int | None = None,
        drop_oldest_pending: bool = True,
    ) -> None:
        super().__init__(parent)
        self._log = get_logger(__name__)
        self._name = str(name)
        self._merge_func = merge_func
        self._snapshot_func = snapshot_func
        self._save_func = save_func
        self._use_worker = bool(use_worker)
        self._max_pending_jobs = (
            int(max_pending_jobs)
            if isinstance(max_pending_jobs, int) and max_pending_jobs > 0
            else None
        )
        self._drop_oldest_pending = bool(drop_oldest_pending)

        self._pending_keys: set[Hashable] = set()
        self._pending_full_refresh = False
        self._pending_payloads: list[Any] = []

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(max(0, int(debounce_ms)))
        self._debounce_timer.timeout.connect(self._flush_pending)  # type: ignore[arg-type]

        self._job_queue: Deque[Any] = deque()
        self._executor: ThreadPoolExecutor | None = None
        if self._use_worker:
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f"{self._name}Worker"
            )
        self._active_future: Future | None = None
        self._shutdown = False
        self._suspended = False

    def enqueue(
        self,
        *,
        keys: Iterable[Hashable] | None = None,
        payload: Any = None,
        full_refresh: bool = False,
        immediate: bool = False,
    ) -> None:
        """Queue a diff for persistence."""
        if self._shutdown:
            return
        if keys:
            self._pending_keys.update(keys)
        if payload is not None:
            self._pending_payloads.append(payload)
        if full_refresh:
            self._pending_full_refresh = True

        if self._suspended:
            return

        if immediate:
            self.flush()
            return

        self._debounce_timer.start()

    def flush(self) -> None:
        """Flush pending diffs (does not wait for background jobs)."""
        if self._shutdown:
            return
        if self._suspended:
            return
        self._debounce_timer.stop()
        self._flush_pending()

    def finish(self) -> None:
        """Flush pending diffs and wait for all queued saves to finish."""
        was_suspended = self._suspended
        if was_suspended:
            self._suspended = False
        self.flush()
        self._drain_jobs()
        self._suspended = was_suspended

    def shutdown(self) -> None:
        """Flush, wait for pending jobs, and stop the executor."""
        if self._shutdown:
            return
        self.finish()
        if self._executor is not None:
            self._executor.shutdown(wait=True)
        self._shutdown = True

    def pause(self) -> None:
        """Suspend debounce/merge processing until `resume()` is called."""
        if self._suspended:
            return
        self._suspended = True
        self._debounce_timer.stop()

    def resume(self, *, flush_pending: bool = True) -> None:
        """Resume processing after a `pause()`."""
        if not self._suspended:
            return
        self._suspended = False
        if not flush_pending:
            return
        if self._pending_full_refresh or self._pending_keys or self._pending_payloads:
            self._flush_pending()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _flush_pending(self) -> None:
        if self._suspended:
            return
        if not (self._pending_full_refresh or self._pending_keys or self._pending_payloads):
            return

        keys = set(self._pending_keys)
        payloads = list(self._pending_payloads)
        full_refresh = self._pending_full_refresh
        self._pending_keys.clear()
        self._pending_payloads.clear()
        self._pending_full_refresh = False

        try:
            should_snapshot = self._merge_func(keys, full_refresh, payloads)
        except Exception:
            self._log.exception(
                "PersistenceQueue merge callback failed",
                extra={"operation": "persistence_queue", "phase": "error", "name": self._name},
            )
            return

        if not should_snapshot:
            return

        try:
            job_payload = self._snapshot_func()
        except Exception:
            self._log.exception(
                "PersistenceQueue snapshot callback failed",
                extra={"operation": "persistence_queue", "phase": "error", "name": self._name},
            )
            return

        if job_payload is None:
            return

        self._job_queue.append(job_payload)
        self._trim_pending_jobs()
        self._try_start_job()

    def _try_start_job(self) -> None:
        if self._shutdown:
            return
        if not self._job_queue:
            return
        if not self._use_worker:
            while self._job_queue:
                payload = self._job_queue.popleft()
                success, payload, error = self._run_job(payload)
                self._emit_completion(success, payload, error)
            return
        if self._active_future is not None and not self._active_future.done():
            return
        if self._executor is None:
            return
        payload = self._job_queue.popleft()
        self._active_future = self._executor.submit(self._run_job, payload)

        def _notify(future: Future) -> None:
            QTimer.singleShot(0, lambda: self._handle_future_completion(future))

        self._active_future.add_done_callback(_notify)

    def _run_job(self, payload: Any) -> tuple[bool, Any, BaseException | None]:
        try:
            result = self._save_func(payload)
            success = True if result is None else bool(result)
            return success, payload, None
        except Exception as exc:  # pragma: no cover - worker thread logging
            self._log.exception(
                "PersistenceQueue worker failed while saving",
                extra={"operation": "persistence_queue", "phase": "error", "name": self._name},
            )
            return False, payload, exc

    def _handle_future_completion(self, future: Future) -> None:
        if future is not self._active_future:
            return
        self._active_future = None
        try:
            success, payload, error = future.result()
        except Exception as exc:  # pragma: no cover - defensive
            self._log.exception(
                "PersistenceQueue future raised unexpectedly",
                extra={"operation": "persistence_queue", "phase": "error", "name": self._name},
            )
            success, payload, error = False, None, exc
        self._emit_completion(bool(success), payload, error)
        self._try_start_job()

    def _emit_completion(self, success: bool, payload: Any, error: BaseException | None) -> None:
        if success:
            self.jobFinished.emit(payload)
        else:
            self.jobFailed.emit(payload, error)

    def _trim_pending_jobs(self) -> None:
        if self._max_pending_jobs is None:
            return
        while len(self._job_queue) > self._max_pending_jobs:
            dropped = self._job_queue.popleft() if self._drop_oldest_pending else self._job_queue.pop()
            self._log.debug(
                "Dropped pending PersistenceQueue job",
                extra={
                    "operation": "persistence_queue",
                    "phase": "debug",
                    "name": self._name,
                    "dropped": type(dropped).__name__,
                    "max_pending_jobs": self._max_pending_jobs,
                },
            )

    def _drain_jobs(self) -> None:
        if self._use_worker:
            future = self._active_future
            if future is not None:
                self._handle_future_completion(future)
                self._active_future = None
            while self._job_queue:
                payload = self._job_queue.popleft()
                success, _, error = self._run_job(payload)
                self._emit_completion(success, payload, error)
        else:
            while self._job_queue:
                payload = self._job_queue.popleft()
                success, payload, error = self._run_job(payload)
                self._emit_completion(success, payload, error)

