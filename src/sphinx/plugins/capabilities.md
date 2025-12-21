# Capabilities (shared providers)

See {doc}`sharing` for the overview of when to use capabilities vs commands vs events.

Capabilities are how plugins share **data/services** without importing each other.

## What to publish

Publish "provider" interfaces such as:

- live video frame stream (`LiveVideoSource`)
- model catalog/query interfaces
- shared indexing caches
- high-rate streams backed by a ring buffer (see {doc}`streaming`)

## Availability

Consumers must treat capabilities as **optional**:

- `get(capability_id)` returns `None` if the provider plugin is disabled/offline.
- UI should degrade gracefully and/or issue an activation request via commands.

## Don't share widgets as data

If multiple workspaces need a camera feed, expose the **feed** as a capability. If you
also want a shared preview UI, expose a *widget factory* capability like
`create_preview_widget(parent)`; consumers embed it, but still consume frames
from the underlying data capability (no "widget grab" screenshots).

## Example (provider + consumer)

Provider (in `on_load` / `on_app_loaded`):

```python
from datalens.api.plugins import CapabilityProvider

ctx.app.capabilities.register(
    CapabilityProvider(
        capability_id="capture.live_source",
        provider=my_live_source,
        owner_plugin_id=self.plugin_id,
        description="Live camera frames provider.",
    ),
    replace_owner=True,
)
```

Consumer:

```python
live = ctx.app.capabilities.get("capture.live_source")
if live is None:
    return  # provider disabled/offline
frame = live.get_latest()
```

