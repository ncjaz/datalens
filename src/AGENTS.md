# Agent Instructions (DataLens V2)

These instructions apply to the V2 source tree rooted at `datalens/src/`.

## Core principles

- **Non-blocking UI is mandatory**: never block the Qt UI thread on I/O, model work, or long CPU tasks.
- **Plugins are first-class**: shipped plugins and user-installed plugins behave the same way; no plugin-to-plugin imports.
- **DDD layering**: keep domain dataclasses pure; put I/O, threading, and Qt in runtime layers.
- **Avoid monoliths**: keep files small and cohesive; split by feature/package when a file starts accumulating multiple concerns.
- **Document + verify**: add/maintain docstrings and docs pages; run sanity checks after changes (imports, signatures, smoke paths).

## V2 folder structure (contract)

Use this structure when deciding where new files belong:

- `datalens/domain/` – **pure domain contracts** (dataclasses/enums/IDs)
  - No Qt, no threads, no file/network I/O.
- `datalens/core/` – **runtime context + wiring contracts**
  - `AppContext` / `ProjectContext`, cross-cutting runtime concepts.
- `datalens/infra/` – **low-level infrastructure**
  - background execution primitives, path helpers, streaming, platform glue.
- `datalens/services/` – **application layer / use-cases**
  - project load/close lifecycle, persistence, settings, plugin discovery/runtime.
- `datalens/ui/` – **UI widgets/windows**
  - Prefer thin UI that calls services; keep non-trivial logic out of widgets.
- `datalens/plugins/` – **shipped plugins**
  - Discovered via `manifest.json`; may be grouped into subfolders (“packs”).
- `sphinx/` – **V2 documentation site** (Sphinx + MyST)
- `review_and_plan/` – **V2 planning/specs** (design notes, implementation plans)

## UI/UX rules

- **Theme-first styling**: use `AppTheme` helpers and opacity policy; avoid hard-coded colors.
  - See `sphinx/plugins/theming.md`.
- **Consistency**: reuse core widgets (`DatalensButton`, `Toggle`, etc.) instead of bespoke QSS.
- **Iconography**: new icons must follow V2 icon guidelines.
  - See `sphinx/plugins/iconography.md`.

## “UI + logic” pairing rule (avoid monolithic widgets)

When a feature needs both UI and non-trivial logic:

- Put **UI** in `datalens/ui/...` (widgets, layouts, signal wiring).
- Put **logic** in `datalens/services/...` or `datalens/infra/...` (I/O, DB, background work).
- Add cross-references in module docstrings so the pairing is easy to find:
  - UI module mentions the service/runner module(s) it depends on.
  - Service/runner module mentions the UI module(s) that present it.

Example (already implemented):

- UI: `datalens/ui/widgets/dialogs/loader_dialog.py`
- Runner: `datalens/infra/background/loader_runner.py`

## Background work / persistence (plugin-safe)

- **Loader runner**: use `datalens.infra.background.loader_runner.run_with_loader` for long tasks that need UX feedback.
- **Project DB**: plugin- and app-facing SQLite access goes through `ProjectDb` (`datalens/services/db/project_db.py`).
  - Core must never delete/corrupt plugin-owned tables.
- **File I/O**: use `IoWriter` (`datalens/services/background_io/writer.py`) for non-blocking disk writes.
- **Shutdown/flush**: services/plugins that manage pipelines must register a project flush hook:
  - `AppContext.register_project_flush_hook(...)`

## Plugins (agreement/contract)

- **Discovery is metadata-only**: do not import plugin runtime code just to list plugins.
  - Plugin roots are discovered recursively via `manifest.json` under:
    - `datalens/plugins/` (shipped)
    - `<user data dir>/plugins/` (user-installed)
- **No plugin-to-plugin imports**: sharing happens via stable systems:
  - capabilities (providers), commands (requests), streaming (high-rate data).
  - See `sphinx/plugins/*`.
- **Stage is a UX hint**: plugin `manifest.json` includes `stage` (`dev|alpha|beta|release`) for future welcome highlighting.

## Migrations + lifecycle entrypoints (core + plugins)

- Core DB migrations live in `datalens/services/db/migrations_runner.py`.
- Project open/close lifecycle is owned by `datalens/services/project_service.py`.
- Contract for future plugin migrations:
  - Core runs core migrations first.
  - Then the plugin runtime invokes enabled plugins’ migration hooks.
  - Core-owned metadata table tracks plugin schema versions (planned `plugin_meta`).
  - Core never alters plugin-owned tables beyond core-owned metadata rows.

## Planning process (Kiro-inspired specs)

For any new system (DB, streaming, plugin runtime, background pipelines):

- Create a short plan/spec in `review_and_plan/` before implementation:
  - **Objective**
  - **Tasks (ordered)**
  - **Correctness criteria** (what must be true)
  - **Failure modes** (what happens on errors)
  - **Performance constraints** (UI thread, throughput)
  - **Validation steps** (how we’ll confirm it works)

Kiro references:
- https://kiro.dev/docs/specs/concepts/
- https://kiro.dev/docs/specs/correctness/

## Validation expectations (don’t guess)

- Prefer verifying via codebase inspection + running checks:
  - `python -m compileall -q datalens`
  - targeted module imports
  - Sphinx `make html` when docs change (if the environment is set up)
- Avoid broad `except Exception: pass` unless errors are truly best-effort and logged/visible.
- If unsure about behavior/semantics, stop and confirm via:
  - existing V1 behavior (reference)
  - existing V2 patterns
  - upstream docs (Qt, Python, Sphinx, etc.)

