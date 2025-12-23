# Capture Plugin (V2) — Plan

Status: **Planned**

## Objective

Implement a V2 **Capture workspace plugin** that can:

- Connect to **Intel RealSense** cameras (via RealSense SDK).
- Connect to **standard webcams** (via OpenCV).
- Provide a V1-like UI workflow: device selection, preview, capture, and per-device controls.
- Provide **shared access** to the live frames and a **request API** (start/stop/capture) for other plugins without reimplementing capture.

Non-negotiables:

- Never block the UI thread (preview + capture + device enumeration must be non-blocking).
- No duplicate RealSense entries in the device dropdown.
- Avoid importing plugin-to-plugin code; sharing is via capabilities/commands/events.

## High-level UX (V1 parity with V2 adjustments)

## UI implementation rules (V2)

- Prefer DataLens V2 custom widgets where available:
  - Buttons: `DatalensButton` with semantic variants (Confirm/Cancel/etc.)
  - Toggles/checkboxes: DataLens core widgets (not ad-hoc QSS)
  - Dialogs: DataLens dialog patterns (Loader dialog for long operations)
- Avoid bespoke styling per-plugin unless the core widget set cannot express the design.

### Device dropdown

- One dropdown listing:
  - RealSense devices (deduplicated)
  - “normal” webcams
- Selecting a device chooses the backend automatically:
  - RealSense selection → RealSense backend
  - webcam selection → OpenCV backend

### Controls & relevance

- Controls shown are **backend-dependent**:
  - RealSense: show RealSense-specific controls (profiles, streams, exposure/auto-exposure if supported, etc.)
  - Webcam: hide controls not supported by OpenCV/video backend
    - webcam exposure may be supported on some cameras/drivers; treat as “best-effort capability”.

### Start/Stop

- One button that toggles:
  - “Start” → “Stop” when active.
- Styling:
  - “Start” uses **Confirm** semantic styling (green).
  - “Stop” uses **Cancel** semantic styling (red).

### Preview border warning

- If the preview is not showing a camera source, show a **red border** around the preview widget (use the theme’s warning/cancel border token).

### Save toggles

- Toggle: Save **RGB** images (always applicable).
- Toggle: Save **Depth** images (RealSense only; hidden/disabled for webcam).
- Toggle: **HDR/SDR** if supported by the RealSense profile; default **SDR**.

### Visibility optimization

- When the Capture workspace is **not visible/focused**, do not set/update pixmaps (avoid unnecessary work).
  - The capture pipeline may still run if other plugins need frames, but UI updates should be skipped.

## Sharing + control from other plugins

The Capture plugin must expose:

1) **Read access** to the most recent frames:
   - RGB frame (numpy array or encoded bytes)
   - Depth frame (if available)
   - camera metadata (timestamps, intrinsics if available, dimensions, fps)

2) **Request API** for:
   - start capture for a selected device
   - stop capture
   - request a “capture now” event (save current frame(s) or return copies)

We should support multiple consumers without coupling them to the capture UI:

- A “model test” plugin should be able to consume frames without implementing camera I/O.

### Contracts to use (V2)

- **Capabilities** (pull/query):
  - Provide “latest frame snapshot” capability.
  - Provide “device list snapshot” capability.
- **Commands** (push/request):
  - Start/stop/capture commands directed at the capture plugin.
- **Events** (notifications):
  - “capture started/stopped”
  - “device list changed”
  - “frame available” (coarse notifications only; not high-rate payloads)

## Implementation design

### Architecture split

- `datalens/plugins/capture/` (plugin package)
  - `plugin.py`: registers workspace widget + sharing registrations
  - `ui/`: workspace UI components
  - `services/`: capture pipeline orchestration (threads, backends)
  - `domain/` (plugin-local, optional): capture-specific dataclasses (device descriptors, frame packets)

Core rule: **RealSense/OpenCV I/O never runs on the UI thread**.

### Backend abstraction

Define a common interface used by the pipeline:

- `CaptureBackend` protocol:
  - `enumerate_devices() -> list[CaptureDevice]`
  - `open(device_id, config) -> CaptureSession`
  - `close()`
  - `read_latest() -> FramePacket | None`
  - (optional) set controls: exposure, auto-exposure, etc (capabilities-based)

Backends:

- `RealSenseBackend` (RealSense SDK)
- `OpenCvBackend` (cv2.VideoCapture)

### Device identity + deduplication

For RealSense:

- Define a stable device id key such as:
  - serial number (preferred)
  - fallback: USB path + name hash
- Deduplicate by this stable id; show friendly label in UI:
  - “RealSense D455 (Serial 0123456789)”

For webcam:

- Use OpenCV index + optional OS-level name if discoverable.

### Preview rendering

Avoid converting frames into QPixmaps on the capture thread:

- Background thread produces:
  - numpy arrays / bytes
  - minimal metadata
- UI thread converts for display when:
  - Capture workspace is visible
  - Preview is enabled

### Saving images

Saving must be non-blocking:

- Use `IoWriter` or ProjectService persistence mechanisms (depending on where the project is open).
- Decide output paths:
  - project-scoped capture output under project root (preferred)
  - user-scoped cache for “no project open” (optional, document)

#### Output folder structure + intrinsics sidecar (v0)

Capture output is grouped by camera name:

- `<capture_root>/<camera_name>/rgb/<camera_name>_<timestamp>.jpg`
- `<capture_root>/<camera_name>/depth/<camera_name>_<timestamp>.png` (RealSense only)

On the first capture for a given camera, write a best-effort dotfile (once):

- `<capture_root>/.camera_intrinsics_<camera_name>.json`

The payload includes `rgb_intrinsics` and, if available, `depth_intrinsics`.

Notes:

- Depth intrinsics may differ from RGB intrinsics (RealSense has separate stream intrinsics and usually extrinsics between streams).
- If intrinsics are unavailable (typical for webcams), the file is not created.

### Post-save hook (reserved)

Add an internal function/entrypoint (can be a no-op initially) that is invoked after the plugin
has successfully saved an image (and registered it in the project DB if a project is open).

This is a Capture-internal seam we can later use for:

- emitting richer events
- notifying other systems (e.g., auto-ingest / preview refresh)
- post-processing (hashing, generating thumbnails) as a background stage
- future cross-app networking/sync (e.g. publish a “new asset saved” message with enough metadata to replicate)

Proposed API shape (plugin-internal; implementation TBD):

- `on_image_saved(saved: SavedCaptureImage) -> None`

Where `SavedCaptureImage` includes:

- relative path(s) to files saved
- timestamps
- device id + backend kind
- hash (sha256) if computed (or “pending” if deferred)
- optional `media_id` if registered into the core media index (preferred for stable references)

### Project DB usage (plugin-owned)

Store capture configuration and history in PluginDb:

- last selected device id
- per-device settings selected in UI
- save toggles
- last save directory (if project open)

Do not store high-rate frame data in SQLite.

### Core media index registration (project-scoped)

When a project is open, the Capture plugin should register saved outputs into a **core-owned**
media index table (not plugin-owned tables), so all plugins can discover and reference files
without scanning the filesystem repeatedly or poking into other plugins’ tables.

See the core plan: `datalens/src/review_and_plan/media_index.md`.

This is where we track file-level metadata like:

- `relative_path` / `dir_rel` (for directory filtering relative to the project root)
- discovered/created timestamps
- optional `sha256` (computed asynchronously; never UI-blocking)

## Failure modes + UX

- No device selected → show warning in UI.
- Device open fails:
  - show a non-modal error summary
  - ensure pipeline is stopped and resources released
- Device disconnect while running:
  - stop pipeline
  - publish event “capture stopped (disconnected)”
  - update dropdown state

## Performance constraints

- UI thread:
  - only converts frames to pixmap when visible
  - no blocking I/O
- Capture thread:
  - should not allocate unbounded memory
  - should drop frames when consumers are slow (latest-frame semantics)

## Logging + diagnostics (required)

We want to avoid “it crashed with no logs”.

Capture should have both:

- **Info-level** logs for user-visible state transitions:
  - device selected
  - capture started/stopped
  - save toggles changed
  - capture requested (manual capture)
- **Debug-level** logs for troubleshooting:
  - enumeration results (counts, dedupe keys)
  - backend capability detection (what controls are supported)
  - frame drop/skip behavior (e.g. UI not visible, slow consumer)
  - command/capability registration
  - non-fatal exceptions handled best-effort (always log with traceback)

Use the V2 logging system (`datalens.core.logging.get_logger`) and bind plugin attribution where appropriate (plugin id, operation, phase).

## Validation checklist

- Start/Stop toggles without freezing the UI.
- RealSense device appears once in dropdown (no duplicates).
- Webcam selection hides RealSense controls.
- Save toggles:
  - RGB works for both backends
  - Depth toggle only visible/enabled for RealSense
- Another plugin can:
  - read the latest frame via capability
  - issue start/stop command to capture plugin
- When Capture workspace is not visible:
  - frames can still be produced (if desired)
  - UI does not update pixmap unnecessarily

## TODO (implementation order)

1) Define capture sharing contracts (capability ids + command ids).
2) Implement device enumeration (RealSense + OpenCV) + deduping.
3) Implement capture session pipeline + latest-frame buffer.
4) Implement Capture workspace UI (dropdown, preview, start/stop, toggles).
5) Implement saving pipeline (IoWriter) + PluginDb settings persistence.
6) Integrate sharing (capabilities + commands + events) + docs/examples.
