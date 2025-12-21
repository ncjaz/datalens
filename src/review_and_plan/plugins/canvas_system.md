# Image + Overlay Canvas System (V2) — Plan

Status: **Planned**

## Objective

Provide a reusable, plugin-friendly **image canvas** widget system that matches the proven V1 approach:

- Display an image (pixmap / frame).
- Render one or more overlay layers above the image (shapes, markers, selection, notes).
- Handle interaction (mouse/key) without blocking the UI.

This system should be usable by:

- Annotation plugin (polygons/boxes/masks + editing).
- Capture plugin (live preview + “notes/highlight” layer without full annotation persistence).
- Review/MEval (read-only overlay rendering).

## Why this system exists (and why not QGraphicsView by default)

V1 used:

- `QScrollArea`
- `QLabel` for the pixmap
- `QStackedLayout(StackAll)` stacking an interactive overlay `QWidget` on top

This pattern is:

- deterministic for input routing (overlay owns events)
- easy to optimize
- low risk for UI/Qt “weirdness”

`QGraphicsView` remains an option for future gallery/timeline use-cases, but the default canvas should be V1-style.

## Desired capabilities (MVP → future)

### MVP

- Image display (QPixmap / QImage input).
- One overlay layer (custom paint) with:
  - points/markers
  - lines (solid/dashed)
  - polygons (filled/outlined)
  - bounding boxes (outlined)
  - selection highlighting
- Coordinate transforms:
  - map image normalized coords ↔ widget coordinates
  - map widget coordinates ↔ image pixel coords
- Zoom + pan:
  - zoom in/out
  - pan via scrollbars or mouse-drag
- Non-blocking:
  - never do heavy geometry or I/O inside `paintEvent`

### Future

- Multiple overlay layers (stacked) with z-order:
  - base overlay (annotations)
  - transient overlay (hover/preview)
  - UI overlay (badges/controls)
- Editing features:
  - add/remove vertices by clicking on edges
  - drag vertex handles
  - snapping options (grid/edge)
- Mask overlays:
  - store mask data (RLE/polygon approximation) and render efficiently
- Viewport state persistence (zoom/center) with QSettings

## API design (V2)

Keep the canvas system split into:

1) **Pure domain geometry**
   - use existing domain:
     - `datalens.domain.annotations.boxes.NormalizedBox`
     - `datalens.domain.annotations.polygons.NormalizedPoint`
   - add minimal additional *generic* geometry if needed (optional):
     - `NormalizedPolyline`, `NormalizedRect`, `NormalizedCircle` (only if justified)

2) **Canvas widget + overlay controllers (UI)**
   - `ImageCanvas`: owns pixmap + scroll + coordinate transforms
   - `OverlayLayer` protocol: paint + hit-test + (optional) input hooks
   - `OverlayController`: tool state + selection state (no painting)

3) **Plugin-specific tools**
   - annotation plugin provides `AnnotationOverlayLayer`, `AnnotationToolController`
   - capture plugin provides `NotesOverlayLayer` (simple, transient)

### Coordinate system choice

Use normalized coordinates in domain (0..1):

- makes DB persistence independent of camera resolution
- aligns with the existing domain annotation dataclasses

Canvas converts to pixel/widget space on demand.

## Editing “vertex on edge” requirement (V1 pain point)

We want a reliable UX for:

- click on an edge to insert a new vertex
- select a vertex and delete it

Proposed approach:

- Implement robust hit-testing:
  - vertex hit: within radius `r`
  - edge hit: within distance `d` to segment, plus segment projection bounds
- Editing actions should be explicit:
  - Insert vertex: click edge + modifier (e.g. Alt+Click) or a tool mode
  - Delete vertex: select vertex + Delete key (or right-click menu)

This avoids accidental edits while drawing or panning.

## Persistence model

The canvas system itself does not own persistence.

- Annotation plugin persists to PluginDb tables.
- Capture plugin may choose to persist notes (optional) or keep transient state only.

Canvas should expose “snapshot-able” state if needed:

- viewport state (zoom, center)
- active tool id

Persist UI state via QSettings (UI geometry) and PluginDb/SettingsStore for semantic settings.

## Performance constraints

- Painting must be O(n_visible) with minimal allocations.
- Avoid converting images to pixmaps repeatedly; cache scaled pixmaps by zoom.
- For live video:
  - latest-frame semantics (drop frames if UI lags)
  - avoid per-frame expensive polygon recomputation

## Implementation tasks (ordered)

1) Introduce `ImageCanvas` widget:
   - owns `QScrollArea` integration + pixmap display
   - exposes mapping helpers (normalized ↔ widget coords)
2) Introduce `OverlayLayer` protocol + simple built-in layers:
   - points + polylines + polygons + boxes
3) Add zoom/pan support + viewport state snapshot
4) Add “notes overlay” layer demo in `widget_test` to validate interaction
5) Add editing helpers:
   - vertex hit-testing
   - edge insertion hit-testing
6) Document the system in Sphinx (UI section) with code examples

## Logging + diagnostics (required)

The canvas is an interaction-heavy widget, so it must be debuggable without
turning the app into a wall of logs.

Required logging policy:

- **Info-level** (low volume): major state transitions
  - tool changes (select/box/polygon/mask/etc.)
  - overlay mode changes (enabled/disabled layers)
  - zoom preset changes (fit-to-window, reset zoom)
- **Debug-level** (higher volume, but still controlled):
  - input state transitions (press → drag → release)
  - hit-testing decisions (vertex hit, edge hit, selection changes)
  - vertex insert/delete operations (especially edge insertion)
  - mapping diagnostics (normalized ↔ pixel) when errors occur
- Never log on every mouse-move by default; if needed, gate behind debug flags
  and rate-limit (e.g. “log every Nth move”).

Always log exceptions with traceback when caught best-effort.
