from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, DefaultDict

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId

log = get_logger(__name__)

EventName = str
EventCallback = Callable[[object], None]
UiScheduler = Callable[[Callable[[], None]], None]


@dataclass(frozen=True)
class Subscription:
    """
    Subscription token returned by :meth:`EventHub.subscribe`.

    Call :meth:`unsubscribe` to stop receiving events.
    """

    unsubscribe: Callable[[], None]


@dataclass(frozen=True)
class EventEnvelope:
    """
    Metadata wrapper around a published event.

    This exists to support future "event monitor" UI:
    consumers can render a stream of recent envelopes without coupling to the
    publisher.
    """

    name: EventName
    payload: object
    published_at_s: float
    publisher_thread_id: int


# ---------------------------------------------------------------------------
# Minimal payload dataclasses (Qt-free)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectOpened:
    project_root: Path
    timestamp_s: float


@dataclass(frozen=True)
class ProjectClosing:
    project_root: Path
    reason: str
    timestamp_s: float


@dataclass(frozen=True)
class ProjectClosed:
    project_root: Path
    timestamp_s: float


@dataclass(frozen=True)
class ProjectOpenFailed:
    project_root: Path
    error: str
    timestamp_s: float


@dataclass(frozen=True)
class ActiveProjectChanged:
    previous_root: Path | None
    current_root: Path | None
    timestamp_s: float


@dataclass(frozen=True)
class PluginEnabled:
    plugin_id: PluginId
    timestamp_s: float


@dataclass(frozen=True)
class PluginDisabled:
    plugin_id: PluginId
    timestamp_s: float


@dataclass(frozen=True)
class PluginsEnabledChanged:
    enabled_plugin_ids: tuple[PluginId, ...]
    timestamp_s: float


@dataclass(frozen=True)
class FocusedWorkspaceChanged:
    previous_plugin_id: PluginId | None
    current_plugin_id: PluginId | None
    timestamp_s: float


class EventHub:
    """
    App-wide event hub for semantic coordination across UI/services/plugins.

    Design intent:
    - :meth:`publish` is non-blocking (enqueue + schedule one UI drain tick).
    - subscriber callbacks are delivered queued on the UI thread by default.
    - callbacks must be fast; heavy work should be scheduled onto background
      systems (loader/threadpool/IoWriter) and results marshaled back to UI.

    This is not a replacement for Qt signals for local widget wiring.
    """

    # Project lifecycle (V2)
    PROJECT_OPENED: EventName = "ProjectOpened"
    PROJECT_CLOSING: EventName = "ProjectClosing"
    PROJECT_CLOSED: EventName = "ProjectClosed"
    PROJECT_OPEN_FAILED: EventName = "ProjectOpenFailed"
    ACTIVE_PROJECT_CHANGED: EventName = "ActiveProjectChanged"

    # Plugin lifecycle / UX state (V2)
    PLUGIN_ENABLED: EventName = "PluginEnabled"
    PLUGIN_DISABLED: EventName = "PluginDisabled"
    PLUGINS_ENABLED_CHANGED: EventName = "PluginsEnabledChanged"
    FOCUSED_WORKSPACE_CHANGED: EventName = "FocusedWorkspaceChanged"

    # Cross-cutting (from docs/events.md, implemented as names only for now)
    MEDIA_LIST_UPDATED: EventName = "MediaListUpdated"
    MEDIA_DISCOVERED: EventName = "MediaDiscovered"
    MEDIA_REMOVED: EventName = "MediaRemoved"
    ANNOTATIONS_CHANGED: EventName = "AnnotationsChanged"
    MODEL_STATE_CHANGED: EventName = "ModelStateChanged"
    VIEW_MODE_CHANGED: EventName = "ViewModeChanged"
    SHORTCUT_MODE_CHANGED: EventName = "ShortcutModeChanged"
    ISOLATION_CHANGED: EventName = "IsolationChanged"
    PREVIOUS_BOXES_VISIBILITY_CHANGED: EventName = "PreviousBoxesVisibilityChanged"
    TRAINING_SPLITS_CHANGED: EventName = "TrainingSplitsChanged"
    TRAINING_RUNS_CHANGED: EventName = "TrainingRunsChanged"
    TRAINING_RUN_QUEUED: EventName = "TrainingRunQueued"
    TRAINING_RUN_STARTED: EventName = "TrainingRunStarted"
    TRAINING_RUN_PROGRESS: EventName = "TrainingRunProgress"
    TRAINING_RUN_COMPLETED: EventName = "TrainingRunCompleted"
    TRAINING_RUN_FAILED: EventName = "TrainingRunFailed"

    ANY: EventName = "*"

    def __init__(self, *, history_size: int = 200) -> None:
        self._lock = threading.Lock()
        self._subscriptions: DefaultDict[EventName, list[tuple[int, EventCallback]]] = defaultdict(list)
        self._queue: deque[EventEnvelope] = deque()
        self._scheduled = False

        self._ui_scheduler: UiScheduler | None = None
        self._ui_thread_id: int | None = None

        self._next_id = 1
        self._history: deque[EventEnvelope] = deque(maxlen=max(0, int(history_size)))

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def attach_ui_scheduler(self, scheduler: UiScheduler) -> None:
        """
        Attach a scheduler that runs callables on the Qt UI thread.

        Typically called once at app startup (after QApplication exists).
        """
        with self._lock:
            self._ui_scheduler = scheduler
            self._ui_thread_id = threading.get_ident()
        self._schedule_drain()

    @property
    def ui_thread_id(self) -> int | None:
        return self._ui_thread_id

    # ------------------------------------------------------------------
    # Subscription API
    # ------------------------------------------------------------------

    def subscribe(self, name: EventName, callback: EventCallback) -> Subscription:
        """
        Subscribe to a specific event name, or ``EventHub.ANY`` for all events.
        """
        if not isinstance(name, str) or not name:
            raise ValueError("Event name must be a non-empty string")

        with self._lock:
            sub_id = self._next_id
            self._next_id += 1
            self._subscriptions[name].append((sub_id, callback))

        def _unsubscribe() -> None:
            with self._lock:
                items = self._subscriptions.get(name, [])
                self._subscriptions[name] = [(i, cb) for (i, cb) in items if i != sub_id]
                if not self._subscriptions[name]:
                    self._subscriptions.pop(name, None)

        return Subscription(unsubscribe=_unsubscribe)

    # ------------------------------------------------------------------
    # Publish / delivery
    # ------------------------------------------------------------------

    def publish(self, name: EventName, payload: object) -> None:
        """
        Publish an event.

        Safe to call from any thread. Delivery is queued on the UI thread.
        """
        envelope = EventEnvelope(
            name=name,
            payload=payload,
            published_at_s=time.time(),
            publisher_thread_id=threading.get_ident(),
        )
        with self._lock:
            self._queue.append(envelope)
            if self._history.maxlen:
                self._history.append(envelope)
        self._schedule_drain()

    def history_snapshot(self) -> list[EventEnvelope]:
        """Return a snapshot of recent published events (for future UI tooling)."""
        with self._lock:
            return list(self._history)

    # ------------------------------------------------------------------

    def _schedule_drain(self) -> None:
        with self._lock:
            if self._scheduled:
                return
            scheduler = self._ui_scheduler
            if scheduler is None:
                return
            self._scheduled = True
        try:
            scheduler(self._drain_on_ui_thread)
        except Exception:
            with self._lock:
                self._scheduled = False
            log.warning("Failed to schedule EventHub drain (best-effort)", exc_info=True)

    def _drain_on_ui_thread(self) -> None:
        with self._lock:
            self._scheduled = False

        while True:
            with self._lock:
                if not self._queue:
                    return
                envelope = self._queue.popleft()
                callbacks = list(self._subscriptions.get(envelope.name, ()))
                callbacks_all = list(self._subscriptions.get(self.ANY, ()))

            for _, cb in callbacks_all + callbacks:
                try:
                    cb(envelope.payload)
                except Exception:
                    log.exception(
                        "EventHub subscriber failed",
                        extra={
                            "operation": "event_hub",
                            "phase": "subscriber_error",
                            "event": envelope.name,
                            "subscriber": getattr(cb, "__qualname__", repr(cb)),
                        },
                    )

            with self._lock:
                if self._queue and self._ui_scheduler is not None:
                    # Avoid starving paint/input: keep delivery in discrete ticks.
                    pass
                else:
                    return
            self._schedule_drain()
            return
