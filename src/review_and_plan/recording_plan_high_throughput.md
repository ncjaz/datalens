# High-throughput recording plan (Capture plugin)

This document outlines a robust plan for **high-throughput recording** from
multiple cameras (webcams/OpenCV, RealSense SDK), targeting **PNG sequences
initially** with a clean upgrade path to **MJPEG/H264/H265 via ffmpeg**.

The goals are:

- sustained throughput without freezing the UI
- predictable backpressure (bounded memory)
- simple plugin developer experience (a reusable pipeline inside the capture plugin)
- clean integration with project persistence (SQLite + file layout)

## Key constraints (reality check)

- USB bandwidth is often the first bottleneck (multiple cameras at 15fps+).
- Writing many small PNG files adds:
  - CPU overhead (encoding/compression)
  - filesystem overhead (lots of small files)
  - disk bandwidth requirements
- A general-purpose “IoWriter” queue is not suitable for sustained frame capture.
  It is designed for small/medium writes (JSON, manifests, metadata).

## Recommended architecture

### Per-camera pipeline (threaded)

Each camera gets its own pipeline with explicit backpressure:

1. **Capture worker** (per camera)
   - Runs in its own thread.
   - Talks to the camera SDK (OpenCV/RealSense) and produces frames with:
     - timestamp (monotonic + wall time if needed)
     - frame index
     - optional metadata (exposure, depth scale, intrinsics)
2. **Bounded queue** (per camera)
   - Fixed size N to prevent RAM growth.
   - Configurable overflow policy:
     - drop-oldest (keeps latest frames; best for “live”)
     - drop-newest (preserves continuity; best for “record exact”)
     - block (generally avoid: can destabilize capture timing)
3. **Recorder backend** (per camera)
   - Consumes frames and writes to disk.
   - Encapsulated behind a stable interface so we can swap formats later.

### Recorder backend interface

Inside the capture plugin, define:

- `Recorder.start(session_dir, stream_meta) -> None`
- `Recorder.write(frame) -> None`
- `Recorder.stop() -> None`

Initial implementation:

- `PngSequenceRecorder`:
  - writes `rgb_000001.png`, `depth_000001.png`
  - uses monotonic numbering + timestamps for ordering

Future implementations:

- `FfmpegRecorder` (per camera stream):
  - spawns an ffmpeg subprocess and pipes frames
  - supports MJPEG / H264 / H265
  - reduces file count and can be much faster than per-frame PNG

## Project integration

### File layout (suggested)

Within the project root:

- `captures/`
  - `session_YYYYMMDD_HHMMSS/`
    - `camera_<id>/`
      - `rgb/` (PNG sequence) or `rgb.mp4` (future)
      - `depth/` (PNG sequence) or `depth.mkv` (future)
      - `meta.json` (intrinsics, fps, encoder settings, etc.)

Keep app-managed state under:

- `<project_root>/.datalens/`
  - `project.sqlite` (project metadata/index)
  - `project_meta.json` (derived, human readable)

### SQLite usage (indexing, not storage)

Do not store frames as SQLite blobs.

Use SQLite to store:

- capture sessions (start/stop time, config)
- camera streams (id, type, intrinsics refs)
- per-file index entries (optional):
  - frame index → relative path → timestamp

This enables:

- “Eval” tab to find the latest capture outputs
- fast queries without scanning the filesystem

## Performance and robustness practices

### Avoid UI blocking

- Capture threads never call Qt UI APIs directly.
- UI updates are signals/queued events: “fps”, “dropped frames”, “disk lag”.
- Disk I/O never runs on the UI thread.

### Backpressure and drop policy

Expose settings:

- queue depth per camera (default e.g. 30–60 frames)
- overflow policy (default: drop-oldest for live capture)

### Atomic metadata

Write a session-level `meta.json`:

- written at start (planned config)
- updated at end (final counts, dropped frames)
- use atomic write (tmp → rename)

### Monitoring

Track per camera:

- capture fps
- encode/write fps
- queue depth
- drop count
- disk write latency

Show a compact status in the status bar and a detailed panel in the capture tab.

## Threading vs multiprocessing

Recommended default:

- per-camera capture threads
- per-camera recorder threads (or a small recorder pool)

Consider ffmpeg subprocesses (recommended “multi-process” path):

- keep Python simple; encoding happens outside Python
- one ffmpeg process per camera stream is a common, robust pattern

Use full multiprocessing only if:

- SDK or encoding is unstable in threads, or
- Python CPU becomes the bottleneck and cannot be moved to native code/subprocess.

## Suggested implementation order

1. Define capture plugin session model (domain objects: SessionId, CameraStreamId, settings)
2. Implement `PngSequenceRecorder` + bounded queues + per-camera threads
3. Add session metadata JSON + SQLite session index tables
4. Add UI controls for queue depth + overflow policy + output dir
5. Add ffmpeg recorder backend (MJPEG first, then H264/H265)

