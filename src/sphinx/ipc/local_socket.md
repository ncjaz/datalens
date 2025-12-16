# Local sockets (`QLocalServer` / `QLocalSocket`)

Local sockets provide the default “control plane” IPC for V2:

- RPC calls (request/response)
- low-rate events
- optional binary payloads (small/medium)

Implementation modules:

- `datalens.infra.ipc.local_socket`
- `datalens.infra.ipc.protocol`

## Message framing and data formats

Qt local sockets are a byte stream, so V2 uses explicit framing:

```text
[u32 header_len][u32 payload_len][header_json_utf8][payload_bytes]
```

Header:

- JSON object (UTF-8)
- must include a `kind` field: `hello`, `event`, `rpc_request`, `rpc_response`

Payload:

- raw bytes (optional)
- avoid base64 for performance

This supports two common payload strategies:

1) **Header-only** messages (all data in JSON): great for events, metadata.
2) **Header + binary payload**: good for small/medium blobs (zips, thumbnails).

For camera frames and other high-rate payloads, prefer shared memory (see
{doc}`shared_memory`).

## RPC usage (`RpcPeer`)

`RpcPeer` provides:

- `register(method, handler)` — register a handler for incoming RPC requests
- `call(request_id, method, params, ..., on_done=...)` — send an RPC request
- `event_received` — subscribe to events

Handlers must return quickly. If you need long work, schedule it to a background
system inside the worker process and respond later (future enhancement: async RPC).

## Example: ping worker

Host:

```python
from datalens.infra.ipc.protocol import new_request_id

def on_connected(rpc):
    rpc.call(new_request_id(), "ping", {"hello": "world"}, on_done=print)
```

Worker:

```python
def on_ready(rpc):
    rpc.register("ping", lambda params, payload: {"pong": True, "params": params})
```

## Latency notes

For local sockets on the same machine:

- transport overhead is typically sub-millisecond per message
- real latency often comes from serialization and copies (JSON, codecs, image decode)

If you need low-latency/high-FPS streaming, add shared memory.

## Pros / cons

Pros:

- simplest IPC building block (one channel for commands + events)
- good enough for most metadata and low-rate messages

Cons:

- large payloads are copied through the socket (bandwidth + CPU)
- codec overhead (JPEG/PNG) can dominate latency for video preview
