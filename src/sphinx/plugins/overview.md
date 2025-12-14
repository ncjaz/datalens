# Plugin overview

V2 plugins are **optional**, **isolated** feature packages that integrate with
the host application through stable contracts (domain types + plugin runtime
interfaces).

## Goals

- Allow features to be enabled/disabled independently.
- Avoid plugin-to-plugin imports (keep boundaries clean).
- Support “provider might be offline” gracefully.
- Enable shared systems (e.g., live camera feed) to be consumed by multiple tabs.

## What a plugin can provide

Common plugin feature kinds:

- **Tab/workspace**: a UI surface (e.g., Capture, Review, Eval).
- **Service**: background logic (indexing, syncing, watchers).
- **Data source**: a storage backend or remote API provider.
- **Model**: model families/variants and runtime wiring.

## Rules

- Plugins should depend on **core/domain contracts**, not other plugins.
- Shared resources should be exposed as **capabilities** (data/services), not by
  handing out internal widgets.
- Cross-plugin requests should go through the **command bus** (request/response),
  not direct method calls.
