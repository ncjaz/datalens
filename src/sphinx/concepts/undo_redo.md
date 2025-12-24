# Undo/Redo

This page describes the **whole-app undo/redo model** for DataLens V2 and how UI actions, tools, and dialogs feed into it.

## What Qt already provides

Before adding custom infrastructure, we reuse Qt for Python (PySide6/PyQt) primitives:

- `QUndoStack` + `QUndoCommand` for the undo framework (push/undo/redo, merge, macros).
- `QUndoGroup` to route a single Undo/Redo menu/toolbar pair to the active workspace’s stack.
- `QKeySequence.StandardKey` for OS-correct default shortcuts.
- `createUndoAction()` / `createRedoAction()` for actions whose enabled state + text track stack state automatically.

## Whole-app default (recommended)

The default is **per-workspace stacks** with **global routing**:

- Each workspace owns a `QUndoStack` representing edits to its active “document”.
- The main window owns a `QUndoGroup` and switches its active stack when the active workspace changes.

This prevents mixing unrelated histories (annotation edits vs capture controls vs model browsing) while keeping one consistent set of Undo/Redo actions.

### Routing diagram

```
          (tools)           (buttons/menus)           (dialogs)
      host.apply_mutation     canvas.commands.*    canvas.commands.* / apply_mutation
              |                    |                      |
              +----------+---------+----------------------+
                         |
                    QUndoStack.push(command)
                         |
             +-----------+------------+
             |                        |
         Ctrl+Z/Ctrl+Y            Undo/Redo QAction
      (ShortcutRegistry)       (QUndoGroup create*Action)
             |                        |
             +-----------+------------+
                         |
                 active stack (workspace)
```

## How an edit becomes undoable

The system is intentionally explicit: **undoable changes must flow through `apply_mutation()`** (directly, or via the command builder).

### Tool example (already “automatic”)

```python
host.apply_mutation(
    UpdateVerticesMutation(shape_id=sid, vertex_updates={idx: pos}),
    description="Move vertex",
    merge_id=f"drag_{sid}_{idx}",
)
```

### UI button/menu example (command builder)

```python
canvas.commands.delete_shapes(selected_ids)
```

### Multi-step operation example (macro grouping)

```python
with canvas.undo_group("Delete shape with annotations") as cmd:
    cmd.delete_shapes([shape_id])
    cmd.delete_shapes(annotation_ids)
```

## Coalescing interactive edits

Interactive gestures can emit many updates (dragging, painting). Use Qt merge support:

- The tool provides a stable `merge_id` for the gesture.
- The `QUndoCommand` implements `id()`/`mergeWith()` to coalesce consecutive commands.

Result: “one drag = one undo step”.

## Modal dialogs and preferences

“Active workspace” is a routing decision, not “whatever widget has focus”.

- Dialogs that edit the **current document** (properties, “apply change” dialogs) should call workspace APIs (`canvas.commands.*` / `apply_mutation()`), so undo works normally.
- Preferences / keyboard shortcut configuration is **application configuration** and should not write to the document undo stack. Prefer Apply/OK/Cancel semantics and “Reset to defaults”.

While a configuration modal is open, undo/redo shortcuts should generally no-op (or be left to text widgets within the dialog).

Implementation note: DataLens routes Ctrl+Z/Ctrl+Y through the shortcuts system (not QAction shortcuts), registered with `allow_in_text_inputs=False`, and only dispatches document undo/redo when the main window is the active window.

## DataLens V1 note (for comparison)

V1’s annotation workspace uses **snapshot stacks** (per-image undo/redo of `list[AnnotationBoxRecord]`). This is simple and works well for a bounded model, but it’s not a great whole-app default because snapshots get expensive and don’t compose well with side effects.

In V2 we keep the *framework* consistent (`QUndoCommand` + `QUndoStack`) and only use snapshots as a bounded fallback when a subsystem is still blob-state.
