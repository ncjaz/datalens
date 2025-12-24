from __future__ import annotations

"""
Capture plugin stable identifiers (shared between plugin runtime + UI).

Keep these in a small dedicated module to avoid import cycles between:
- `datalens.plugins.capture.plugin` (imports UI lazily)
- `datalens.plugins.capture.ui.workspace` (UI code)
"""

# Gesture binding used by the refresh toolbutton:
# - Click: refresh once (always)
# - Primary+Click: toggle auto-refresh (continuous rescan while stopped)
CAPTURE_GESTURE_AUTO_REFRESH_TOGGLE = "auto_refresh_toggle"
CAPTURE_GESTURE_AUTO_REFRESH_DEFAULT_CHORD = "Primary+LeftClick"

