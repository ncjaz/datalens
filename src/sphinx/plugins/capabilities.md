# Capabilities (shared providers)

Capabilities are how plugins share **data/services** without importing each
other.

## What to publish

Publish “provider” interfaces such as:

- live video frame stream (`LiveVideoSource`)
- model catalog/query interfaces
- shared indexing caches
- high-rate streams backed by a ring buffer (see :doc:`streaming`)

## Availability

Consumers must treat capabilities as **optional**:

- `get(capability)` returns `None` if the provider plugin is disabled/offline.
- UI should degrade gracefully and/or issue an activation request via commands.

## Don’t share widgets as data

If multiple tabs need a camera feed, expose the **feed** as a capability. If you
also want a shared preview UI, expose a *widget factory* capability like
`create_preview_widget(parent)`; consumers embed it, but still consume frames
from the underlying data capability (no “widget grab” screenshots).
