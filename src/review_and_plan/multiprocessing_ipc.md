# Multiprocessing + IPC (V2 plan)

This document defines a V2 plan for running **background workers out-of-process**
and communicating with them via **IPC**, while preserving the V2 non-blocking UI
rules and plugin safety guarantees.

Primary motivation:

- keep the Qt UI thread responsive even under heavy capture/indexing/training work
- isolate failures (worker crash/hang should not take down the UI process)
- provide a consistent, easy-to-use developer API (plugins should not reinvent IPC)

## Objective

Provide a core, cross-platform “IPC kit” that shipped and third-party plugins can
use to:

- spawn/manage worker processes (`QProcess`)
- send commands + receive results (RPC-style)
- stream low-rate events (pub/sub-style)
- optionally stream high-rate binary payloads (video frames) efficiently

## Non-goals (for the initial implementation)

- Rendering Qt widgets from another process inside the main window (not possible
  with standard Qt; UI plugins remain in-process).
- Remote workers across machines (TCP can be added later; initial scope is local-only).
- A full distributed actor system; this is a small, pragmatic wrapper.

## Constraints (must follow V2 rules)

- Never block the UI thread on:
  - worker startup/shutdown
  - IPC reads/writes
  - request/response waits
- Plugin code must be able to use this without importing other plugins.
- The wrapper must run on Windows/macOS/Linux.

## Proposed architecture

### Control plane (default): `QLocalServer` / `QLocalSocket`

Use Qt local sockets for:

- RPC: request/response (commands)
- events: low-rate notifications (file discovered, job status, etc.)
- small/medium payloads (JSON headers + optional binary payload)

Properties:

- cross-platform (named pipes on Windows, Unix domain sockets elsewhere)
- requires explicit framing (local sockets are a byte stream)

### Data plane (optional fast path): shared memory + local socket notifications

For high-rate payloads (e.g. camera frames), avoid copying multi-MB buffers
through the socket.

- shared memory holds the large payload (ring buffer / double buffer)
- local socket sends only a small notification (slot index + metadata)

## Message protocol (wire format)

Use a small, explicit framing format so we can parse messages reliably on all OSes:

```
[u32 header_len][u32 payload_len][header_json_bytes][payload_bytes]
```

- `header_json_bytes` is UTF-8 JSON (no base64 for binary data).
- `payload_bytes` is optional (can be empty).

Required header fields (minimum viable):

- `kind`: `"event" | "rpc_request" | "rpc_response" | "hello"`
- `id`: request id (for RPC)
- `topic` / `method`: routing fields for events/RPC
- `ok`: boolean for responses
- `meta`: dict for extensibility (timestamps, formats, etc.)

## Plugin developer UX

Goal: developers shouldn’t need to learn Qt socket details.

We want a high-level API that looks like:

- `worker = LocalWorkerProcess(...)`
- `worker.rpc.call("watch.start", {...}, on_done=...)`
- `worker.events.subscribe("files.discovered", handler=...)`
- `worker.stop()` (non-blocking; integrates with project flush hooks later)

## Cross-platform considerations

- Always call `QLocalServer.removeServer(name)` before `listen(name)` to clean up
  stale endpoints after crashes.
- Use short, ASCII-only endpoint names; some platforms have length limits.
- For shared memory, ensure the creator unlinks the segment during shutdown.

## Tasks (tracked)

### Phase 1: local-socket “control plane” (QLocalServer/QLocalSocket)

- [x] Define message dataclasses + codec helpers (encode/decode framing).
- [x] Implement `LocalIpcServer` / `LocalIpcClient` with non-blocking read/write.
- [x] Implement basic RPC layer (call + handler registry + timeouts).
- [x] Implement `QProcess` runner wrapper for starting/stopping workers.
- [x] Document usage patterns + examples in Sphinx.

### Phase 2: shared memory “data plane” (shared memory + socket notifications)

- [x] Implement shared-memory buffer helper (double-buffer or ring-buffer).
- [x] Define a frame/message header contract (width/height/format/stride/timestamp).
- [x] Document when to choose shared memory vs socket payloads.
- [x] Add backpressure/drop policy recommendations for streaming.

## Correctness criteria

- UI thread remains responsive even if a worker is slow/hung.
- Worker crashes do not crash the UI process; the wrapper reports failure.
- Framing is robust: partial reads/writes do not corrupt message boundaries.
- RPC responses map to the correct pending request and time out cleanly.
- Socket endpoints are cleaned up on restart across Windows/macOS/Linux.

## Validation steps

- Create a minimal “echo worker” that:
  - connects to the host via local socket
  - responds to `ping` RPC
  - emits a periodic `"tick"` event
- Host (UI process) starts worker, logs events, performs an RPC call, then stops worker.
