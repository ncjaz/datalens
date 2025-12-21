from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
import threading
import time
from typing import Any, Optional

from datalens.core.app_settings import load_app_settings, save_app_settings
from datalens.domain.system.settings import AppSettings
from datalens.infra.paths import settings_json_path


_locks: dict[Path, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    resolved = path.resolve()
    with _locks_guard:
        lock = _locks.get(resolved)
        if lock is None:
            lock = threading.Lock()
            _locks[resolved] = lock
        return lock


class SettingsStore:
    """
    Convenience helper around the persisted `settings.json`.

    Goals:

    - Make it easy to safely update settings without repeating load/replace/save
      boilerplate.
    - Keep writes atomic (delegates to `save_app_settings`).
    - Be safe for use from background threads (no Qt dependencies).
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or settings_json_path()
        self._lock = _lock_for(self._path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> AppSettings:
        with self._lock:
            return load_app_settings(self._path)

    def save(self, settings: AppSettings) -> None:
        with self._lock:
            save_app_settings(self._path, settings)

    def apply(
        self,
        mutator: Callable[[AppSettings], AppSettings],
        *,
        save: bool = True,
    ) -> tuple[AppSettings, bool]:
        """
        Atomically load -> mutate -> save the settings.

        The `mutator` must be side-effect free and return a new `AppSettings`
        instance (use `dataclasses.replace`).
        """
        with self._lock:
            current = load_app_settings(self._path)
            updated = mutator(current)
            changed = updated != current
            if changed and save:
                save_app_settings(self._path, updated)
            return updated, changed

    def update(self, mutator: Callable[[AppSettings], AppSettings], *, save: bool = True) -> AppSettings:
        updated, _ = self.apply(mutator, save=save)
        return updated

    def update_fields(self, **kwargs: Any) -> AppSettings:
        """
        Convenience wrapper for simple top-level updates.

        Example:
            store.update_fields(theme_name="default")
        """

        def mutator(current: AppSettings) -> AppSettings:
            return replace(current, **kwargs)

        return self.update(mutator)


class DebouncedSettingsWriter:
    """
    Background settings writer that coalesces rapid updates.

    This is useful for UI flows that generate frequent changes (toggles, sliders)
    without blocking the UI thread on disk IO.
    """

    def __init__(self, store: SettingsStore | None = None, *, debounce_seconds: float = 0.25) -> None:
        self._store = store or SettingsStore()
        self._debounce_seconds = max(0.0, float(debounce_seconds))

        self._lock = threading.Lock()
        self._pending: Optional[AppSettings] = None
        self._wake = threading.Event()
        self._stop = threading.Event()

        self._thread = threading.Thread(target=self._run, name="SettingsWriter", daemon=True)
        self._thread.start()

    @property
    def path(self) -> Path:
        return self._store.path

    def request_save(self, settings: AppSettings) -> None:
        """
        Schedule a save of `settings` in the background.

        Only the latest requested settings are written after the debounce window.
        """
        with self._lock:
            self._pending = settings
            self._wake.set()

    def request_update(self, mutator: Callable[[AppSettings], AppSettings]) -> AppSettings:
        """
        Compute updated settings under the settings file lock, then schedule a
        debounced write of the result (no immediate disk IO).
        """
        updated, changed = self._store.apply(mutator, save=False)
        if changed:
            self.request_save(updated)
        return updated

    def flush(self) -> None:
        """Force any pending write to be committed now."""
        with self._lock:
            pending = self._pending
            self._pending = None
            self._wake.clear()
        if pending is not None:
            self._store.save(pending)

    def close(self) -> None:
        """Stop the writer thread (flushes pending updates)."""
        self.flush()
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait()
            if self._stop.is_set():
                return

            # Debounce window: wait until there have been no new requests for
            # `debounce_seconds`. Important: `Event.wait()` does not clear the
            # event; we must clear it ourselves between waits to avoid a
            # zero-sleep busy loop when the event remains set.
            while True:
                self._wake.clear()
                if self._stop.is_set():
                    return
                # If a new request comes in, extend the window.
                if self._wake.wait(timeout=self._debounce_seconds):
                    continue
                break

            with self._lock:
                pending = self._pending
                self._pending = None

            if pending is not None:
                self._store.save(pending)


_DEFAULT_STORE: SettingsStore | None = None
_DEFAULT_WRITER: DebouncedSettingsWriter | None = None
_DEFAULT_WRITER_LOCK = threading.Lock()


def default_settings_store() -> SettingsStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = SettingsStore()
    return _DEFAULT_STORE


def default_debounced_settings_writer(*, debounce_seconds: float = 0.25) -> DebouncedSettingsWriter:
    """
    Return a shared DebouncedSettingsWriter instance for the process.

    This avoids spawning multiple background writer threads across short-lived
    dialogs/widgets (welcome, preferences, etc.).
    """
    global _DEFAULT_WRITER
    with _DEFAULT_WRITER_LOCK:
        if _DEFAULT_WRITER is None:
            _DEFAULT_WRITER = DebouncedSettingsWriter(default_settings_store(), debounce_seconds=debounce_seconds)
        return _DEFAULT_WRITER
