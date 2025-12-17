# Event Hub (Planned): App-Wide EventHub + Project Lifecycle Events

Status: **Planned (not implemented)**  
Owner: Core (plugin-safe contract)  
Primary docs: `docs/events.md` (event list + payload contracts)

## Objective

Provide a single, plugin-safe place for **semantic app events** so UI tabs, core services, and plugins can coordinate without:
- long Qt signal chains
- plugins holding references to internal UI objects
- blocking the publisher (especially the UI thread)

This plan assumes the "best choice" decision:
- `publish()` is **non-blocking**
- callbacks are delivered **queued on the UI thread by default**
- callbacks must be **fast** and schedule heavy work onto background systems (threadpool/loader/IoWriter), then marshal results back to UI (signals/queued call)

## Non-goals

- Replacing Qt signals for local widget wiring (signals remain the right tool for intra-widget interactions).
- Streaming large/high-rate payloads (e.g. video frames) through the hub. Use dedicated streaming/buffering/IPC primitives for that.
- Making every subscriber run "in parallel by default". That is unsafe for Qt and creates nondeterministic race conditions.
- Cross-plugin imports. Plugins should integrate via core-owned systems (events, capabilities, commands/requests), not by importing each other's code.

## Design (high-level)

### API surface (minimal)

- `EventHub.subscribe(event_name, callback) -> Subscription`
  - `callback(payload: object) -> None`
  - `Subscription.unsubscribe() -> None`
- `EventHub.publish(event_name, payload) -> None`
  - callable from any thread
  - enqueues delivery and returns immediately

Optional (later, only if needed):
- delivery mode per subscription: `delivery="ui"|"publisher"|"background"`
  - default remains `"ui"` for safety in a Qt+plugin ecosystem

### Threading & delivery semantics

- `publish()` never executes subscriber callbacks inline.
- Event delivery is queued onto the UI thread using a Qt-safe mechanism:
  - recommended: a `QObject` owned by the UI thread that drains an internal queue on a `QTimer.singleShot(0, ...)` tick
- Subscriber callbacks run in a deterministic order (subscription order) within the UI-thread drain loop.

### Error handling & robustness

- One subscriber exception must not break others:
  - catch exceptions per-callback and log with event name + subscriber identity
- Avoid re-entrancy traps:
  - if a callback publishes another event, it should enqueue and be delivered in a later tick (or guard against recursion).

### Payloads (typed dataclasses)

- Define payload dataclasses in `datalens/src/datalens/core/events.py` (or a `datalens/core/events/` package if it grows).
- Keep payloads Qt-free (no QWidget/QPixmap/etc) to remain plugin-safe and layer-clean.

### Project lifecycle integration

Project lifecycle must remain owned by `ProjectService` (correctness + ordering), but it should publish semantic events after state changes:

- `ProjectOpened(project_root, project_id?, timestamp, ...)`
- `ProjectClosing(project_root, reason, ...)`
- `ProjectClosed(project_root, ...)`
- `ProjectOpenFailed(project_root, error, ...)`
- `ActiveProjectChanged(previous_root, current_root)`

Plugins continue to use lifecycle hooks for "do the thing safely":
- app-scope: `on_load`
- project-scope: `on_project_migrate`, `on_project_opened`, `on_project_closing`

The hub is for "others can react" (UI refreshes, caches, indexers, uploaders, etc.).

## Tasks (ordered)

1) Implement `EventHub` in `datalens/src/datalens/core/events.py`
   - thread-safe queue + UI-thread drain
   - `Subscription` token with `unsubscribe()`
   - per-subscriber exception isolation + logging
2) Wire hub into runtime context
   - add `events: EventHub` to `AppContext` (`datalens/src/datalens/core/context.py`)
   - initialise in `create_app_context()`
3) Define initial event names + payload dataclasses (minimum viable set)
   - project lifecycle events (above)
   - optional: `SaveRequested`, `ExportRequested`, `PluginsEnabledChanged`
4) Publish project lifecycle events from `ProjectService`
   - publish after attach/close and on failures
   - ensure publish occurs off critical UI path (publish is queued anyway)
5) Document contracts
   - update `docs/events.md` with the new events + payloads
6) Plugin integration guidance
   - example: subscribe in `on_load`, unsubscribe in plugin disable/unload (when we add that lifecycle)
   - examples that schedule heavy work to background and return immediately

## Correctness criteria

- `publish()` never blocks the UI thread beyond enqueueing + scheduling one drain tick.
- Publishing from background threads is safe and does not call UI code on that thread.
- Subscriber callback failures are logged and do not prevent other subscribers from running.
- Project lifecycle events reflect actual state transitions (no "opened" without `active_project` set).

## Validation steps

- `python -m compileall -q datalens/src`
- Minimal smoke:
  - publish from background thread, verify subscriber runs on UI thread (Qt main thread)
  - publish from UI thread, verify it queues (does not inline-run subscribers)
