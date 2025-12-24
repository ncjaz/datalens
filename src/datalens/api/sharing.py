"""
Stable-ish identifiers for cross-plugin sharing (V2).

These constants are intended as a *convergence point* so core and plugin
authors don't invent competing strings for the same concept.

Notes:

- These IDs are a coordination mechanism, not a security boundary.
- Only constants explicitly documented as "implemented" should be relied on at runtime; others are reserved for future use.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Capabilities (pull / query)
# ---------------------------------------------------------------------------

# Implemented: returns `WorkspaceStateSnapshot` (core-owned snapshot).
CAP_WORKSPACE_STATE_SNAPSHOT = "datalens.workspace_state.snapshot"

# Implemented: returns a small dict with `has_project` + `project_root` (core-owned).
CAP_PROJECT_STATUS = "datalens.project.status"

# Implemented: returns a JSON-serializable dict snapshot of plugin preferences
# (effective values + schema metadata), suitable for diagnostics UIs.
CAP_PLUGIN_PREFERENCES_SNAPSHOT = "datalens.plugin_preferences.snapshot"

# Implemented: returns a `MediaIndexClient` for non-blocking queries over the
# core-owned project `media_files` table.
CAP_MEDIA_INDEX = "datalens.media.index"

# Reserved / planned (do not rely on these yet):
CAP_MEDIA_CURRENT = "datalens.media.current"
CAP_ANNOTATIONS_CURRENT = "datalens.annotations.current"
CAP_CAPTURE_LIVE_FRAMES_V0 = "capture.live_frames.v0"

# ---------------------------------------------------------------------------
# Commands (push / request-response)
# ---------------------------------------------------------------------------

# Implemented: register a file into the core media index.
CMD_MEDIA_REGISTER = "datalens.media.register"

# Reserved / planned (do not rely on these yet):
CMD_PROJECT_OPEN = "datalens.project.open"
CMD_PROJECT_CLOSE = "datalens.project.close"
CMD_WORKSPACE_FOCUS = "datalens.workspace.focus"
CMD_CAPTURE_START = "capture.start"
CMD_CAPTURE_STOP = "capture.stop"

__all__ = [
    "CAP_ANNOTATIONS_CURRENT",
    "CAP_CAPTURE_LIVE_FRAMES_V0",
    "CAP_MEDIA_INDEX",
    "CAP_MEDIA_CURRENT",
    "CAP_PLUGIN_PREFERENCES_SNAPSHOT",
    "CAP_PROJECT_STATUS",
    "CAP_WORKSPACE_STATE_SNAPSHOT",
    "CMD_MEDIA_REGISTER",
    "CMD_CAPTURE_START",
    "CMD_CAPTURE_STOP",
    "CMD_PROJECT_CLOSE",
    "CMD_PROJECT_OPEN",
    "CMD_WORKSPACE_FOCUS",
]
