from __future__ import annotations

import contextvars
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Any

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId

log = get_logger(__name__)

CommandId = str


@dataclass(frozen=True)
class CommandContext:
    """
    Context passed to command handlers.

    Commands are intended for plugin-to-plugin coordination without imports:
    - producer issues `dispatch("capability.command", payload, ...)`
    - handler returns a result (synchronously) on the command executor thread
    - caller receives a Future

    Keep handlers fast; for long work, handlers should enqueue work onto other
    background systems (DB/IoWriter/loader) and return quickly.
    """

    command_id: CommandId
    payload: object
    caller_plugin_id: PluginId | None
    dispatched_at_s: float


CommandHandler = Callable[[CommandContext], object]


@dataclass(frozen=True)
class RegisteredHandler:
    command_id: CommandId
    handler: CommandHandler
    owner_plugin_id: PluginId | None = None
    description: str = ""


class CommandBus:
    """
    In-process command bus for request/response style coordination.

    Design intent:
    - A convenience mechanism (not a security boundary).
    - Calls are executed off the UI thread by default (ThreadPoolExecutor).
    - Plugin disable/unload can remove its handlers (`unregister_owner`).
    """

    def __init__(self, *, max_workers: int = 4) -> None:
        self._lock = Lock()
        self._handlers: dict[str, RegisteredHandler] = {}
        self._executor: ThreadPoolExecutor | None = None
        self._max_workers = max(1, int(max_workers))

    def register(self, handler: RegisteredHandler, *, replace: bool = False) -> None:
        cid = str(handler.command_id).strip()
        if not cid:
            raise ValueError("command_id must be a non-empty string")
        if not callable(handler.handler):
            raise TypeError("handler must be callable")

        with self._lock:
            if not replace and cid in self._handlers:
                existing = self._handlers[cid]
                raise ValueError(
                    f"Command already registered: {cid!r} (owner={existing.owner_plugin_id})"
                )
            self._handlers[cid] = handler

        log.debug(
            "Command registered",
            extra={
                "operation": "commands",
                "phase": "register",
                "command_id": cid,
                "owner_plugin_id": str(handler.owner_plugin_id) if handler.owner_plugin_id else None,
            },
        )

    def unregister(self, command_id: CommandId) -> None:
        cid = str(command_id).strip()
        with self._lock:
            self._handlers.pop(cid, None)

    def unregister_owner(self, owner_plugin_id: PluginId) -> None:
        owner = PluginId(str(owner_plugin_id))
        with self._lock:
            for cid, rh in list(self._handlers.items()):
                if rh.owner_plugin_id == owner:
                    self._handlers.pop(cid, None)

        log.debug(
            "Commands removed for plugin",
            extra={"operation": "commands", "phase": "unregister_owner", "owner_plugin_id": str(owner)},
        )

    def dispatch(
        self,
        command_id: CommandId,
        payload: object,
        *,
        caller_plugin_id: PluginId | None = None,
    ) -> Future[object]:
        """
        Dispatch a command and return a Future for the handler result.

        Safe to call from the UI thread (the handler is executed in a threadpool).
        """
        cid = str(command_id).strip()
        if not cid:
            raise ValueError("command_id must be a non-empty string")

        with self._lock:
            handler = self._handlers.get(cid)
            if handler is None:
                raise KeyError(f"No command handler registered for {cid!r}")
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="datalens-cmd")
            executor = self._executor

        ctx = CommandContext(
            command_id=cid,
            payload=payload,
            caller_plugin_id=caller_plugin_id,
            dispatched_at_s=time.time(),
        )
        captured = contextvars.copy_context()

        def run() -> object:
            return captured.run(handler.handler, ctx)

        future: Future[object] = executor.submit(run)  # type: ignore[assignment]
        return future

    def snapshot(self) -> list[dict[str, Any]]:
        """Return a JSON-serializable snapshot for debugging/inspection UIs."""
        with self._lock:
            out: list[dict[str, Any]] = []
            for cid, h in sorted(self._handlers.items(), key=lambda kv: kv[0]):
                out.append(
                    {
                        "command_id": cid,
                        "owner_plugin_id": str(h.owner_plugin_id) if h.owner_plugin_id else None,
                        "description": str(h.description or ""),
                        "handler": getattr(h.handler, "__qualname__", repr(h.handler)),
                    }
                )
            return out

    def shutdown(self, *, wait: bool = False) -> None:
        """Best-effort shutdown for the internal threadpool."""
        with self._lock:
            executor = self._executor
            self._executor = None
        if executor is None:
            return
        try:
            executor.shutdown(wait=bool(wait), cancel_futures=True)
        except Exception:
            log.debug("CommandBus shutdown failed (best-effort)", exc_info=True)


__all__ = ["CommandBus", "CommandContext", "CommandHandler", "CommandId", "RegisteredHandler"]

