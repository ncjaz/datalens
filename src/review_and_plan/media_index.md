# Project Media Index (V2) — Plan

Status: **Implemented (v0)** (core schema + command + query capability)

## Objective

Create a **core-owned** media/file index for each project so:

- All plugins can reference files (images/video/etc.) by stable ids without scanning the filesystem repeatedly.
- Plugins do not need to poke each other's DB tables or import each other.
- The app can support filtering/browsing by directory (relative to project root) efficiently.

This is intended to be the canonical home for "what files exist in this project", regardless of whether they were:

- discovered by a file watcher / crawler, or
- created by a plugin (e.g. Capture saving images).

## Ownership model

- Table(s) are **core-owned** (migrated by core).
- Plugins do not write these tables directly via SQL.
- Instead, core exposes a stable registration entrypoint:
  - command: `datalens.media.register` (recommended)
  - and/or capability: `datalens.media.index` for querying

Capture (and other producers) should call the command to register newly created files.

## Proposed schema (v0)

Single table approach (start simple).

### `media_files`

Columns:

- `media_id` TEXT PRIMARY KEY (uuid/ulid or sha-based id)
- `relative_path` TEXT NOT NULL (posix-style, relative to project root)
- `dir_rel` TEXT NOT NULL (posix-style directory relative path, `""` for project root)
- `filename` TEXT NOT NULL
- `ext` TEXT NOT NULL
- `size_bytes` INTEGER NOT NULL DEFAULT 0
- `sha256` TEXT NULL (computed asynchronously; optional at first)
- `created_at_s` REAL NULL (filesystem mtime/ctime best-effort)
- `discovered_at_s` REAL NOT NULL (when the app indexed it)
- `source_plugin_id` TEXT NULL (who created it, if known)
- `source_kind` TEXT NOT NULL (e.g. `capture|watcher|import`)
- `mime` TEXT NULL (optional)

Indexes:

- `INDEX media_files_dir_rel ON media_files(dir_rel)`
- `INDEX media_files_sha256 ON media_files(sha256)`
- `INDEX media_files_discovered_at ON media_files(discovered_at_s)`

### Directory filtering strategy

Do **not** normalize directories into a separate table initially.

Instead:

- store `dir_rel`
- filter by:
  - exact directory: `WHERE dir_rel = ?`
  - subtree: `WHERE relative_path LIKE 'subdir/%'` (prefix query)

If we later need true directory trees (huge projects, advanced queries), we can add:

- a `media_dirs` table (optional)
- a materialized path index

## Interaction with file discovery

Two indexers can feed the same table:

1) **Crawler** at project-open (one-time scan)
2) **Watcher** (incremental updates)

Both use the same core command:

- register or update
- mark removed (optional) or delete row if the file is removed

## Non-blocking requirements

- Hash computation (sha256) must be background (IoWriter or a worker pool), never UI-thread.
- DB writes go through the `ProjectDb` executor.
- Producers should be able to register a file with "sha256 pending" and update later.

## Events (coarse)

After changes:

- publish `EventHub.MEDIA_DISCOVERED` / `MEDIA_REMOVED` / `MEDIA_LIST_UPDATED` (coarse, low-rate).
- avoid putting raw frame bytes on EventHub.

## Future consideration: cross-app sync (not implemented)

One reason to centralize a core media index (with stable ids + hashes) is to support future
networking/sync features (e.g. "project changes" replication between machines).

This plan does **not** implement networking, but it influences the schema:

- prefer stable `media_id` values (uuid/ulid)
- keep `relative_path`/`dir_rel` canonical and portable
- compute `sha256` asynchronously when enabled so content can be verified/deduplicated

## Implementation tasks

1) [x] Add core migrations for `media_files`.
2) [x] Add a core service (application layer) that owns registration + querying.
   - `register_media_file(...)` (core write, upsert by path)
   - `MediaIndexClient` (non-blocking query facade)
3) [x] Expose command(s) for plugins:
   - `CMD_MEDIA_REGISTER` (`datalens.media.register`)
   - `CMD_MEDIA_REMOVE` (optional / future)
4) [x] Add a small query capability for UI/plugins:
   - `CAP_MEDIA_INDEX` (`datalens.media.index`) returning `MediaIndexClient`
   - list by directory + latest N
5) [ ] Wire Capture post-save to register new files via the command.
6) [x] Document the contract in Sphinx (Plugins -> Sharing / Commands / Capabilities).
