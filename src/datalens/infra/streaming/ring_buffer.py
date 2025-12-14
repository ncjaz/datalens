from __future__ import annotations

from dataclasses import dataclass
from threading import Condition, RLock
from typing import Callable, Generic, Iterable, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RingBufferItem(Generic[T]):
    """An item stored in a :class:`RingBuffer` along with its sequence number."""

    seq: int
    value: T


@dataclass(frozen=True)
class ReadSinceResult(Generic[T]):
    """
    Result of :meth:`RingBuffer.read_since`.

    `dropped` indicates that the caller asked for data that was already evicted
    (i.e., the consumer fell behind the buffer capacity).
    """

    items: tuple[RingBufferItem[T], ...]
    dropped: bool
    oldest_seq: Optional[int]
    newest_seq: Optional[int]


class Subscription:
    """Handle returned by :meth:`RingBuffer.subscribe`."""

    def __init__(self, unsubscribe: Callable[[], None]) -> None:
        self._unsubscribe = unsubscribe
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._unsubscribe()

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()


class RingBuffer(Generic[T]):
    """
    Thread-safe fixed-capacity ring buffer with sequence numbers.

    Design goals:
    - O(1) append (drop-oldest when full).
    - Consumers can read "latest" or "since last seen" without blocking writers.
    - Supports both polling (`latest_if_changed`) and callbacks (`subscribe`).

    Notes
    -----
    - Stored values are kept by reference. For large payloads (images, numpy
      arrays, tensors), prefer storing immutable objects or shared "refs" rather
      than copying bytes into the buffer.
    - Subscriber callbacks run on the thread calling :meth:`append`.
    """

    def __init__(self, capacity: int = 16) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._capacity = int(capacity)
        self._buf: list[Optional[RingBufferItem[T]]] = [None] * self._capacity
        self._head = 0  # next write index
        self._count = 0
        self._seq = -1
        self._lock = RLock()
        self._cond = Condition(self._lock)
        self._subscribers: dict[int, Callable[[RingBufferItem[T]], None]] = {}
        self._next_subscriber_id = 1

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        with self._lock:
            return self._count

    def _oldest_index_unlocked(self) -> int:
        return (self._head - self._count) % self._capacity

    def _oldest_seq_unlocked(self) -> Optional[int]:
        if self._count == 0:
            return None
        return self._seq - self._count + 1

    def append(self, value: T) -> int:
        """Append a value and return the assigned sequence number."""
        callbacks: list[Callable[[RingBufferItem[T]], None]]
        item: RingBufferItem[T]
        with self._lock:
            self._seq += 1
            item = RingBufferItem(seq=self._seq, value=value)
            self._buf[self._head] = item
            self._head = (self._head + 1) % self._capacity
            self._count = min(self._count + 1, self._capacity)
            callbacks = list(self._subscribers.values())
            self._cond.notify_all()

        for callback in callbacks:
            try:
                callback(item)
            except Exception:
                # Callbacks are best-effort; producers should not be destabilised
                # by consumer errors.
                continue
        return item.seq

    def latest(self) -> Optional[RingBufferItem[T]]:
        """Return the most recent item, or None if empty."""
        with self._lock:
            if self._count == 0:
                return None
            idx = (self._head - 1) % self._capacity
            return self._buf[idx]

    def latest_seq(self) -> Optional[int]:
        """Return the newest sequence number, or None if empty."""
        with self._lock:
            return None if self._count == 0 else self._seq

    def latest_if_changed(self, last_seen_seq: Optional[int]) -> Optional[RingBufferItem[T]]:
        """
        Return the latest item only if it is newer than `last_seen_seq`.

        This is the recommended polling API for consumers that run at their own
        cadence (e.g., UI redraw at 30 Hz vs capture at 120 Hz).
        """
        item = self.latest()
        if item is None:
            return None
        if last_seen_seq is None or item.seq > last_seen_seq:
            return item
        return None

    def wait_for_change(
        self, last_seen_seq: Optional[int], timeout_s: Optional[float] = None
    ) -> Optional[RingBufferItem[T]]:
        """
        Block until a new item arrives (seq > `last_seen_seq`) or timeout.

        Returns the latest item (not every intermediate item). This is useful in
        non-Qt worker loops. UI code should generally use callbacks or timers.
        """
        with self._lock:
            if self._count == 0:
                if not self._cond.wait(timeout=timeout_s):
                    return None
                return self.latest()

            if last_seen_seq is None:
                return self.latest()

            def _predicate() -> bool:
                return self._count > 0 and self._seq > last_seen_seq

            if not self._cond.wait_for(_predicate, timeout=timeout_s):
                return None
            return self.latest()

    def snapshot(self) -> tuple[RingBufferItem[T], ...]:
        """Return all currently stored items from oldest to newest."""
        with self._lock:
            if self._count == 0:
                return ()
            oldest_idx = self._oldest_index_unlocked()
            items: list[RingBufferItem[T]] = []
            for i in range(self._count):
                idx = (oldest_idx + i) % self._capacity
                item = self._buf[idx]
                if item is not None:
                    items.append(item)
            return tuple(items)

    def recent(self, count: int) -> tuple[RingBufferItem[T], ...]:
        """Return up to `count` most recent items, ordered oldest to newest."""
        if count <= 0:
            return ()
        with self._lock:
            if self._count == 0:
                return ()
            take = min(int(count), self._count)
            start_idx = (self._head - take) % self._capacity
            items: list[RingBufferItem[T]] = []
            for i in range(take):
                idx = (start_idx + i) % self._capacity
                item = self._buf[idx]
                if item is not None:
                    items.append(item)
            return tuple(items)

    def read_since(self, last_seen_seq: int) -> ReadSinceResult[T]:
        """
        Return items newer than `last_seen_seq` that are still retained.

        If the consumer fell behind (requested seq is older than the buffer's
        oldest item), `dropped=True` and the returned items start at the oldest
        retained sequence.
        """
        with self._lock:
            oldest_seq = self._oldest_seq_unlocked()
            newest_seq = None if self._count == 0 else self._seq
            if oldest_seq is None or newest_seq is None:
                return ReadSinceResult(items=(), dropped=False, oldest_seq=None, newest_seq=None)

            requested_next = int(last_seen_seq) + 1
            dropped = requested_next < oldest_seq
            start_seq = max(requested_next, oldest_seq)
            if start_seq > newest_seq:
                return ReadSinceResult(items=(), dropped=dropped, oldest_seq=oldest_seq, newest_seq=newest_seq)

            oldest_idx = self._oldest_index_unlocked()
            items: list[RingBufferItem[T]] = []
            for seq in range(start_seq, newest_seq + 1):
                offset = seq - oldest_seq
                idx = (oldest_idx + offset) % self._capacity
                item = self._buf[idx]
                if item is not None and item.seq == seq:
                    items.append(item)

            return ReadSinceResult(
                items=tuple(items),
                dropped=dropped,
                oldest_seq=oldest_seq,
                newest_seq=newest_seq,
            )

    def subscribe(self, callback: Callable[[RingBufferItem[T]], None]) -> Subscription:
        """
        Subscribe to new items.

        The callback is invoked with the appended item on the thread that calls
        :meth:`append`.
        """
        with self._lock:
            sub_id = self._next_subscriber_id
            self._next_subscriber_id += 1
            self._subscribers[sub_id] = callback

        def _unsubscribe() -> None:
            with self._lock:
                self._subscribers.pop(sub_id, None)

        return Subscription(_unsubscribe)

    def extend(self, values: Iterable[T]) -> Optional[int]:
        """Append multiple values. Returns the last sequence number if any appended."""
        last_seq: Optional[int] = None
        for value in values:
            last_seq = self.append(value)
        return last_seq

