# Capture plugin (MVP)

The `capture` plugin provides a workspace for previewing a camera stream and saving individual images into the active project.

Status

- Webcams (OpenCV) are supported as the MVP.
- RealSense + other SDKs are planned (the UI is designed to hide unsupported controls).

## UX rules

- Preview works without an open project.
- Saving/registering requires an open project:
  - the Save button is disabled
  - the preview frame border shows the primary (orange) border to indicate “save gated”
- When there is no active camera source, the preview frame border is red (cancel border).
- The camera dropdown supports a best-effort hot-plug refresh control:
  - `Click` the refresh icon: refresh devices once (spinner animates while scanning)
  - `<modifier>+Click`: toggle continuous auto-refresh until stopped (default modifier is `Shift`)
  - the modifier is user-configurable via `settings.json`:
    - `plugin_settings.capture.auto_refresh_modifier` ∈ `shift|ctrl|alt|meta`
  - auto-refresh is paused while capture is starting/running (to keep selection stable)

## Sharing contracts

This plugin is designed to be consumed by other plugins without imports.

### Capability: `CAP_CAPTURE_LIVE_FRAMES_V0`

Defined in `datalens/api/sharing.py`:

- `CAP_CAPTURE_LIVE_FRAMES_V0 = "capture.live_frames.v0"`

Provider contract:

- `get_latest() -> FrameBundle | None`
- `status() -> dict[str, object]`

Frame payload type:

- `FrameBundle` is defined in `datalens/domain/system/frames.py`
- It is device-agnostic: `rgb` is required; `depth` and `intrinsics` may be `None`.

Consumer pattern (pull, best-effort):

```python
from datalens.api.sharing import CAP_CAPTURE_LIVE_FRAMES_V0

provider = ctx.app.capabilities.get(CAP_CAPTURE_LIVE_FRAMES_V0)
if provider is not None:
    frame = provider.get_latest()
```

### Commands: `CMD_CAPTURE_START` / `CMD_CAPTURE_STOP` (best-effort)

Defined in `datalens/api/sharing.py`:

- `CMD_CAPTURE_START = "capture.start"`
- `CMD_CAPTURE_STOP = "capture.stop"`

MVP payload:

- Start: `{"device_index": 0}`
- Stop: payload ignored

These commands do not provide a full “device negotiation” protocol yet; they are intended as a minimal coordination hook for other plugins.

## Saving + media index registration

On “Save image”:

- the plugin encodes a JPEG using `datalens/extensions/images/encode.py`
- writes it off the UI thread via `AppContext.io` (IoWriter)
- registers the file into the core media index via `CMD_MEDIA_REGISTER`

The media index record type is `MediaFileRecord` in `datalens/domain/system/media_index.py`.

### Output folder structure + intrinsics sidecar (v0)

Saved images are grouped by camera name under the chosen capture root:

- `<capture_root>/<camera_name>/rgb/<camera_name>_<timestamp>.jpg`
- `<capture_root>/<camera_name>/depth/<camera_name>_<timestamp>.png` (if depth is available)

On first capture for a camera (best-effort), the plugin writes:

- `<capture_root>/.camera_intrinsics_<camera_name>.json`

This JSON includes both RGB and depth intrinsics when available. Depth intrinsics may differ from RGB intrinsics.

## OpenCV backend configuration (cross-platform)

OpenCV camera enumeration/opening behaves differently across platforms and backends, and some backends
can print warnings or hang during probing.

DataLens keeps the defaults cross-platform, but exposes optional environment overrides for debugging/field work:

- `DATALENS_CAPTURE_OPENCV_BACKEND`
  - Empty (default): use platform heuristics (Windows prefers DSHOW, macOS AVFoundation, Linux V4L2).
  - `ANY`: let OpenCV pick its default backend.
  - A backend name such as `MSMF`, `DSHOW`, `AVFOUNDATION`, `V4L2` (or with `CAP_` prefix).
- `DATALENS_CAPTURE_OPENCV_BACKEND_FALLBACKS`
  - Optional comma-separated fallback list (e.g. `MSMF,DSHOW`).
- `DATALENS_CAPTURE_OPENCV_SILENCE_PROBE_LOGS`
  - `1` (default): suppress OpenCV WARN/ERROR spam during short device probes (restored immediately after).
  - `0`: leave OpenCV logging unchanged.
- `DATALENS_CAPTURE_ENUMERATION_MODE`
  - `indices` (default): list candidate webcam indices without opening devices (fast, may include non-existent indices).
  - `probe`: probe by opening devices (more accurate, can be slower/noisier).
- `DATALENS_CAPTURE_MAX_INDICES`
  - Maximum webcam indices to consider during enumeration (default used by the UI is `1`).

## Logging

- User-visible transitions log at `info` (`start`, `stop`, `save`).
- Debug logging avoids per-frame spam; a periodic “heartbeat” is used when debug logging is enabled.
