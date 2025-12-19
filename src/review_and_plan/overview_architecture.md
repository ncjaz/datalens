# DataLens V2 Architecture Overview (Implementation Guide)

Last updated: 2025-12-17

This document is a high-level architectural overview of **DataLens V2 as implemented today**, plus the **next planned work**.

It complements:
- `datalens/src/AGENTS.md` (engineering rules + layering contract)
- `datalens/src/review_and_plan/project_db_and_persistence.md` (project DB + persistence plan/status)
- `datalens/src/review_and_plan/project_service.md` (project lifecycle plan/status)
- `datalens/src/review_and_plan/logging_system.md` (logging plan/status)
- `datalens/src/review_and_plan/event_hub.md` (EventHub plan/status)
- `datalens/src/review_and_plan/state_registry_and_inspector.md` (state registry + inspector plan/status)
- `datalens/src/review_and_plan/shortcuts_system.md` (keyboard + mouse shortcuts plan/status)

If you're looking for the older, very detailed architecture write-ups/diagrams (600+ lines), those still exist but are only partially accurate for V2:
- `datalens/src/review_and_plan/ARCHITECTURE_SUMMARY.md` (legacy, comprehensive narrative)
- `datalens/src/review_and_plan/architecture_diagram.md` (legacy, large Mermaid diagram)
- `datalens/src/_build/html/_sources/review_and_plan/*.md.txt` are generated build artifacts and can be stale

## Current V2 Architecture Diagram

```mermaid
flowchart TB
    subgraph Entry["Entrypoint / Startup"]
        APP[datalens/app.py<br/>main()]
        LOADER[run_with_loader()<br/>LoaderDialog + LoaderWorker]
        WELCOME[WelcomeWindow<br/>(modal)]
        MAIN[MainWindow<br/>(placeholder UI)]
    end

    subgraph Runtime["Runtime Context"]
        QAPP[DatalensApplication<br/>(QApplication)]
        APPCTX[AppContext<br/>(theme, io, active_project, hooks)]
        THEME[AppTheme]
    end

    subgraph Plugins["Plugin Runtime (V2)"]
        DISC[discover_plugins()<br/>metadata-only]
        HOST[PluginHost<br/>load/enable/hooks]
        RT[Plugin runtimes<br/>(on_load / on_project_migrate / on_project_opened / on_project_closing)]
        PDB[PluginDb<br/>plugin-scoped facade]
    end

    subgraph Persistence["Project Persistence (V2)"]
        PS[ProjectService<br/>load/open/close]
        PPATHS[project_paths.py<br/>.datalens/ layout]
        PSQL[ProjectDb<br/>SqliteProjectDb<br/>1 DB thread]
        IOW[IoWriter<br/>1 IO thread]
        PQ[PersistenceQueue<br/>merge->snapshot->save]
        SQLITE[(project.sqlite<br/>app_meta/plugin_kv/plugin_meta)]
        META[project_meta.json<br/>(derived)]
    end

    subgraph Logging["Logging (V2)"]
        LOG[core/logging.py<br/>QueueHandler -> QueueListener -> RotatingFile]
        CTXV[contextvars propagation<br/>DB/IO/loader threads]
        SLOW[Slow Qt event logging<br/>QApplication.notify]
    end

    %% startup
    APP --> QAPP
    QAPP --> APPCTX
    QAPP --> SLOW
    APP --> LOADER
    LOADER -->|startup result| WELCOME
    WELCOME -->|enabled plugins| LOADER
    LOADER --> MAIN

    %% plugins
    APP --> DISC
    DISC --> HOST
    HOST --> RT
    RT --> PDB
    PDB --> PSQL

    %% project persistence
    APP --> PS
    PS --> PPATHS
    PS --> PSQL
    PS --> IOW
    PSQL --> SQLITE
    IOW --> META
    MAIN --> PQ
    PQ --> PSQL

    %% logging
    APP --> LOG
    LOG --> CTXV
    CTXV --> PSQL
    CTXV --> IOW
    CTXV --> LOADER
```

## What's Implemented Today (V2)

### Startup flow + UI shell
- Entrypoint: `datalens/src/datalens/app.py`
- Loader UX (non-blocking): `datalens/src/datalens/infra/background/loader_runner.py`, `datalens/src/datalens/infra/background/loader_worker.py`, `datalens/src/datalens/ui/widgets/dialogs/loader_dialog.py`
- Welcome screen: `datalens/src/datalens/ui/welcome_window.py`
- Main window: `datalens/src/datalens/ui/main_window.py` (placeholder content today)
- QApplication wrapper + slow-event logging: `datalens/src/datalens/ui/application.py`

### Project DB + persistence primitives
- Per-project SQLite DB + executor: `datalens/src/datalens/services/db/project_db.py`
- Core schema + migrations (core-only): `datalens/src/datalens/services/db/migrations_runner.py`
  - Core tables: `app_meta`, `plugin_kv`, `plugin_meta`
- Project open/close lifecycle: `datalens/src/datalens/services/project_service.py`
- Async file writer (small/medium writes): `datalens/src/datalens/services/background_io/writer.py`
- PersistenceQueue (merge -> snapshot -> save): `datalens/src/datalens/infra/persistence_queue.py`
  - Example usage: `datalens/src/datalens/ui/main_window.py` persists per-project UI state to `plugin_kv`.

### Plugin runtime (minimal, but real)
- Discovery (metadata-only): `datalens/src/datalens/services/plugins/loader.py`, `datalens/src/datalens/services/plugins/registry.py`
- Host + lifecycle hooks: `datalens/src/datalens/services/plugins/host.py`, `datalens/src/datalens/services/plugins/runtime.py`
- Plugin migrations hook: `on_project_migrate` (core migrations complete first; plugins can migrate their own tables)
- Plugin-scoped DB facade: `datalens/src/datalens/services/db/plugin_db.py`
- Shipped plugins exist but are mostly placeholders; they at least record `plugin_meta` via `on_project_migrate`:
  - `datalens/src/datalens/plugins/*/plugin.py`

### Logging (plugin-aware, non-blocking)
- Central async logging pipeline: `datalens/src/datalens/core/logging.py`
- Context propagation into DB/IO/loader threads via `contextvars.copy_context()` (see `ProjectDb`, `IoWriter`, loader worker).

## What's Planned Next (High-Level)

This is the "roadmap" implied by the existing plans + current gaps.

## Feature Status Index (Single Source of Truth)

Use this section as the quick "what's left" checklist. Each item should point to an owned plan/spec doc and state whether it is complete.

| Feature | Objective | Plan/Spec | Status |
| --- | --- | --- | --- |
| Project DB + persistence | Non-blocking, plugin-safe project storage + flush semantics | `datalens/src/review_and_plan/project_db_and_persistence.md` | In progress (hardening ongoing) |
| Project service | Project open/close/switch orchestration + failure UX | `datalens/src/review_and_plan/project_service.md` | In progress (hardening planned) |
| Logging system | Non-blocking logging + UI slow-event profiling | `datalens/src/review_and_plan/logging_system.md` | In progress |
| Event hub | App-wide semantic events (queued UI-thread delivery; publish non-blocking) | `datalens/src/review_and_plan/event_hub.md` | Implemented (MVP) |
| State registry + inspector | Queryable core/plugin state + Help → States inspector | `datalens/src/review_and_plan/state_registry_and_inspector.md` | Planned |
| Shortcuts system | Keyboard + mouse shortcut registry/dispatcher (window-focused, plugin pages) | `datalens/src/review_and_plan/shortcuts_system.md` | Implemented (MVP) |

### 1) Real feature implementations (beyond placeholders)
- Build real workspace UIs for shipped plugins (annotation/review/meval/train/capture).
- Implement V2 annotation persistence pipeline (V1-style):
  - UI emits diffs -> merge/cache update -> snapshot -> background save -> flush on close.
  - Use `PersistenceQueue` + `ProjectDb`/`IoWriter` (depending on what becomes authoritative).

### 2) Event-driven coordination systems (in progress)
These are described in earlier planning docs; some exist as MVP implementations, others are still planned:
- Event hub (`EventHub`) is implemented (MVP), but richer patterns (channels, subscriptions, monitoring UI) are still planned.
- Capability registry
- Command bus

When implemented, they should follow the plugin safety rules in `datalens/src/AGENTS.md` (no plugin-to-plugin imports; stable contracts).

Plugin integration direction (intent):
- Plugins must not import each other or reach into each other's runtime objects.
- Cross-plugin integration should go via core-owned systems:
  - capability registry (providers)
  - command/request APIs (ask another capability to do work)
  - events (notify others that something happened)

### 3) Project/open UX hardening
- Finish the "project selection / open project" UI flows (welcome screen currently stores paths but the UI is still simplified).
- Decide and document the supported **no-project** startup mode ("open app without a project"), and enforce gating across UI + plugins (see `datalens/src/review_and_plan/project_service.md`).
- Consider adopting **UI-first startup**: show the main window with no project, then open the requested project via a loader flow (see `datalens/src/review_and_plan/project_service.md`).
- Ensure project open does not block UI and correctly stages:
  - inspect -> migrate core -> plugin migrate -> ready -> derived artifacts

### 4) Persistence consolidation
- Decide "settings write story" (debounced writer vs shared `IoWriter`) and document/enforce it.
- Expand per-project persistence beyond UI state (plugin state, indexes, caches).

## Threading Model (V2)

### UI thread (Qt)
- All widgets/windows/dialogs
- `PersistenceQueue.merge_func` + `snapshot_func` must run here if they touch Qt objects

### Background threads (Python / Qt)
- DB thread: `SqliteProjectDb` single-threaded executor
- IO thread: `IoWriter` single-threaded executor
- Loader thread: `LoaderWorker` uses a `QThread` for long tasks
- Optional: plugin-owned threads/pipelines (must flush via project flush hook)

### Cross-thread rules (non-negotiable)
- Never block the UI thread on I/O or `.result()` waits; use loader/background stages.
- If work is scheduled onto shared executors (DB/IO/loader), propagate logging context (`contextvars`).

## File/Directory Layout (V2)

### V2 source tree (contract)
- `datalens/src/datalens/domain/` – pure domain contracts (no Qt/I/O)
- `datalens/src/datalens/core/` – runtime context + cross-cutting (logging, context)
- `datalens/src/datalens/infra/` – low-level primitives (loader infra, persistence queue, paths)
- `datalens/src/datalens/services/` – application services (project lifecycle, DB, IO, plugins)
- `datalens/src/datalens/ui/` – UI widgets/windows
- `datalens/src/datalens/plugins/` – shipped plugins (manifest + runtime)

### Project layout (authoritative)
- `<project_root>/.datalens/project.sqlite` (authoritative core metadata + plugin state)
- `<project_root>/.datalens/project_meta.json` (derived; regenerable)

See `datalens/src/datalens/infra/project_paths.py` and `datalens/src/review_and_plan/project_db_and_persistence.md`.

## Implementation Checklist (Updated)

### Implemented (initial)
- [x] Async logging pipeline (queue + rotation) with context propagation
- [x] Loader UX for background tasks
- [x] ProjectDb + core schema + inspect-first open + core migrations (v0/v1 -> v2)
- [x] IoWriter async file writes + flush/close semantics
- [x] PersistenceQueue (merge/snapshot/save) primitive
- [x] Minimal plugin runtime + plugin migrations hook + plugin_meta tracking

### In progress / next
- [ ] Real plugin UIs (workspaces/tabs) beyond placeholders
- [ ] V2 annotation persistence pipeline (don't lose edits)
- [x] Event hub / command bus / capabilities (implemented MVP)
- [ ] File watcher/media discovery services (if still desired in V2)
