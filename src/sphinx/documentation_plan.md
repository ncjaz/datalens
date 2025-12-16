# Documentation plan (V2)

This is the staged plan for turning the current V2 skeleton into a navigable,
maintainable documentation site.

## 1) Stabilise the docs build

- Keep `datalens/src/sphinx/conf.py` importing only V2 code (avoid the V1
  `src/datalens` package on `sys.path`).
- Keep optional runtime dependencies mocked/stubbed so API generation is stable.
- Prefer Mermaid diagrams for architecture docs where they clarify cross-module
  relationships.

## 2) Document the contracts first

- `datalens.domain`: dataclasses and invariants (IDs, normalized geometry, etc.).
- Core coordination contracts: event hub payloads, capability interfaces, command
  request/response payloads.
- Streaming contracts should standardise on monotonic `seq` counters as the
  primary “changed since last read” token; timestamps belong in the payload when
  needed.

## 3) Flesh out core systems docs as they land

- Plugin runtime lifecycle (load/enable/disable, tab registration).
- Capability registry and command bus behaviour (availability, activation
  requests, reject reasons, cleanup).
- Persistence and background worker patterns.

## 4) Expand API pages by area (not one mega page)

When modules become non-empty, add them to the appropriate `sphinx/api/*.rst`
page so the API stays grouped by concern.
