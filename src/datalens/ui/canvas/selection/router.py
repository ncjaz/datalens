from __future__ import annotations

from datalens.core.logging import get_logger
from datalens.ui.canvas.layers.base import CanvasHit

log = get_logger(__name__)


class SelectionRouter:
    """
    Minimal selection router (v0).

    This is a placeholder for future richer selection/drag capture behavior.
    For now it only logs hits so we can validate hit-testing + routing.
    """

    def handle_hit(self, hit: CanvasHit) -> bool:
        log.debug(
            "Canvas hit",
            extra={
                "operation": "canvas",
                "phase": "hit",
                "layer_id": str(hit.layer_id),
                "kind": str(hit.kind),
            },
        )
        return False

