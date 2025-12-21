"""
Stable-ish identifiers for cross-plugin sharing (V2).

These constants are intended as a *convergence point* so core and plugin
authors don't invent competing strings for the same concept.

Notes:
- These IDs are a coordination mechanism, not a security boundary.
- Only constants explicitly documented as "implemented" should be relied on at
  runtime; others are reserved for future use.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Capabilities (pull / query)
# ---------------------------------------------------------------------------

# Implemented: returns `WorkspaceStateSnapshot` (core-owned snapshot).
CAP_WORKSPACE_STATE_SNAPSHOT = "datalens.workspace_state.snapshot"

# Implemented: returns a small dict with `has_project` + `project_root` (core-owned).
CAP_PROJECT_STATUS = "datalens.project.status"

# Reserved / planned (do not rely on these yet):
CAP_MEDIA_CURRENT = "datalens.media.current"
CAP_ANNOTATIONS_CURRENT = "datalens.annotations.current"

# ---------------------------------------------------------------------------
# Commands (push / request-response)
# ---------------------------------------------------------------------------

# Reserved / planned (do not rely on these yet):
CMD_PROJECT_OPEN = "datalens.project.open"
CMD_PROJECT_CLOSE = "datalens.project.close"
CMD_WORKSPACE_FOCUS = "datalens.workspace.focus"

__all__ = [
    "CAP_ANNOTATIONS_CURRENT",
    "CAP_MEDIA_CURRENT",
    "CAP_PROJECT_STATUS",
    "CAP_WORKSPACE_STATE_SNAPSHOT",
    "CMD_PROJECT_CLOSE",
    "CMD_PROJECT_OPEN",
    "CMD_WORKSPACE_FOCUS",
]

