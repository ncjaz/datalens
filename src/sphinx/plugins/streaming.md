# Streaming (shared high-rate data)

This page describes how V2 shares high-rate data (video frames, numpy arrays,
telemetry samples, etc.) between plugins without plugin-to-plugin imports.

## Goals

- Share data across tabs/services without importing other plugins.
- Decouple producer/consumer rates (60–120 Hz capture vs 10–30 Hz UI).
- Avoid broadcasting large payloads through the global event hub.
- Keep the mechanism **generic** (not video-specific).

## Architecture: capability + command + stream buffer

- **Capabilities** expose providers: “I can produce a stream”.
- **Commands** request actions: “start/stop/configure the stream”.
- **EventHub** broadcasts coarse state changes: “stream started/stopped”.
- **Ring buffer** holds recent samples for consumers at different rates.

```mermaid
flowchart TB
    subgraph Core["Core"]
        REG["Capability Registry"]
        BUS["Command Bus"]
        HUB["EventHub (coarse updates)"]
    end

    subgraph Provider["Provider plugin/service (e.g., Capture)"]
        CAP["Live capture service"]
        RB["RingBuffer[Sample] (in-process)"]
    end

    subgraph Consumer["Consumer plugin/tab (e.g., Eval/Review)"]
        UI["UI/worker loop"]
    end

    CAP -->|append(sample)| RB
    CAP -->|register Stream capability| REG
    UI -->|get stream capability (optional)| REG

    UI -->|StartStream(config)| BUS
    BUS -->|dispatch| CAP
    CAP -->|Accepted/Rejected| BUS

    CAP -.->|StreamStateChanged| HUB
    HUB -.->|notify subscribers| UI
    UI -->|poll latest_if_changed / read_since| RB
```

## The buffer: `RingBuffer[T]`

Implementation: `datalens/src/datalens/infra/streaming/ring_buffer.py`.

Recommended defaults:

- **Capacity**: 16 items for “latest + small history”.
  - This retains a small window without holding too many large objects alive.
  - Providers should make capacity configurable per stream when needed.
- **Change tracking**: every `append(value)` assigns a monotonically increasing
  integer sequence number (`seq`). Consumers should treat `seq` as the canonical
  “changed since last read” token (use `latest_if_changed(last_seq)` or
  `read_since(last_seq)`).

Core APIs:

- `append(value) -> seq`: producer writes new samples.
- `latest()`: consumer reads latest (may repeat).
- `latest_if_changed(last_seq)`: polling helper to avoid unnecessary work.
- `read_since(last_seq)`: pull all retained samples newer than `last_seq`,
  with a `dropped` flag if the consumer fell behind.
- `subscribe(callback)`: push notifications (callback runs on producer thread).

Timestamps:

- If consumers need wall/monotonic time, include it in the sample payload (`T`)
  (e.g., a `Sample` dataclass with `timestamp_ns` + `payload_ref`).

## What is a “sample”?

The ring buffer is generic and stores `T` by reference. A “sample” can be:

- a dataclass (e.g., `(timestamp, payload_ref, metadata)`),
- a numpy array (if treated as immutable by consumers),
- a small “ref” object pointing at shared memory / GPU buffer / bytes.

Guidelines:

- Prefer storing **references** (or immutable arrays) to avoid copying on every
  frame.
- If the producer reuses buffers, store an immutable copy or a reference-counted
  buffer type so consumers don’t see mutated data.

## How this ties into plugin communication

Typical pattern for a provider feature:

1. Register a capability (e.g., `LiveVideoStream`) that exposes:
   - `buffer: RingBuffer[VideoFrameRef]`
   - `state: StreamState`
2. Register command handlers:
   - `StartStream(config)`, `StopStream()`, `SetStreamConfig(config)`
3. Publish coarse state via the event hub:
   - `StreamStateChanged(stream_id, active, reason=None)`

Consumers:

- Query the capability registry; if missing, disable UI or request activation.
- Use `latest_if_changed` for UI redraw loops, or `read_since` for evaluation.
