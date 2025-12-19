from __future__ import annotations

import threading
import time

from datalens.api.plugins import (
    BasePlugin,
    CapabilityProvider,
    CommandContext,
    GestureBindingSpec,
    GestureId,
    PluginAppContext,
    PluginFutureResult,
    PluginId,
    PluginProjectContext,
    RegisteredHandler,
    ShortcutCommandId,
    ShortcutCommandSpec,
    ShortcutPageSpec,
    ShortcutScope,
    ShortcutSectionSpec,
)
from datalens.core.logging import bind_log_context, get_logger


log = get_logger(__name__)


class _CounterCapability:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = 0

    def get(self) -> int:
        with self._lock:
            return int(self._value)

    def increment(self, amount: int = 1) -> int:
        with self._lock:
            self._value += int(amount)
            return int(self._value)


class WidgetTestPlugin(BasePlugin):
    """Plugin runtime entrypoint for `widget test`.

    Notes for plugin authors:
    - All hooks run on the caller thread (typically a background loader stage).
      Keep hooks fast; schedule heavy work to background systems (DB/IoWriter/threadpool).
    - Do not touch Qt widgets from background threads. Only mutate UI on the Qt thread.
    - Project hooks may be called with no UI focus (headless service behavior).

    Hook order (typical):
    - `on_load` once per app run when enabled
    - (optional) `on_project_migrate` then `on_project_opened` when a project is opened
    - `on_project_closing` on close/switch (return Futures for flush waits)
    - `on_unload` when disabled or app exits

    Workspace plugins (kind=`workspace`) may also receive:
    - `on_defocus` then `on_focus` when switching active workspaces
    """

    def __init__(self) -> None:
        self._counter = _CounterCapability()

    @property
    def plugin_id(self) -> PluginId:
        return PluginId('widget_test')

    def on_load(self, ctx: PluginAppContext) -> None:
        """App-scope setup.

        Do lightweight registration only (menus, actions, capability providers).
        Avoid blocking I/O and long computations here.
        """
        ctx.app.capabilities.register(
            CapabilityProvider(
                capability_id="widget_test.counter",
                provider=self._counter,
                owner_plugin_id=self.plugin_id,
                description="Shared counter demo capability (widget_test).",
            ),
            replace_owner=True,
        )

        def echo_cmd(command_ctx: CommandContext) -> object:
            return {"echo": command_ctx.payload, "caller_plugin_id": str(command_ctx.caller_plugin_id or "")}

        def increment_cmd(command_ctx: CommandContext) -> object:
            amount = 1
            try:
                amount = int(command_ctx.payload) if command_ctx.payload is not None else 1
            except Exception:
                amount = 1
            return {"counter": self._counter.increment(amount), "amount": amount}

        def get_counter_cmd(command_ctx: CommandContext) -> object:
            return {"counter": self._counter.get()}

        ctx.app.commands.register(
            RegisteredHandler(
                command_id="widget_test.echo",
                handler=echo_cmd,
                owner_plugin_id=self.plugin_id,
                description="Echo payload for command bus demo.",
            ),
            replace=True,
        )
        ctx.app.commands.register(
            RegisteredHandler(
                command_id="widget_test.counter.increment",
                handler=increment_cmd,
                owner_plugin_id=self.plugin_id,
                description="Increment widget_test counter.",
            ),
            replace=True,
        )
        ctx.app.commands.register(
            RegisteredHandler(
                command_id="widget_test.counter.get",
                handler=get_counter_cmd,
                owner_plugin_id=self.plugin_id,
                description="Get widget_test counter.",
            ),
            replace=True,
        )

        return None

    def on_unload(self, ctx: PluginAppContext) -> None:
        """App-scope teardown.

        Disconnect signals/actions and stop app-scoped services started in `on_load`.
        """
        return None

    def on_focus(self, ctx: PluginAppContext) -> None:
        """Called when this workspace becomes active in the UI."""
        return None

    def on_defocus(self, ctx: PluginAppContext) -> None:
        """Called when this workspace is no longer active in the UI."""
        return None

    def register_shortcuts(self, ctx: PluginAppContext) -> None:
        """
        Declare a minimal shortcuts page for testing the shortcuts system.

        These bindings are workspace-scoped: they only fire when the Widget Test
        workspace is active (focused) in the current top-level window.
        """
        page = ShortcutPageSpec(
            page_id="widget_test",
            title="Widget Test",
            sections=(
                ShortcutSectionSpec(
                    section_id="debug",
                    title="Debug",
                    commands=(
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("log_hello"),
                            title="Log a test message",
                            description="Emits a log line to confirm shortcut dispatch.",
                            default_chord="Ctrl+Shift+H",
                            scope=ShortcutScope.WORKSPACE,
                        ),
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("run_count_10"),
                            title="Run loader: count to 10",
                            description="Opens a loader dialog and counts to 10 (mixes ctx.log and log.progress).",
                            default_chord="Ctrl+Shift+T",
                            scope=ShortcutScope.WORKSPACE,
                            consume_event=False,
                        ),
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("blocked_in_text"),
                            title="Blocked in text inputs",
                            description="Should NOT fire while typing in a text input (tests allow_in_text_inputs).",
                            default_chord="Ctrl+Shift+B",
                            scope=ShortcutScope.WORKSPACE,
                            allow_in_text_inputs=False,
                        ),
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("allowed_in_text"),
                            title="Allowed in text inputs",
                            description="Should fire while typing in a text input (tests allow_in_text_inputs).",
                            default_chord="Ctrl+Shift+I",
                            scope=ShortcutScope.WORKSPACE,
                            allow_in_text_inputs=True,
                        ),
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("multi_modifier"),
                            title="Multi-modifier keyboard chord",
                            description="Tests Ctrl+Alt+Shift combinations.",
                            default_chord="Ctrl+Alt+Shift+M",
                            scope=ShortcutScope.WORKSPACE,
                        ),
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("hold_toggle_demo"),
                            title="Hold/Toggle demo (widget-handled)",
                            description=(
                                "A stateful command handled by the focused widget: Hold keeps it active while pressed; "
                                "Toggle persists until pressed again (configured in Preferences)."
                            ),
                            default_chord="Ctrl+Shift+O",
                            scope=ShortcutScope.WORKSPACE,
                            dispatch_globally=False,
                            mode_toggle_default=False,
                            consume_event=True,
                        ),
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("hold_toggle_demo_toggle_default"),
                            title="Hold/Toggle demo (toggle default)",
                            description="Same as Hold/Toggle demo, but the default mode is Toggle.",
                            default_chord="Ctrl+Shift+Y",
                            scope=ShortcutScope.WORKSPACE,
                            dispatch_globally=False,
                            mode_toggle_default=True,
                            consume_event=True,
                        ),
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("conflict_a"),
                            title="Conflict demo A",
                            description="Deliberate conflict: shares the same default chord as Conflict demo B.",
                            default_chord="Ctrl+Shift+C",
                            scope=ShortcutScope.WORKSPACE,
                        ),
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("conflict_b"),
                            title="Conflict demo B",
                            description="Deliberate conflict: shares the same default chord as Conflict demo A.",
                            default_chord="Ctrl+Shift+C",
                            scope=ShortcutScope.WORKSPACE,
                        ),
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("mouse_demo"),
                            title="Mouse chord demo",
                            description="Tests mouse chord dispatch in an opt-in widget subtree.",
                            default_chord="Alt+RightClick",
                            scope=ShortcutScope.WORKSPACE,
                            consume_event=False,
                        ),
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("wheel_demo"),
                            title="Wheel chord demo",
                            description="Tests wheel chord dispatch in an opt-in widget subtree.",
                            default_chord="Ctrl+WheelUp",
                            scope=ShortcutScope.WORKSPACE,
                            consume_event=False,
                        ),
                        ShortcutCommandSpec(
                            command_id=ShortcutCommandId("consume_click"),
                            title="Consume-event mouse chord",
                            description="Ctrl+LeftClick should be consumed (click counter should not increment).",
                            default_chord="Ctrl+LeftClick",
                            scope=ShortcutScope.WORKSPACE,
                            consume_event=True,
                        ),
                    ),
                    gestures=(
                        GestureBindingSpec(
                            gesture_id=GestureId("shift_drag"),
                            title="Shift + LeftDrag (begin chord)",
                            description="Begin chord for the gesture demo panel (press Shift and drag).",
                            begin_chord="Shift+LeftClick",
                            scope=ShortcutScope.WORKSPACE,
                            consume_event=False,
                        ),
                    ),
                ),
            ),
        )
        ctx.app.shortcuts.register_page(
            plugin_id=self.plugin_id,
            plugin_name=ctx.plugin.name,
            page=page,
            callbacks={
                "log_hello": self._shortcut_log_hello,
                "run_count_10": self._shortcut_run_count_10,
                "blocked_in_text": self._shortcut_blocked_in_text,
                "allowed_in_text": self._shortcut_allowed_in_text,
                "multi_modifier": self._shortcut_multi_modifier,
                "mouse_demo": self._shortcut_mouse_demo,
                "wheel_demo": self._shortcut_wheel_demo,
                "consume_click": self._shortcut_consume_click,
                "conflict_a": self._shortcut_conflict_a,
                "conflict_b": self._shortcut_conflict_b,
            },
        )

    def _shortcut_log_hello(self) -> None:
        with bind_log_context(plugin_id=str(self.plugin_id), operation="shortcuts", phase="invoke"):
            log.info("Widget Test shortcut fired")

    def _shortcut_run_count_10(self) -> None:
        """
        Shortcut callback: run a background count-to-10 task under a loader dialog.

        This intentionally mixes:
        - `ctx.log(...)` (explicit loader context messages)
        - `log.progress(...)` (optional UX mirroring into the loader dialog)
        """
        try:
            from PySide6.QtWidgets import QApplication

            parent = QApplication.activeWindow()
        except Exception:
            parent = None

        from datalens.infra.background.loader_context import LoaderContext
        from datalens.infra.background.loader_runner import run_with_loader

        def task(ctx: LoaderContext) -> object:
            for i in range(1, 11):
                ctx.raise_if_cancelled()
                msg = f"Count {i}/10"
                ctx.log(msg)
                log.progress(msg, value=i / 10.0)
                ctx.set_progress(i / 10.0)
                time.sleep(0.2)
            return None

        with bind_log_context(plugin_id=str(self.plugin_id), operation="shortcut_loader", op_id="count10"):
            run_with_loader(
                parent=parent,
                title="Widget Test: Counting...",
                task=task,
                dialog_options={
                    "cancelable": True,
                    "max_messages": 6,
                    "log_context": {"plugin_id": str(self.plugin_id), "operation": "shortcut_loader", "op_id": "count10"},
                },
            )

    def _shortcut_blocked_in_text(self) -> None:
        with bind_log_context(plugin_id=str(self.plugin_id), operation="shortcuts", phase="blocked_in_text"):
            log.info("Blocked-in-text shortcut fired (this should NOT happen if a text input is focused).")

    def _shortcut_allowed_in_text(self) -> None:
        with bind_log_context(plugin_id=str(self.plugin_id), operation="shortcuts", phase="allowed_in_text"):
            log.info("Allowed-in-text shortcut fired (OK even if a text input is focused).")

    def _shortcut_multi_modifier(self) -> None:
        with bind_log_context(plugin_id=str(self.plugin_id), operation="shortcuts", phase="multi_modifier"):
            log.info("Multi-modifier shortcut fired.")

    def _shortcut_mouse_demo(self) -> None:
        with bind_log_context(plugin_id=str(self.plugin_id), operation="shortcuts", phase="mouse_demo"):
            log.info("Mouse chord shortcut fired.")

    def _shortcut_wheel_demo(self) -> None:
        with bind_log_context(plugin_id=str(self.plugin_id), operation="shortcuts", phase="wheel_demo"):
            log.info("Wheel chord shortcut fired.")

    def _shortcut_consume_click(self) -> None:
        with bind_log_context(plugin_id=str(self.plugin_id), operation="shortcuts", phase="consume_click"):
            log.info("Consume-event mouse chord fired (event should be consumed).")

    def _shortcut_conflict_a(self) -> None:
        with bind_log_context(plugin_id=str(self.plugin_id), operation="shortcuts", phase="conflict_a"):
            log.info("Conflict demo A fired")

    def _shortcut_conflict_b(self) -> None:
        with bind_log_context(plugin_id=str(self.plugin_id), operation="shortcuts", phase="conflict_b"):
            log.info("Conflict demo B fired")

    def create_workspace_widget(self, parent, ctx: PluginAppContext):
        """
        Create the workspace widget for this plugin.

        This is called on the Qt UI thread when the workspace becomes visible.
        Keep widget construction reasonably fast; offload heavy work to services.
        """
        from .ui.workspace import WorkspaceWidget

        return WorkspaceWidget(theme=ctx.app.theme, parent=parent)

    def on_project_migrate(self, ctx: PluginProjectContext) -> PluginFutureResult:
        """Project-scope DB migrations (runs before `on_project_opened`)."""
        return ctx.db.plugin_meta_set(plugin_version=ctx.plugin.version, schema_version=1)

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        """Project-scope setup.

        Start watchers/pipelines and restore state from `ctx.db.kv_get(...)`.
        """
        return None

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        """Project-scope teardown.

        Stop pipelines and return Futures representing flush/shutdown work so core can await them.
        """
        # Close/flush policy simulation for Task 2 hardening:
        # allow the widget test workspace to inject a delay/failure/timeout into
        # the project close path so we can validate the warn/retry/force-close UX.
        try:
            state = ctx.app.plugin_state.handle_for(self.plugin_id)
            enabled = bool(state.get("test.project_close.enabled") or False)
            mode = str(state.get("test.project_close.mode") or "off")
            delay_s = float(state.get("test.project_close.delay_seconds") or 0.0)
        except Exception:
            enabled = False
            mode = "off"
            delay_s = 0.0

        if not enabled or mode in {"off", "disabled"}:
            return None

        from concurrent.futures import Future
        import threading

        fut: Future[object] = Future()

        def run() -> None:
            try:
                if delay_s > 0:
                    time.sleep(max(0.0, delay_s))
                if mode == "fail":
                    raise RuntimeError("WidgetTest: intentional close-hook failure")
                if mode == "hang":
                    # Never complete: used to test timeout behavior.
                    while True:
                        time.sleep(3600)
                fut.set_result(object())
            except Exception as exc:
                fut.set_exception(exc)

        with bind_log_context(plugin_id=str(self.plugin_id), operation="widget_test_close_hook", phase=mode):
            log.info(
                "Project close hook armed",
                extra={"mode": mode, "delay_s": delay_s},
            )
        threading.Thread(target=run, name="WidgetTest(close_hook)", daemon=True).start()
        return fut


def get_plugin() -> BasePlugin:
    return WidgetTestPlugin()
