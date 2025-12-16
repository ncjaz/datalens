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
- Plugin lifecycle: `datalens/services/plugins/host.py`
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
from typing import Any, Iterator
from uuid import uuid4

from datalens.infra.paths import datalens_user_data_dir


_LOG_CONTEXT: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "datalens_log_context",
    default={},
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
    return logging.LoggerAdapter(logger, dict(bind))


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
