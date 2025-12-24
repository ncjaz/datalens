from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence, QUndoGroup, QUndoStack
from PySide6.QtWidgets import QWidget

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId


log = get_logger(__name__)


class UndoRedoController:
    """
    Main-window undo/redo routing for per-workspace undo stacks.

    Qt provides `QUndoGroup` specifically for this problem: keep a single pair of
    undo/redo actions (menu/toolbar/shortcuts) and route them to whichever
    `QUndoStack` is currently active.

    This controller deliberately does *not* set QAction shortcuts. DataLens V2
    treats the shortcuts system as the single source of truth for chords so user
    overrides don't double-fire alongside Qt-native QAction shortcuts.
    """

    def __init__(self, parent: QWidget) -> None:
        self._group = QUndoGroup(parent)
        self._known_stack_ids: set[int] = set()
        self._active_plugin_id: PluginId | None = None
        self._active_workspace_widget_type: str | None = None

        self._tracking_stack: QUndoStack | None = None
        self._use_stack_index_signal = False
        self._last_index: int | None = None
        self._last_undo_text: str = ""
        self._last_redo_text: str = ""
        self._ignore_next_index_change = False

        self.undo_action: QAction = self._group.createUndoAction(parent, "Undo")
        self.redo_action: QAction = self._group.createRedoAction(parent, "Redo")

        self._strip_action_shortcuts(self.undo_action)
        self._strip_action_shortcuts(self.redo_action)

        self.undo_action.setObjectName("Datalens:UndoAction")
        self.redo_action.setObjectName("Datalens:RedoAction")

        self._connect_group_signals()

        log.info("Undo/redo controller initialized", extra={"operation": "undo", "phase": "init"})

    @property
    def group(self) -> QUndoGroup:
        return self._group

    @property
    def active_plugin_id(self) -> PluginId | None:
        return self._active_plugin_id

    def set_active_workspace_widget(self, plugin_id: PluginId | None, widget: QWidget | None) -> None:
        """
        Set the active undo stack by inspecting the workspace widget.

        Workspaces that support undo should expose `undo_stack: QUndoStack`.
        """
        stack: QUndoStack | None = None
        widget_type: str | None = None
        if widget is not None:
            widget_type = type(widget).__name__
            stack = getattr(widget, "undo_stack", None)
            if stack is not None and not isinstance(stack, QUndoStack):
                log.warning(
                    "Workspace undo_stack is not a QUndoStack; disabling undo for this workspace",
                    extra={
                        "operation": "undo",
                        "phase": "invalid_stack",
                        "plugin_id": str(plugin_id) if plugin_id is not None else "",
                        "widget_type": type(widget).__name__,
                        "stack_type": type(stack).__name__,
                    },
                )
                stack = None

        self._active_workspace_widget_type = widget_type
        self.set_active_stack(plugin_id=plugin_id, stack=stack)

    def set_active_stack(self, *, plugin_id: PluginId | None, stack: QUndoStack | None) -> None:
        """Set the active undo stack for the main window."""
        if stack is not None:
            self._ensure_stack_registered(stack)
        # Reset state early so any immediate indexChanged emissions during
        # setActiveStack() aren't misclassified as undo/redo operations.
        self._set_tracking_stack(stack)
        try:
            self._group.setActiveStack(stack)
        except Exception:
            log.warning(
                "Failed to set active undo stack (best-effort)",
                exc_info=True,
                extra={
                    "operation": "undo",
                    "phase": "set_active_stack_error",
                    "plugin_id": str(plugin_id) if plugin_id is not None else "",
                },
            )
            try:
                self._group.setActiveStack(None)
            except Exception:
                pass
            stack = None

        self._set_tracking_stack(stack)
        self._active_plugin_id = plugin_id
        log.info(
            "Active undo stack changed",
            extra={
                "operation": "undo",
                "phase": "active_stack_changed",
                "plugin_id": str(plugin_id) if plugin_id is not None else "",
                "workspace_widget": self._active_workspace_widget_type or "",
                "enabled": bool(stack is not None),
            },
        )

    def undo(self) -> None:
        """Invoke undo on the active stack (if any)."""
        try:
            self._group.undo()
        except Exception:
            log.debug("Undo failed (best-effort)", exc_info=True, extra={"operation": "undo", "phase": "undo_error"})

    def redo(self) -> None:
        """Invoke redo on the active stack (if any)."""
        try:
            self._group.redo()
        except Exception:
            log.debug("Redo failed (best-effort)", exc_info=True, extra={"operation": "undo", "phase": "redo_error"})

    # ------------------------------------------------------------------
    # Logging + tracking
    # ------------------------------------------------------------------

    def _connect_group_signals(self) -> None:
        """
        Best-effort: wire up Qt undo signals for logging.

        Prefer Qt built-ins (`QUndoGroup`/`QUndoStack` signals) over custom plumbing.
        """
        try:
            self._group.activeStackChanged.connect(self._on_active_stack_changed)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self._group.indexChanged.connect(self._on_index_changed)  # type: ignore[attr-defined]
            self._use_stack_index_signal = False
        except Exception:
            # Fallback: connect to the active `QUndoStack.indexChanged`.
            self._use_stack_index_signal = True

    def _ensure_stack_registered(self, stack: QUndoStack) -> None:
        stack_id = int(id(stack))
        if stack_id in self._known_stack_ids:
            return
        try:
            self._group.addStack(stack)
            self._known_stack_ids.add(stack_id)
        except Exception:
            # Some Qt bindings implicitly register stacks via setActiveStack.
            # Best-effort: still track it to avoid spamming addStack calls.
            self._known_stack_ids.add(stack_id)

    def _on_active_stack_changed(self, stack: QUndoStack | None) -> None:
        self._set_tracking_stack(stack)

    def _set_tracking_stack(self, stack: QUndoStack | None) -> None:
        if self._use_stack_index_signal and self._tracking_stack is not None:
            try:
                self._tracking_stack.indexChanged.disconnect(self._on_index_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
        self._tracking_stack = stack
        if stack is None:
            self._last_index = None
            self._last_undo_text = ""
            self._last_redo_text = ""
            self._ignore_next_index_change = False
            return

        if self._use_stack_index_signal:
            try:
                stack.indexChanged.connect(self._on_index_changed)  # type: ignore[attr-defined]
            except Exception:
                pass

        self._last_index = self._safe_stack_index(stack)
        self._last_undo_text = self._safe_stack_undo_text(stack)
        self._last_redo_text = self._safe_stack_redo_text(stack)
        # The first indexChanged after switching stacks is bookkeeping; avoid
        # misclassifying it as an undo/redo event.
        self._ignore_next_index_change = True

    def _on_index_changed(self, index: int) -> None:
        if self._ignore_next_index_change:
            self._ignore_next_index_change = False
            self._last_index = int(index)
            return

        stack = self._tracking_stack
        if stack is None:
            return

        prev_index = self._last_index
        prev_undo = self._last_undo_text
        prev_redo = self._last_redo_text

        new_index = int(index)
        self._last_index = new_index

        new_undo = self._safe_stack_undo_text(stack)
        new_redo = self._safe_stack_redo_text(stack)
        self._last_undo_text = new_undo
        self._last_redo_text = new_redo

        if prev_index is None:
            return

        delta = new_index - int(prev_index)
        if delta == 0:
            return

        if delta < 0:
            # After an undo, the undone command becomes the next redo item.
            undone = new_redo or prev_undo
            cmd_meta = self._command_meta(stack, command_index=new_index)
            log.info(
                "Undo applied",
                extra={
                    "operation": "undo",
                    "phase": "undo_applied",
                    "plugin_id": str(self._active_plugin_id) if self._active_plugin_id is not None else "",
                    "workspace_widget": self._active_workspace_widget_type or "",
                    "command": str(undone),
                    "steps": abs(int(delta)),
                    **cmd_meta,
                },
            )
            return

        if delta > 0:
            # Classify redo vs push best-effort:
            # - after redo, undoText usually equals the command that was redone.
            redone = new_undo if (prev_redo and new_undo == prev_redo) else ""
            if redone:
                cmd_meta = self._command_meta(stack, command_index=max(0, new_index - 1))
                log.info(
                    "Redo applied",
                    extra={
                        "operation": "undo",
                        "phase": "redo_applied",
                        "plugin_id": str(self._active_plugin_id) if self._active_plugin_id is not None else "",
                        "workspace_widget": self._active_workspace_widget_type or "",
                        "command": str(redone),
                        "steps": abs(int(delta)),
                        **cmd_meta,
                    },
                )

    @staticmethod
    def _safe_stack_index(stack: QUndoStack) -> int:
        try:
            return int(stack.index())
        except Exception:
            return 0

    @staticmethod
    def _safe_stack_undo_text(stack: QUndoStack) -> str:
        try:
            return str(stack.undoText() or "")
        except Exception:
            return ""

    @staticmethod
    def _safe_stack_redo_text(stack: QUndoStack) -> str:
        try:
            return str(stack.redoText() or "")
        except Exception:
            return ""

    @classmethod
    def _command_meta(cls, stack: QUndoStack, *, command_index: int) -> dict[str, object]:
        """
        Best-effort: extract structured metadata from the command at `command_index`.

        This avoids requiring every command type to implement a formal interface
        while still providing richer logs for DataLens-owned commands.
        """
        cmd = cls._safe_stack_command(stack, command_index)
        if cmd is None:
            return {}

        meta: dict[str, object] = {}
        try:
            meta["command_type"] = type(cmd).__name__
        except Exception:
            pass

        raw_undo_meta = getattr(cmd, "_undo_meta", None)
        if isinstance(raw_undo_meta, dict):
            for k, v in raw_undo_meta.items():
                try:
                    key = str(k)
                except Exception:
                    continue
                if not key:
                    continue
                if v is None:
                    continue
                try:
                    meta[key] = v if isinstance(v, (int, float, bool)) else str(v)
                except Exception:
                    continue

        edit = getattr(cmd, "_edit", None)
        if edit is not None:
            for field, key in (
                ("kind", "edit_kind"),
                ("layer_id", "edit_layer_id"),
                ("shape_id", "edit_shape_id"),
                ("vertex_index", "edit_vertex_index"),
            ):
                try:
                    value = getattr(edit, field)
                except Exception:
                    continue
                if value is None:
                    continue
                try:
                    meta[key] = str(value)
                except Exception:
                    continue

        return meta

    @staticmethod
    def _safe_stack_command(stack: QUndoStack, index: int) -> object | None:
        try:
            count = int(stack.count())
        except Exception:
            count = -1
        if count >= 0 and not (0 <= int(index) < count):
            return None
        try:
            return stack.command(int(index))
        except Exception:
            return None

    @staticmethod
    def _strip_action_shortcuts(action: QAction) -> None:
        """
        Remove any Qt-native shortcuts from an undo/redo action.

        `createUndoAction()` / `createRedoAction()` may set platform defaults
        (`Ctrl+Z`, `Ctrl+Y`, etc.). DataLens routes chords through the shortcuts
        system so user overrides remain authoritative and we don't double-fire.
        """
        try:
            action.setShortcut(QKeySequence())
        except Exception:
            pass
        try:
            action.setShortcuts([])
        except Exception:
            pass


__all__ = ["UndoRedoController"]
