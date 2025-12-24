# Undo/Redo API (contract)

This page is the **API contract** for the V2 undo/redo system. It documents the intended public surface; implementation details may evolve, but callers should remain stable.

## Qt types we build on

- `QUndoStack` (per workspace)
- `QUndoCommand` (one undoable step)
- `QUndoGroup` (main-window routing to the active stack)

## Required workspace surface

Each workspace that supports undo must expose a `QUndoStack` (directly, or via a lightweight controller):

```python
class Workspace(Protocol):
    @property
    def undo_stack(self) -> QUndoStack: ...
```

The main window sets the active stack on workspace focus changes:

```python
undo_group.setActiveStack(workspace.undo_stack)
```

Note: DataLens routes chords via the shortcuts system, so undo/redo `QAction` instances created from `createUndoAction()` / `createRedoAction()` should not set Qt-native shortcuts (avoid double-fire).

## Tool/Canvas integration surface

### `apply_mutation()` (lowest-level)

All undoable domain edits flow through `apply_mutation()`:

```python
class ToolHost(Protocol):
    def apply_mutation(
        self,
        mutation: ToolMutation,
        *,
        description: str,
        merge_id: str | None = None,
    ) -> bool: ...
```

Semantics:

- Creates a `QUndoCommand` that can `redo()` and `undo()` the change.
- Pushes to the workspace `QUndoStack` (redo truncation is automatic).
- If `merge_id` is supplied, enables coalescing with `QUndoCommand.mergeWith()`.

### `commands` (recommended for UI code)

UI handlers (buttons, menus, dialog Apply) should prefer a fluent command builder that wraps common mutations and standardizes undo labels:

```python
class CanvasHost(Protocol):
    @property
    def commands(self) -> CommandBuilder: ...
```

Typical methods (examples):

```python
class CommandBuilder:
    def add_shape(self, shape_type: str, points: list[QPointF], **attributes) -> bool: ...
    def delete_shapes(self, shape_ids: list[str]) -> bool: ...
    def update_vertices(self, shape_id: str, vertex_updates: dict[int, QPointF], *, merge_id: str | None = None) -> bool: ...
    def set_attribute(self, shape_ids: list[str], attribute_name: str, value: Any) -> bool: ...
```

### `undo_group()` (macro grouping)

For multi-step operations, provide a context manager that wraps `beginMacro()` / `endMacro()`:

```python
@contextmanager
def undo_group(self, description: str) -> Iterator[CommandBuilder]:
    ...
```

## Preferences and settings

- **Document/workspace-scoped settings** may be modeled as undoable commands (commit boundaries; avoid per-keystroke).
- **Application configuration** (e.g., shortcut rebinding) must not go into the document undo stack; use Apply/Cancel/Reset UX.

Qt helpers to reuse:
- `QKeySequenceEdit` for shortcut capture in preferences.
- `QSettings` for non-document UI state (window geometry/state).
