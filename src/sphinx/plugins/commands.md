# Commands (cross-plugin requests)

See {doc}`sharing` for the overview of when to use capabilities vs commands vs events.

Commands provide request/response messaging between plugins without direct imports.

## When to use commands

- start/stop streaming
- change provider settings
- request a one-off computation (“compute X for me”)

## Design guidelines

- Commands should be **idempotent** where practical (repeat requests are safe).
- Handlers must be **fast**; for long work, enqueue onto DB/IoWriter/loader and return quickly.
- Do not block the UI thread waiting for results.

## Example (register + dispatch)

Register a handler (in `on_load` / `on_app_loaded`):

```python
from datalens.api.plugins import RegisteredHandler

ctx.app.commands.register(
    RegisteredHandler(
        command_id="capture.start_stream",
        handler=lambda cmd: {"accepted": True},
        owner_plugin_id=self.plugin_id,
    ),
    replace=True,
)
```

Dispatch (never block the UI thread on `.result()`):

```python
future = ctx.app.commands.dispatch("capture.start_stream", {"fps": 1})
future.add_done_callback(lambda f: print(f.result()))
```

## Example: Eval requests Capture

```{mermaid}
sequenceDiagram
    participant Eval as Eval plugin/workspace
    participant Bus as Command Bus
    participant Capture as Capture plugin/workspace

    Eval->>Bus: StartLiveStream(settings)
    Bus->>Capture: StartLiveStream(settings)
    Capture-->>Bus: Accepted/Rejected (+reason)
```

