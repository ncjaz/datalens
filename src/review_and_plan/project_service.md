# Project Service (Plan): Project Open / Close / Switch Lifecycle

Status: **Planned hardening + consolidation (partially implemented)**  
Implementation: `datalens/src/datalens/services/project_service.py`  
Related plans: `datalens/src/review_and_plan/project_db_and_persistence.md`, `datalens/src/review_and_plan/event_hub.md`

## Objective

Make project lifecycle operations **correct, non-blocking, and consistent** across the entire app:

- Open / close / switch projects through a single authority (`ProjectService`).
- Enforce non-blocking UI: no I/O waits on the Qt main thread.
- Provide predictable plugin lifecycle ordering (migrate -> opened; closing flush hooks).
- Define failure UX for close/flush failures (warn/retry/block close behavior).
- Publish semantic project lifecycle events (via EventHub, planned) after state transitions.

## Current state (as implemented today)

The service file `datalens/src/datalens/services/project_service.py` already provides:

- `load_project(...)` (background-only; guarded by `_require_not_ui_thread`)
  - creates/opens per-project DB via `SqliteProjectDb`
  - inspects first using read-only DB connection
  - ensures/migrates core schema without touching plugin-owned tables
- `attach_project(...)` sets `AppContext.active_project` (gating)
  - schedules best-effort derived `project_meta.json` write via `IoWriter`
- `close_project(...)` (best-effort)
- `close_project_blocking(...)` (flush guarantees)
  - runs plugin flush hooks, then DB flush, then IO flush

However, the *application-wide* “always go through this service for lifecycle” rule is not fully enforced yet:

- Some lifecycle coordination is currently staged from `datalens/src/datalens/app.py` (loader stages + plugin hooks).
- There is not yet an app-wide EventHub implementation (see `datalens/src/review_and_plan/event_hub.md`).

## Non-goals

- Putting long-running work in the UI layer.
- Making plugin hooks run on the UI thread.
- Making derived artifacts (like `project_meta.json`) part of the open critical path.
- Adding a complex workflow engine; keep lifecycle sequencing explicit and testable.

## Canonical lifecycle contract

## No-project mode (supported, but requires discipline)

DataLens V2 should support starting the app with **no project open** (e.g. welcome -> main window, or "Continue without project").

Frankly: this direction is fine, but it is **not free**. It increases the amount of gating we must do across the UI and plugins, otherwise we will get:
- runtime errors from `app_ctx.require_project()` (by design it raises)
- subtle bugs where plugins/services assume a project DB exists
- inconsistent behavior between “started with project” vs “opened project later”

If we commit to this, the following becomes a contract:

- `AppContext.active_project` is allowed to be `None` for long periods.
- Any project-dependent UI action must be disabled/hidden or must prompt the user to open/create a project.
- Plugins must treat `on_load` as **app-scope only** (safe with no project), and only start project-scoped work in:
  - `on_project_migrate`
  - `on_project_opened`
- Project open/switch is the moment we “turn on” project-scoped systems:
  - ProjectService attaches the project, invokes plugin hooks in order, and (later) publishes project lifecycle events via EventHub.

This is exactly why the “single authority” goal matters: every project-open path must use the same orchestrated pipeline so hooks/events always fire.

## Startup sequencing (planned): show UI first, open project after

Instead of "startup WITH a project", prefer:

1) start the app and show `MainWindow` (with `active_project = None`)
2) then open the requested project (welcome selection or `--load-last-project`) using a loader stage/overlay

This is a good UX direction (faster perceived startup), but it is only safe if we fully commit to "no project" gating. If we half-implement it, it will feel flaky.

Contract if we adopt this:

- The main window must have a clear "No project open" state and disable/guard project-dependent actions.
- Plugin UIs must tolerate the project being opened later (no project assumptions at construction time).
- Every project-open path must use the same orchestrated pipeline so plugin hooks and (later) EventHub events always fire.

### Open (or switch) project (high-level)

1) Validate input path (create if needed; reject invalid).
2) If a project is already open: close it (blocking, with flush semantics).
3) Load project resources (DB executor, core schema ensure/migrate).
4) Attach project to `AppContext` (`active_project` becomes non-None).
5) Run plugin project hooks (ordering must be consistent):
   - `on_project_migrate`
   - `on_project_opened`
6) Best-effort derived artifacts:
   - schedule `project_meta.json` generation/write (must never block UI)
7) Publish lifecycle events (planned EventHub):
   - `ProjectOpened`, `ActiveProjectChanged`, etc.

### Close project (high-level)

1) Run plugin flush hooks (plugins own their pipelines).
2) Flush DB executor (authoritative project state).
3) Flush IO writer (derived artifacts, exports, caches).
4) Close DB resources.
5) Set `AppContext.active_project = None`.
6) Publish lifecycle events (planned EventHub):
   - `ProjectClosing` (with reason: `switch|user|shutdown|force|open_failed`), then `ProjectClosed`, etc.

## Threading & UI rules (non-negotiable)

- `ProjectService.open/close/load` must never run on the Qt UI thread.
- UI triggers must use:
  - loader stages (`run_with_loader` / `run_with_loader_sequence`) **or**
  - an async wrapper that uses background execution and reports progress safely.
- Any UI updates resulting from project transitions must be marshaled back onto the UI thread.

## Plugin integration contract

### Hooks (already implemented)

Plugins are notified through `PluginHost` lifecycle hooks:

- `on_load(ctx)` runs when the plugin is enabled for the current app run (app-scope; must be safe with no project open).
- `on_project_migrate(ctx)` runs after core schema is ready, before `on_project_opened`.
- `on_project_opened(ctx)` runs after the project is attached.
- `on_project_closing(ctx)` runs during close (via `AppContext.register_project_flush_hook`).

There is not yet a dedicated `on_unload`/`on_disable` hook; today plugins are effectively "enabled for this run". If/when we add runtime enable/disable, we need explicit spin-down hooks and event unsubscription guidance.

## App-level project open hooks (core developer entrypoints)

In addition to plugin hooks, core/app developers can register app-level entrypoints on the `AppContext`:

- `AppContext.register_pre_project_open_hook(hook: Callable[[Path], None])`
  - Runs on the project open worker thread immediately before the open/switch begins.
- `AppContext.register_post_project_open_hook(hook: Callable[[ProjectContext], None])`
  - Runs on the project open worker thread after the project is attached and ready (after plugin hooks and meta scheduling).

These hooks are best-effort: exceptions are logged and do not abort the open pipeline.

Practical guidance for plugin authors:

- Start app-scope background services in `on_load` (e.g. IPC servers, model warm-up, UI registration), but keep it non-blocking.
- Start project-scoped pipelines only once `on_project_opened` runs (DB/state exists).
- Flush/stop project-scoped work in `on_project_closing` so `close_project_blocking(...)` can guarantee data integrity.

### Ownership and scoping

- Core must never modify plugin-owned tables beyond core-owned metadata rows.
- Plugins should use the scoped facade `PluginDb` (`datalens/src/datalens/services/db/plugin_db.py`).

## Failure modes & UX (to implement)

### Close/flush failures

Decide and implement a consistent policy for `close_project_blocking(...)` failure:

- Warn + allow retry (recommended).
- Block app close if flush fails (data integrity-first).
- Provide “force close” (only if we explicitly accept data loss risk).

The UI surface for this should live in UI code (dialog), but the policy and exceptions should be defined here.

### Open failures

- If open fails during load/migrate: do not mutate `active_project`.
- If open fails after closing an existing project: decide whether to:
  - keep app with no project open, or
  - attempt rollback (likely not feasible; avoid promising it).

All failures must be visible in logs, and surfaced to the user via loader error UI.

## Tasks (ordered)

Status (as of 2025-12-17):

- [x] Consolidate lifecycle entrypoints (welcome + File menu + MRU/startup all go through `open_project_with_plugins(...)` via loader tasks).
- [x] Orchestrated open/switch pipeline exists (staged loader messages + UI-first startup flow).
- [x] Close/flush failure UX policy exists (warn/retry/cancel/force-close via loader UX).
- [x] Plugin hook invocation is consistent via `open_project_with_plugins`.
- [x] Event publication via EventHub (implemented for core project + plugin lifecycle events).
- [ ] Documentation alignment across planning docs (ongoing).

Notes:

- The non-hook project open helper was removed to prevent accidental bypass of plugin lifecycle:
  - `datalens/src/datalens/services/project_service.py` now exposes `open_project_with_plugins(...)` as the canonical pipeline.
- UI entrypoints call `MainWindow.open_project(...)` / `MainWindow.close_project(...)` which delegate into the loader-backed UX (`ProjectActionsController`).

1) Consolidate lifecycle entrypoints
   - ensure all “Open/Switch/Close” UI actions call `ProjectService` (directly or via an orchestrator service).
2) Define an orchestrated open/switch pipeline
   - staged loader messages + progress (inspect -> core migrate -> plugin migrate -> plugin opened -> ready)
   - if we adopt UI-first startup: show main window first, then run the open pipeline (loader overlay/flow)
3) Implement close/flush failure UX policy
   - define timeout defaults; warn/retry/block behavior
   - centralize defaults in a single policy object used by UI orchestration (see `datalens/src/datalens/services/project_close_policy.py`)
4) Align plugin hook invocation location
   - ensure hooks are invoked consistently no matter where the open is triggered (welcome vs menu vs MRU)
5) Event publication (depends on EventHub plan)
   - publish project lifecycle events after state transitions
6) Documentation updates
   - keep `project_db_and_persistence.md` and `overview_architecture.md` aligned with the canonical contract

## Correctness criteria

- UI thread never blocks on `.result()` waits for project DB/IO/plugin futures.
- `active_project` accurately reflects open/closed state (no “opened event” without attach).
- Plugin hooks run in a consistent order and are awaited/handled per policy.
- Derived artifacts (`project_meta.json`) are strictly best-effort and never on the open critical path.
- Close/flush failure policy is explicit, logged, and user-visible.

## Validation steps

- `python -m compileall -q datalens/src`
- Manual smoke:
  - open project from welcome and from menu (when available)
  - switch project (close old -> open new)
  - close app with an active project; verify flush hooks run and timeouts behave as documented
