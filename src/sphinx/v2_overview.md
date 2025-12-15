# V2 overview

DataLens V2 is a re-architecture focused on:

- A clean separation between **domain** (dataclasses/contracts) and **runtime services** (I/O, persistence, plugin lifecycle).
- A consistently **non-blocking UI**: all long-running work happens off the UI thread.
- A first-class **plugin system** so shipped plugins and user-installed plugins behave the same way.

Start here, then read:

- `core_systems.md` for the runtime building blocks used throughout the app.
- `plugins/index.rst` for the plugin model (manifests, lifecycle, capabilities, commands).
- `services.md` for the application-layer services (projects, settings, persistence).

