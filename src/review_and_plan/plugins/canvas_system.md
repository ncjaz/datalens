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
# Raster + vector overlay model (updated)

We want a single **Canvas system** that can render and interact with:

- **Raster overlays** (pixel grids): masks, heatmaps, depth colormaps, brush strokes, model outputs.
- **Vector overlays** (geometry): boxes, polygons, vertices/handles, guidelines, labels.

This avoids creating “two canvases” (one for masks, one for geometry). A plugin can mix both: e.g. paint a mask (raster) while also editing polygon vertices (vector) on top.

## Layer stack (draw order)

Render is always “bottom → top”. Higher layers draw on top and typically receive interaction first.

```
 TOP (drawn last)
 ┌────────────────────────────────────────────────────────────┐
 │ HUD / UI overlays (non-canvas UI)                          │
 │  - tool hints, crosshair, selection banner, help text       │
 ├────────────────────────────────────────────────────────────┤
 │ Vector overlays (interactive)                               │
 │  - vertices/handles                                         │
 │  - polygons/boxes/paths                                     │
 │  - labels, guides, snapping indicators                      │
 ├────────────────────────────────────────────────────────────┤
 │ Raster overlays (pixel)                                     │
 │  - paint strokes (editable)                                 │
 │  - masks (editable or model-provided)                       │
 │  - heatmaps, depth colormap, edges (usually read-only)      │
 ├────────────────────────────────────────────────────────────┤
 │ Base image (RGB)                                            │
 │  - current frame / currently selected media                 │
 └────────────────────────────────────────────────────────────┘
 BOTTOM (drawn first)
```

Notes:
- We treat “HUD” as optional; it’s just another overlay layer type that draws last.
- Raster overlays can also have an “opacity/compose mode” (normal/alpha/multiply) so masks don’t obliterate the base image.

## One system manages both layer types

The Canvas owns:

- **Viewport transform** (pan/zoom): converts between widget pixels and image coordinates.
- **LayerManager**: ordered list of layers; draw + hit-test routing.
- **ToolManager**: active tool selection, event routing, capture rules.

Layers are pure render/hit-test objects; tools implement “behavior”.

## Tools, layers, and interaction routing

Tools should be self-contained and plugin-owned (e.g. `capture/tools/*`), but the Canvas provides a stable contract:

### Key ideas

1. **Only one active tool receives pointer events first**.
2. The active tool may:
   - **consume** the event (e.g. painting stroke started),
   - or **defer** to the Canvas selection/router (e.g. no hit, allow vertex selection).
3. The Canvas selection/router can then hit-test vector/raster layers depending on intent.

### Hit-test priority (typical)

When a pointer event arrives (mouse press/move/release), Canvas does:

1) If there is an **active tool**:
- call `tool.on_pointer_event(...)`
- if it returns `consumed=True`, stop (tool “captures” the gesture)

2) Otherwise (or tool returned `consumed=False`), use default hit-test:

- **Vector handles first** (vertices/resize handles) because they’re small and precise
- then **vector shapes** (polygon interior/edges, box interior/edges)
- then **raster hit-test** (only if there is an interactive raster layer, e.g. paint mask)
- else let event bubble (scroll area, parent widgets, etc.)

This ensures: clicking a vertex doesn’t accidentally “paint”, but painting tool can still intentionally capture the pointer when active.

### How painting and vertex editing coexist

Painting tool workflow:
- When painting tool is active and user presses LMB:
  - tool checks if the press is intended for painting (e.g. within image bounds)
  - it **captures** pointer events until release
  - it writes into a raster layer (e.g. `PaintMaskLayer`) and requests redraw

Vertex editing workflow:
- When selection/edit tool is active (or no tool):
  - Canvas hit-tests vertex handles
  - dragging a handle captures pointer events until release
  - geometry layer updates polygon vertices and requests redraw

If you want “modifier behavior” (e.g. hold Shift to temporarily paint while in selection tool):
- The selection tool can delegate based on modifiers:
  - If `Shift` pressed → temporarily route to paint tool for that gesture only
  - Otherwise → do normal selection/vertex editing

This keeps “painting vs vertex drag” under a unified event router without global hacks.

## Suggested minimal interfaces (v0)

We keep these tiny so they’re easy to implement and don’t bloat the core:

### Layers

- `Layer.draw(painter, view)` (required)
- `Layer.hit_test(point_image_xy, view) -> Hit | None` (optional; only for interactive layers)

Where `Hit` includes:
- `layer_id`, `kind` (`"vertex"|"edge"|"shape"|"pixel"`), `payload` (shape id, vertex index, etc.)

### Tools

- `Tool.on_activate(canvas)` / `Tool.on_deactivate(canvas)` (optional)
- `Tool.on_pointer_event(event, view) -> ToolResult(consumed: bool, cursor: Optional[Cursor])`

Tools can create/manage layers:
- `canvas.layers.add(layer, z=...)`
- `canvas.layers.remove(layer_id)`
- `canvas.layers.set_visible(layer_id, bool)`
- `canvas.layers.set_opacity(layer_id, float)`

## Event flow (simplified)

```
QWidget mousePress/Move/Release
  -> CanvasWidget.handle_pointer_event(e)
      -> ToolManager.active_tool?.on_pointer_event(...)
          -> if consumed: repaint; return
      -> LayerManager.hit_test(...)
          -> produce Hit (vertex/shape/pixel)
      -> SelectionRouter.handle_hit(hit, e)
          -> may start drag/capture
```

## Why this is performant and non-blocking

- **Non-blocking UI is mandatory**: nothing in this system may block the Qt UI thread.
  - No file I/O, no DB calls, no model inference, and no large CPU loops in event handlers (`mouseMoveEvent`, `wheelEvent`, etc.).
  - No heavy work inside `paintEvent` — it must be *pure rendering* of already-prepared data.

- Drawing is fast: only paints cached `QImage/QPixmap` for base + raster overlays and a few vectors.
- Heavy work (model inference, mask generation, depth colorization) must happen off-thread; the tool/layer just swaps in the latest ready-to-draw frame on the UI thread.
- Debounced UI updates: tools should coalesce rapid updates (e.g. brush move) into a steady redraw cadence.

## Proposed folder structure (core canvas + tools)

We want the **core canvas** to be usable by any workspace plugin (Capture, Annotation, Review, etc.).
Then we build **tools** (masking, polygons, selection) on top without turning the core into a monolith.

Principles:
- Keep the **core canvas widget** small, generic, and stable.
- Put tool logic in a **tools package** that depends on the core canvas API.
- Keep heavy computation out of the UI layer (use services/background work and feed results back).

### 1) Core canvas system (app-level)

**Goal**: a reusable `ImageCanvas` widget + small APIs for layers and tools.

Suggested location:

```
datalens/src/datalens/ui/canvas/
  __init__.py
  canvas_widget.py          # ImageCanvas(QWidget): base image + layer rendering + event entrypoint
  viewport.py               # ViewportTransform: pan/zoom; widget<->image coordinate mapping
  layers/
    __init__.py
    base.py                 # Layer protocol + Hit result dataclasses
    raster_layer.py         # RasterLayer: draws a QImage/QPixmap with opacity/compose mode
    vector_layer.py         # VectorLayer base helpers (optional; keep small)
    debug_layer.py          # Optional: debug overlay (FPS, bounds, hit-test markers)
  tools/
    __init__.py
    base.py                 # Tool protocol + ToolResult + tool capture semantics
    tool_manager.py         # ToolManager: active tool + routing rules
  selection/
    __init__.py
    router.py               # Default selection router for generic hit-test -> drag/capture behavior
  adapters/
    __init__.py
    qimage_bridge.py        # Helpers to convert numpy<->QImage safely (copy rules)
```

Why `datalens/ui/canvas`?
- It’s a UI widget system (Qt types), and many workspaces will use it directly.
- It keeps the canvas separate from plugin code while still being “core”.

### 2) “Standard tools” package (app-level, built on the core canvas)

**Goal**: a set of reusable, optional tools that many plugins will want.
This becomes the “V1-like toolbar tools” library.

Suggested location:

```
datalens/src/datalens/ui/canvas_tools/
  __init__.py
  polygon/
    __init__.py
    model.py                # Vertex/Edge/Polygon dataclasses (Qt-free if possible)
    layer.py                # PolygonLayer (vector): draw polygons + handles
    tool.py                 # PolygonTool: create/edit polygons, add/remove vertices
  mask/
    __init__.py
    model.py                # Mask meta (id, label, color, opacity); pixel data not copied here
    layer.py                # MaskLayer (raster): draws mask/heatmap
    paint_tool.py           # PaintTool: brush strokes -> updates MaskLayer
  common/
    __init__.py
    colors.py               # Theme-aware overlay colors (best-effort)
    snapping.py             # Optional: vertex snapping rules
```

Notes:
- Tool “models” should be Qt-free where practical (dataclasses), but it’s fine if vector geometry
  needs Qt-ish helpers as long as it stays out of services and out of DB layers.
- If we later decide tools should be plugin-scoped, this package can still exist as the shared default.

### 3) Plugin-local tools (plugin-owned extensions)

Some tools are specific to one plugin (e.g. Capture’s “depth overlay blend”, “edge detect”, “HDR preview”).
Those should live inside the plugin:

```
datalens/src/datalens/plugins/capture/
  tools/
    __init__.py
    overlay_depth.py        # Produces raster overlays; uses background work if heavy
    overlay_edges.py
    overlay_histogram.py
```

These tools consume the same core canvas API:
- they register a layer (raster or vector)
- they activate/deactivate via the plugin’s toolbar
- they update their layers when new frames arrive

### 4) Public API surface for plugins

We should expose a stable “plugin-facing” API module (thin re-exports + docs) so plugins don’t
import deep internal paths:

```
datalens/src/datalens/api/canvas.py
  # Re-export ImageCanvas, Layer/Tool protocols, and common layer/tool types we consider stable.
```

This mirrors how we treat other plugin-facing systems (sharing, commands, shortcuts).

### 5) Persistence + DB integration (future)

The canvas itself should not know about DB or projects.
Persistence belongs to plugin services (or a shared “annotations persistence” service) that:
- serializes tool model state (polygons, mask references) into PluginDb
- loads it on project open and populates layers
- writes changes via IoWriter/debounced persistence where appropriate
