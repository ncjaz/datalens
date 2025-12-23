from __future__ import annotations

import time
from typing import Any

from datalens.api.sharing import CAP_CAPTURE_LIVE_FRAMES_V0, CMD_CAPTURE_START, CMD_CAPTURE_STOP
from datalens.core.events import EventHub, StatusMessageRequested
from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.domain.system.shortcuts import GestureBindingSpec, GestureId, ShortcutChord, ShortcutPageSpec, ShortcutScope, ShortcutSectionSpec
from datalens.services.capabilities import CapabilityProvider
from datalens.services.commands import RegisteredHandler
from datalens.services.plugins.runtime.contracts import PluginAppContext, ProjectAwarePlugin

from .ids import CAPTURE_GESTURE_AUTO_REFRESH_DEFAULT_CHORD, CAPTURE_GESTURE_AUTO_REFRESH_TOGGLE
from .service import CameraDevice, CameraKind, CaptureService, LiveFramesProvider

log = get_logger(__name__)


class CapturePlugin(ProjectAwarePlugin):
    """
    Capture workspace plugin (webcam-first MVP).

    Pairing:
    - UI: `datalens/plugins/capture/ui/workspace.py`
    - Runtime service: `datalens/plugins/capture/service.py`

    Contract:
    - Preview can run with no project open.
    - Saving works without a project; media index registration requires an open project.
    """

    def __init__(self) -> None:
        super().__init__()
        self._service = CaptureService()
        self._workspace_widget: Any | None = None

    @property
    def plugin_id(self) -> PluginId:
        return PluginId("capture")

    def on_load(self, ctx: PluginAppContext) -> None:
        super().on_load(ctx)
        log.info("Capture plugin loaded", extra={"operation": "capture", "phase": "load"})

        # Expose latest frames to other plugins via a stable capability id.
        ctx.app.capabilities.register(
            CapabilityProvider(
                capability_id=CAP_CAPTURE_LIVE_FRAMES_V0,
                provider=LiveFramesProvider(self._service),
                owner_plugin_id=self.plugin_id,
                description="Capture live frames provider (get_latest FrameBundle).",
            ),
            replace_owner=True,
        )

        # Allow other plugins to request start/stop via commands (best-effort).
        ctx.app.commands.register(
            RegisteredHandler(
                command_id=CMD_CAPTURE_START,
                owner_plugin_id=self.plugin_id,
                description="Start capture (payload: {'device_index': int}).",
                handler=lambda cmd_ctx: self._cmd_start(cmd_ctx.payload),
            ),
            replace=True,
        )
        ctx.app.commands.register(
            RegisteredHandler(
                command_id=CMD_CAPTURE_STOP,
                owner_plugin_id=self.plugin_id,
                description="Stop capture (payload ignored).",
                handler=lambda cmd_ctx: self._cmd_stop(),
            ),
            replace=True,
        )

    def register_shortcuts(self, ctx: PluginAppContext) -> None:
        """
        Register Capture's gesture bindings in Preferences -> Keyboard Shortcuts.

        Notes:
        - These are widget-level gestures (not globally dispatched commands).
        - The refresh button always supports click-to-refresh; this binding controls
          the modifier-click that toggles auto-refresh.
        """

        page = ShortcutPageSpec(
            page_id="capture",
            title="Capture",
            sections=(
                ShortcutSectionSpec(
                    section_id="devices",
                    title="Devices",
                    gestures=(
                        GestureBindingSpec(
                            gesture_id=GestureId(CAPTURE_GESTURE_AUTO_REFRESH_TOGGLE),
                            title="Toggle auto-refresh (modifier-click)",
                            description=(
                                "Hold this modifier while clicking Refresh to toggle auto-refresh scanning. "
                                "By default this follows the global Primary modifier."
                            ),
                            begin_chord=ShortcutChord(CAPTURE_GESTURE_AUTO_REFRESH_DEFAULT_CHORD),
                            scope=ShortcutScope.WORKSPACE,
                            consume_event=True,
                        ),
                    ),
                ),
            ),
        )

        ctx.app.shortcuts.register_page(
            plugin_id=self.plugin_id,
            plugin_name=str(ctx.plugin.name or ctx.plugin.id),
            page=page,
            callbacks={},
        )
        log.info(
            "Shortcuts registered",
            extra={
                "operation": "capture",
                "phase": "register_shortcuts",
                "gesture_id": CAPTURE_GESTURE_AUTO_REFRESH_TOGGLE,
                "default_chord": CAPTURE_GESTURE_AUTO_REFRESH_DEFAULT_CHORD,
            },
        )

    def on_unload(self, ctx: PluginAppContext) -> None:
        log.info("Capture plugin unloading", extra={"operation": "capture", "phase": "unload"})
        try:
            self._service.stop_async()
        except Exception:
            log.debug("CaptureService stop failed (best-effort)", exc_info=True)
        super().on_unload(ctx)

    def on_focus(self, ctx: PluginAppContext) -> None:
        # The workspace widget may not exist yet (created lazily).
        try:
            if self._workspace_widget is not None:
                fn = getattr(self._workspace_widget, "set_view_active", None)
                if callable(fn):
                    fn(True)
        except Exception:
            log.debug("Capture focus update failed (best-effort)", exc_info=True)

    def on_defocus(self, ctx: PluginAppContext) -> None:
        try:
            if self._workspace_widget is not None:
                fn = getattr(self._workspace_widget, "set_view_active", None)
                if callable(fn):
                    fn(False)
        except Exception:
            log.debug("Capture defocus update failed (best-effort)", exc_info=True)

    def create_workspace_widget(self, parent, ctx: PluginAppContext):
        from .ui.workspace import CaptureWorkspaceWidget

        widget = CaptureWorkspaceWidget(parent, theme=ctx.app.theme, app_ctx=ctx.app, service=self._service)
        self._workspace_widget = widget
        return widget

    def _cmd_start(self, payload: object) -> dict[str, object]:
        device: CameraDevice | None = None
        if isinstance(payload, dict):
            raw_id = payload.get("device_id")
            raw_kind = payload.get("device_kind")
            raw_index = payload.get("device_index")
            if raw_id is not None:
                try:
                    device_id = str(raw_id)
                except Exception:
                    device_id = ""
                kind = CameraKind.WEBCAM
                if isinstance(raw_kind, str) and raw_kind.strip().lower() == "realsense":
                    kind = CameraKind.REALSENSE
                device = CameraDevice(device_id=device_id, display_name=device_id, kind=kind)
            elif raw_index is not None:
                try:
                    idx = int(raw_index)
                except Exception:
                    idx = 0
                device = CameraDevice(
                    device_id=f"cv_{idx}",
                    display_name=f"[CV] Webcam {idx}",
                    kind=CameraKind.WEBCAM,
                    device_index=idx,
                )

        started = self._service.start_async(device=device)
        return {"ok": bool(started), "timestamp_s": time.time()}

    def _cmd_stop(self) -> dict[str, object]:
        self._service.stop_async()
        return {"ok": True, "timestamp_s": time.time()}


def get_plugin() -> CapturePlugin:
    return CapturePlugin()


__all__ = ["CapturePlugin", "get_plugin"]
