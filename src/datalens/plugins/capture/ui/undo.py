from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Callable

from PySide6.QtGui import QUndoCommand

from datalens.core.logging import get_logger


log = get_logger(__name__)


@dataclass(frozen=True)
class CaptureUndoMeta:
    setting_key: str
    device_id: str | None = None
    device_kind: str | None = None


class CaptureSettingUndoCommand(QUndoCommand):
    """
    Generic undo command for Capture workspace settings.

    Designed for UI settings that must:
    - update the UI state
    - apply to the capture service (best-effort)
    - persist via PluginPreferencesService so undo/redo also persists
    """

    def __init__(
        self,
        description: str,
        *,
        apply_value: Callable[[object], None],
        old_value: object,
        new_value: object,
        merge_key: str | None = None,
        meta: CaptureUndoMeta | None = None,
    ) -> None:
        super().__init__(str(description))
        self._apply_value = apply_value
        self._old_value = old_value
        self._new_value = new_value
        self._merge_key = str(merge_key) if merge_key else None
        self._undo_meta: dict[str, object] = {}
        if meta is not None:
            self._undo_meta.update(
                {
                    "setting_key": str(meta.setting_key),
                    "device_id": str(meta.device_id) if meta.device_id is not None else "",
                    "device_kind": str(meta.device_kind) if meta.device_kind is not None else "",
                }
            )

    def id(self) -> int:  # noqa: D401 - Qt API name
        """Return a stable id for QUndoStack merge support."""
        if not self._merge_key:
            return -1
        return int(zlib.crc32(self._merge_key.encode("utf-8")) & 0x7FFFFFFF)

    def mergeWith(self, other: object) -> bool:  # noqa: N802 - Qt API name
        if not isinstance(other, CaptureSettingUndoCommand):
            return False
        if not self._merge_key or self._merge_key != other._merge_key:
            return False
        self._new_value = other._new_value
        return True

    def undo(self) -> None:
        self._safe_apply(self._old_value)

    def redo(self) -> None:
        self._safe_apply(self._new_value)

    def _safe_apply(self, value: object) -> None:
        try:
            self._apply_value(value)
        except Exception:
            log.debug(
                "Capture setting undo apply failed (best-effort)",
                exc_info=True,
                extra={"operation": "undo", "phase": "capture_apply_failed", **dict(self._undo_meta)},
            )


__all__ = ["CaptureSettingUndoCommand", "CaptureUndoMeta"]

