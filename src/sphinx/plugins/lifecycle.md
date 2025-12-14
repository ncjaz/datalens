# Plugin lifecycle

The plugin runtime owns plugin lifetimes and keeps the UI consistent when
features are enabled/disabled.

## Phases

1. **Discover**: locate plugin definitions (builtin + external).
2. **Load**: import entrypoints and build feature objects.
3. **Enable**: register features, capabilities, and command handlers.
4. **Activate**: (UI) create tabs lazily when selected; (services) start workers.
5. **Disable**: unregister capabilities/handlers and stop background work.

## UI tabs

Tabs should be created lazily and should not assume that other plugins are
available. If a dependency capability is missing, the tab should:

- disable the relevant UI controls, and/or
- offer an “enable provider” action (via the command bus).
