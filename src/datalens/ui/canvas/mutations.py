from __future__ import annotations

import zlib
from typing import Protocol

from PySide6.QtGui import QUndoCommand

from datalens.api.tools import ToolMutation
from datalens.core.logging import get_logger

log = get_logger(__name__)

_UNSET = object()


class ToolMutationHandler(Protocol):
    def capture_undo_payload(self, mutation: ToolMutation) -> object | None:
        ...

    def apply_mutation(self, mutation: ToolMutation) -> bool:
        ...

    def undo_mutation(self, mutation: ToolMutation, undo_payload: object | None) -> bool:
        ...


class ToolMutationCommand(QUndoCommand):
    def __init__(
        self,
        *,
        mutation: ToolMutation,
        handler: ToolMutationHandler,
        description: str,
        merge_id: str | None = None,
        undo_payload: object = _UNSET,
        already_applied: bool = False,
    ) -> None:
        super().__init__(str(description))
        self._handler = handler
        self._mutation = mutation
        self._merge_id = str(merge_id) if merge_id is not None else None
        self._merge_key = self._compute_merge_key(self._merge_id)
        self._already_applied = bool(already_applied)
        self._first_redo = True

        if undo_payload is _UNSET:
            try:
                self._undo_payload = handler.capture_undo_payload(mutation)
            except Exception:
                log.debug(
                    "Tool mutation undo capture failed (best-effort)",
                    exc_info=True,
                    extra={"operation": "tools", "phase": "mutation_capture_error"},
                )
                self._undo_payload = None
        else:
            self._undo_payload = undo_payload

    def _compute_merge_key(self, merge_id: str | None) -> int:
        if not merge_id:
            return -1
        try:
            return int(zlib.crc32(merge_id.encode("utf-8")) & 0x7FFFFFFF)
        except Exception:
            return -1

    def redo(self) -> None:
        if self._already_applied and self._first_redo:
            self._first_redo = False
            return
        self._first_redo = False
        try:
            ok = bool(self._handler.apply_mutation(self._mutation))
        except Exception:
            log.warning(
                "Tool mutation redo failed",
                exc_info=True,
                extra={"operation": "undo", "phase": "mutation_redo_error"},
            )
            return
        if not ok:
            log.warning(
                "Tool mutation redo rejected",
                extra={"operation": "undo", "phase": "mutation_redo_rejected"},
            )

    def undo(self) -> None:
        try:
            ok = bool(self._handler.undo_mutation(self._mutation, self._undo_payload))
        except Exception:
            log.warning(
                "Tool mutation undo failed",
                exc_info=True,
                extra={"operation": "undo", "phase": "mutation_undo_error"},
            )
            return
        if not ok:
            log.warning(
                "Tool mutation undo rejected",
                extra={"operation": "undo", "phase": "mutation_undo_rejected"},
            )

    def id(self) -> int:
        return self._merge_key

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, ToolMutationCommand):
            return False
        if self._merge_id is None or other._merge_id is None:
            return False
        if self._merge_id != other._merge_id:
            return False
        self._mutation = other._mutation
        if other.text():
            self.setText(other.text())
        return True


__all__ = ["ToolMutationCommand", "ToolMutationHandler"]
