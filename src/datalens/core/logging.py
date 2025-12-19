"""
Central logging (V2).

This module provides a single, async, app-wide logging pipeline suitable for
Qt applications (non-blocking UI) and a plugin runtime (strong attribution).

Design:

- All logs enqueue from the caller thread via a QueueHandler (O(1)).
- A QueueListener thread performs formatting + file writes (RotatingFileHandler).
- A bounded queue drops records on overflow (never block UI).

Attribution:

- Records are enriched with fields like `layer`, `subsystem`, `execution`,
  `plugin_id`, and optional hook/migration metadata.
- Most fields are inferred from the logger name (`__name__`) and current thread,
  with overrides supported via context binding or LoggerAdapter extras.

Pairing / related systems:

- Plugin lifecycle: `datalens/services/plugins/runtime/host.py`
- Shared executors that should propagate logging context:
  - DB: `datalens/services/db/project_db.py`
  - IO: `datalens/services/background_io/writer.py`
"""

from __future__ import annotations

import atexit
import contextvars
import logging
import logging.handlers
import queue
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

from datalens.infra.paths import datalens_user_data_dir


_LOG_CONTEXT: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "datalens_log_context",
    default={},
)

@dataclass(frozen=True, slots=True)
class LoaderDialogSinkPolicy:
    show_log_progress: bool = True
    show_log_info: bool = False
    show_log_warning: bool = False
    show_log_error: bool = False
    show_log_critical: bool = False


_LOADER_DIALOG_SINK: contextvars.ContextVar[
    tuple[Callable[[str, float | None], None], LoaderDialogSinkPolicy] | None
] = contextvars.ContextVar(
    "datalens_loader_dialog_sink",
    default=None,
)


def _infer_layer(logger_name: str) -> str:
    if logger_name.startswith("datalens.ui."):
        return "ui"
    if logger_name.startswith("datalens.services."):
        return "service"
    if logger_name.startswith("datalens.infra."):
        return "infra"
    if logger_name.startswith("datalens.core."):
        return "core"
    if logger_name.startswith("datalens.domain."):
        return "domain"
    if logger_name.startswith(("datalens.plugins.", "datalens._plugins.")):
        return "plugin"
    if logger_name.startswith("datalens."):
        return "app"
    return "external"


_SUBSYSTEM_PREFIXES: tuple[tuple[str, str], ...] = (
    ("datalens.services.db.", "db"),
    ("datalens.services.background_io.", "io"),
    ("datalens.infra.background.", "background"),
    ("datalens.services.plugins.", "plugins"),
    ("datalens.services.project_service", "project"),
    ("datalens.services.settings_store", "settings"),
    ("datalens.services.config_service", "settings"),
    ("datalens.core.events", "events"),
    ("datalens.infra.streaming", "streaming"),
    ("datalens.infra.commands", "commands"),
    ("datalens.infra.events", "events"),
)


def _infer_subsystem(logger_name: str, *, layer: str) -> str:
    for prefix, subsystem in _SUBSYSTEM_PREFIXES:
        if logger_name.startswith(prefix):
            return subsystem
    if layer == "plugin":
        return "plugins"
    return layer


def _infer_execution() -> str:
    current = threading.current_thread()
    if current is threading.main_thread():
        return "ui"

    name = current.name or ""
    if name.startswith("ProjectDb("):
        return "db"
    if name == "IoWriter":
        return "io"
    return "background"


def _default_component(logger_name: str) -> str:
    parts = logger_name.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return logger_name


def _enrich_record(record: logging.LogRecord) -> None:
    """
    Enrich `record` with standard fields without overwriting explicit values.

    Important: This must run on the *caller thread* (before enqueue), otherwise
    `contextvars` and thread-derived fields (e.g. `execution`) would reflect the
    logging thread rather than the origin.
    """

    def present(value: object | None) -> bool:
        return value is not None and value != ""

    ctx = _LOG_CONTEXT.get() or {}

    layer = getattr(record, "layer", None)
    if not present(layer):
        layer = ctx.get("layer") if present(ctx.get("layer")) else _infer_layer(record.name)
        record.layer = layer

    subsystem = getattr(record, "subsystem", None)
    if not present(subsystem):
        override = ctx.get("subsystem")
        subsystem = override if present(override) else _infer_subsystem(record.name, layer=str(layer))
        record.subsystem = subsystem

    component = getattr(record, "component", None)
    if not present(component):
        override = ctx.get("component")
        record.component = override if present(override) else _default_component(record.name)

    execution = getattr(record, "execution", None)
    if not present(execution):
        override = ctx.get("execution")
        record.execution = override if present(override) else _infer_execution()

    if not present(getattr(record, "plugin_id", None)):
        override = ctx.get("plugin_id")
        record.plugin_id = override if present(override) else "-"

    if not present(getattr(record, "project_root", None)):
        override = ctx.get("project_root")
        record.project_root = override if present(override) else "-"

    if not present(getattr(record, "op_id", None)):
        override = ctx.get("op_id")
        record.op_id = override if present(override) else "-"

    if not present(getattr(record, "operation", None)):
        override = ctx.get("operation")
        record.operation = override if present(override) else "-"

    if not present(getattr(record, "phase", None)):
        override = ctx.get("phase")
        record.phase = override if present(override) else "-"

    if not present(getattr(record, "hook", None)):
        override = ctx.get("hook")
        record.hook = override if present(override) else "-"

    if not present(getattr(record, "plugin_phase", None)):
        override = ctx.get("plugin_phase")
        record.plugin_phase = override if present(override) else "-"

    # Attach any remaining context keys as record attributes for downstream
    # handlers/formatters, but never overwrite explicit extras.
    for key, value in ctx.items():
        if hasattr(record, key):
            continue
        setattr(record, key, value)

    # Optional: forward "progress" logs to the active loader dialog (if any).
    #
    # This is best-effort and must never raise or block. It runs on the caller
    # thread, which is important because the loader sink is stored in contextvars
    # and propagates to worker threads via `contextvars.copy_context()`.
    try:
        sink_tuple = _LOADER_DIALOG_SINK.get()
        if not sink_tuple:
            return
        sink, policy = sink_tuple
        if not callable(sink):
            return

        is_progress = bool(getattr(record, "progress", False) or getattr(record, "ui_progress", False))
        allowed = False
        if is_progress:
            allowed = bool(policy.show_log_progress)
        else:
            lvl = int(getattr(record, "levelno", logging.INFO))
            if lvl >= logging.CRITICAL:
                allowed = bool(policy.show_log_critical)
            elif lvl >= logging.ERROR:
                allowed = bool(policy.show_log_error)
            elif lvl >= logging.WARNING:
                allowed = bool(policy.show_log_warning)
            elif lvl >= logging.INFO:
                allowed = bool(policy.show_log_info)

        if allowed:
            plugin = getattr(record, "plugin_id", "-")
            prefix = ""
            if plugin not in ("", "-"):
                prefix = str(plugin)
            else:
                name = str(getattr(record, "name", "") or "")
                if name.startswith("datalens.plugins."):
                    parts = name.split(".")
                    if len(parts) >= 3 and parts[2]:
                        prefix = parts[2]
            text = record.getMessage()
            value_raw = getattr(record, "progress_value", None)
            value: float | None = None
            if isinstance(value_raw, (int, float)):
                v = float(value_raw)
                if v < 0.0:
                    v = 0.0
                if v > 1.0:
                    v = 1.0
                value = v

            if prefix:
                sink(f"{prefix}: {text}", value)
            else:
                sink(text, value)
    except Exception:
        pass


class CompactFormatter(logging.Formatter):
    """Human-friendly formatter that keeps optional context compact."""

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S")
        layer = getattr(record, "layer", _infer_layer(record.name))
        subsystem = getattr(record, "subsystem", _infer_subsystem(record.name, layer=str(layer)))
        execution = getattr(record, "execution", _infer_execution())
        component = getattr(record, "component", _default_component(record.name))
        base = (
            f"{ts}.{int(record.msecs):03d} | "
            f"{record.levelname:<8} | "
            f"{layer}/{subsystem} | "
            f"{execution} | "
            f"{component}"
        )

        ctx_bits: list[str] = []
        if getattr(record, "plugin_id", "-") not in ("", "-"):
            ctx_bits.append(f"plugin={record.plugin_id}")
        if getattr(record, "hook", "-") not in ("", "-"):
            ctx_bits.append(f"hook={record.hook}")
        if getattr(record, "operation", "-") not in ("", "-"):
            ctx_bits.append(f"op={record.operation}")
        if getattr(record, "phase", "-") not in ("", "-"):
            ctx_bits.append(f"phase={record.phase}")
        if getattr(record, "op_id", "-") not in ("", "-"):
            ctx_bits.append(f"id={record.op_id}")

        if ctx_bits:
            base = f"{base} | " + " ".join(ctx_bits)

        msg = record.getMessage()
        if record.exc_info:
            msg = f"{msg}\n{self.formatException(record.exc_info)}"
        return f"{base} | {msg}"


class DroppingQueueHandler(logging.handlers.QueueHandler):
    """
    QueueHandler that never blocks the caller thread.

    When the queue is full, records are dropped and a minimal notice is written
    to stderr periodically (without using logging, to avoid recursion).
    """

    def __init__(self, log_queue: "queue.Queue[logging.LogRecord]", *, notice_interval_s: float = 5.0) -> None:
        super().__init__(log_queue)
        self._dropped = 0
        self._last_notice = 0.0
        self._notice_interval_s = max(0.1, float(notice_interval_s))

    @property
    def dropped_count(self) -> int:
        return self._dropped

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        _enrich_record(record)
        return record

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self._dropped += 1
            now = time.monotonic()
            if now - self._last_notice >= self._notice_interval_s:
                self._last_notice = now
                try:
                    sys.stderr.write(
                        f"[datalens] logging queue full; dropped {self._dropped} record(s)\n"
                    )
                except Exception:
                    # Nothing else we can do without risking recursion.
                    return


@dataclass(frozen=True)
class LoggingSystem:
    """Handle for the configured logging pipeline."""

    log_dir: Path
    log_path: Path | None
    queue_handler: DroppingQueueHandler
    listener: logging.handlers.QueueListener
    handlers: tuple[logging.Handler, ...]


_SYSTEM: LoggingSystem | None = None
_SYSTEM_LOCK = threading.Lock()


def init_logging(
    *,
    app_name: str = "datalens",
    log_dir: Path | None = None,
    log_to_file: bool = True,
    level: int = logging.DEBUG,
    console_level: int = logging.INFO,
    max_bytes: int = 5_000_000,
    backup_count: int = 5,
    queue_size: int = 10_000,
) -> LoggingSystem:
    """
    Initialise the DataLens logging pipeline.

    Safe to call multiple times (idempotent).
    """

    global _SYSTEM
    with _SYSTEM_LOCK:
        if _SYSTEM is not None:
            return _SYSTEM

        resolved_log_dir = Path(log_dir) if log_dir is not None else (datalens_user_data_dir(app_name=app_name) / "logs")
        if log_to_file:
            resolved_log_dir.mkdir(parents=True, exist_ok=True)
            log_path: Path | None = resolved_log_dir / f"{app_name}.log"
        else:
            log_path = None

        # Handlers used by the QueueListener thread.
        formatter = CompactFormatter()

        handlers: list[logging.Handler] = []

        if log_path is not None:
            # File handler (best-effort): if it fails, we still keep stderr logging.
            try:
                file_handler = logging.handlers.RotatingFileHandler(
                    log_path,
                    maxBytes=int(max_bytes),
                    backupCount=int(backup_count),
                    encoding="utf-8",
                    delay=True,
                )
                file_handler.setLevel(level)
                file_handler.setFormatter(formatter)
                handlers.append(file_handler)
            except Exception:
                log_path = None

        stderr_handler = logging.StreamHandler(stream=sys.stderr)
        stderr_handler.setLevel(console_level)
        stderr_handler.setFormatter(formatter)
        handlers.append(stderr_handler)

        log_queue: "queue.Queue[logging.LogRecord]" = queue.Queue(maxsize=int(queue_size))
        queue_handler = DroppingQueueHandler(log_queue)
        queue_handler.setLevel(level)

        listener = logging.handlers.QueueListener(log_queue, *handlers, respect_handler_level=True)
        listener.start()

        datalens_logger = logging.getLogger("datalens")
        datalens_logger.setLevel(level)
        datalens_logger.propagate = False
        datalens_logger.addHandler(queue_handler)

        system = LoggingSystem(
            log_dir=resolved_log_dir,
            log_path=log_path,
            queue_handler=queue_handler,
            listener=listener,
            handlers=tuple(handlers),
        )
        _SYSTEM = system

        # Ensure the listener stops and flushes at exit.
        atexit.register(shutdown_logging)

        datalens_logger.debug("Logging initialised", extra={"operation": "init_logging", "phase": "end"})
        if log_path is None:
            datalens_logger.warning(
                "File logging disabled; using stderr only",
                extra={"operation": "init_logging", "phase": "warning"},
            )

        return system


def shutdown_logging() -> None:
    """Stop the QueueListener and detach handlers (best-effort)."""

    global _SYSTEM
    with _SYSTEM_LOCK:
        system = _SYSTEM
        _SYSTEM = None
    if system is None:
        return
    try:
        system.listener.stop()
    except Exception:
        pass

    try:
        datalens_logger = logging.getLogger("datalens")
        if system.queue_handler in datalens_logger.handlers:
            datalens_logger.removeHandler(system.queue_handler)
    except Exception:
        pass

    for handler in system.handlers:
        try:
            handler.close()
        except Exception:
            continue


def get_logger(name: str | None = None, **bind: Any) -> logging.LoggerAdapter:
    """
    Return a LoggerAdapter with optional bound attributes.

    Prefer calling this with `__name__` so layer/subsystem inference works.
    """
    logger = logging.getLogger(name or "datalens")
    return DatalensLoggerAdapter(logger, dict(bind))


class DatalensLoggerAdapter(logging.LoggerAdapter):
    """
    LoggerAdapter that merges call-site ``extra`` with bound fields.

    Python's stdlib LoggerAdapter overwrites ``kwargs['extra']`` instead of
    merging, which would discard per-call attribution (operation/phase/plugin).
    """

    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:  # type: ignore[override]
        call_extra = kwargs.get("extra")
        merged: dict[str, Any] = dict(self.extra or {})
        if isinstance(call_extra, dict):
            merged.update(call_extra)
        kwargs["extra"] = merged
        return msg, kwargs

    def progress(self, msg: Any, *args: Any, value: float | None = None, **kwargs: Any) -> None:
        """
        Log a user-facing progress message.

        Equivalent to:
        - ``log.info(msg, extra={'progress': True})``

        When a loader dialog is active, this message is also forwarded to the
        dialog (best-effort) while still being logged normally.
        """
        extra = kwargs.get("extra")
        if not isinstance(extra, dict):
            extra = {}
        if "progress" not in extra and "ui_progress" not in extra:
            extra["progress"] = True
        if value is not None and "progress_value" not in extra:
            try:
                v = float(value)
            except Exception:
                v = None
            if v is not None:
                if v < 0.0:
                    v = 0.0
                if v > 1.0:
                    v = 1.0
                extra["progress_value"] = v
        kwargs["extra"] = extra
        self.info(msg, *args, **kwargs)


def current_log_context() -> dict[str, Any]:
    """
    Return the currently bound logging context (contextvars snapshot).

    Useful for diagnostics and tests that need to verify context propagation
    across threads/executors.
    """
    ctx = _LOG_CONTEXT.get() or {}
    return dict(ctx)


@contextmanager
def bind_log_context(**fields: Any) -> Iterator[None]:
    """
    Temporarily bind logging context fields using contextvars.

    Values are merged with any existing context for the current execution flow.
    """
    current = _LOG_CONTEXT.get() or {}
    merged = dict(current)
    for key, value in fields.items():
        if value is None:
            continue
        merged[key] = value
    token = _LOG_CONTEXT.set(merged)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)


@contextmanager
def bind_loader_dialog_sink(
    sink: Callable[[str, float | None], None] | None,
    *,
    policy: LoaderDialogSinkPolicy | None = None,
) -> Iterator[None]:
    """
    Bind a loader dialog sink for the current execution context.

    When bound, logs may be mirrored into the active loader dialog depending on
    `policy`.

    - Progress logs (``extra={'progress': True}`` or ``log.progress(...)``) are
      mirrored when ``policy.show_log_progress`` is True.
    - Non-progress logs can optionally be mirrored by severity (INFO/WARNING/
      ERROR/CRITICAL).

    Notes:

    - This is a UX channel, not a security boundary.
    - The sink must be thread-safe and must not touch Qt widgets directly.
      The loader runner provides a sink that routes to the UI thread.
    """
    pol = policy or LoaderDialogSinkPolicy()
    token = _LOADER_DIALOG_SINK.set(None if not callable(sink) else (sink, pol))
    try:
        yield
    finally:
        _LOADER_DIALOG_SINK.reset(token)


@contextmanager
def bind_loader_progress_sink(sink: Callable[[str], None] | None) -> Iterator[None]:
    """
    Backwards-compatible helper: bind a message-only progress sink.

    Only logs marked with ``extra={'progress': True}`` are mirrored.
    """
    if not callable(sink):
        with bind_loader_dialog_sink(None):
            yield
        return

    def wrapped(message: str, value: float | None) -> None:
        sink(message)

    with bind_loader_dialog_sink(wrapped, policy=LoaderDialogSinkPolicy(show_log_progress=True)):
        yield


def in_loader_progress() -> bool:
    """True if a loader progress sink is currently bound."""
    sink_tuple = _LOADER_DIALOG_SINK.get()
    return bool(sink_tuple and callable(sink_tuple[0]))


@contextmanager
def log_operation(
    *,
    subsystem: str,
    operation: str,
    logger: logging.LoggerAdapter | None = None,
    level: int = logging.INFO,
    op_id: str | None = None,
    **fields: Any,
) -> Iterator[str]:
    """
    Log a start/end/error pair for an operation and expose a correlation id.

    The correlation id (`op_id`) is available to nested logs and propagates to
    shared executors if they capture the context at submission time.
    """

    log = logger or get_logger(__name__)
    correlation = op_id or uuid4().hex[:10]
    start = time.monotonic()

    with bind_log_context(subsystem=subsystem, operation=operation, op_id=correlation, **fields):
        log.log(level, f"{operation} started", extra={"phase": "start"})
        try:
            yield correlation
        except Exception:
            log.exception(f"{operation} failed", extra={"phase": "error"})
            raise
        else:
            elapsed_ms = (time.monotonic() - start) * 1000.0
            log.log(level, f"{operation} finished ({elapsed_ms:.1f} ms)", extra={"phase": "end"})
