from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from datalens.core.logging import get_logger, init_logging
from datalens.infra.background.loader_context import LoaderContext
from datalens.services.config_service import load_settings
from datalens.services.plugins import PluginDiscoveryResult, discover_plugins
from datalens.services.plugins.registry import PluginRecord


@dataclass(frozen=True)
class StartupResult:
    settings: object
    plugin_discovery: PluginDiscoveryResult


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="datalens", add_help=True)
    parser.add_argument(
        "--skip-welcome",
        action="store_true",
        help="Skip the welcome screen and reuse last selected plugins.",
    )
    parser.add_argument(
        "--load-last-project",
        action="store_true",
        help="When skipping welcome, attempt to open the last project.",
    )
    parser.add_argument(
        "--slow-event-threshold-ms",
        type=float,
        default=None,
        help="Override slow Qt event warning threshold (0 disables; otherwise defaults to env/75ms).",
    )
    parser.add_argument(
        "--debug-ui",
        action="store_true",
        help="Dump UI diagnostics (top-level widgets + active QTimers) after startup.",
    )
    logging_group = parser.add_mutually_exclusive_group()
    logging_group.add_argument(
        "--log-to-file",
        dest="log_to_file",
        action="store_true",
        default=True,
        help="Enable logging to a rotating log file under the user data dir (default).",
    )
    logging_group.add_argument(
        "--no-log-file",
        dest="log_to_file",
        action="store_false",
        help="Disable file logging (stderr/console only).",
    )
    return parser.parse_args(argv[1:])


def _startup_task(ctx: LoaderContext) -> object:
    """
    Minimal startup task run in a background thread.

    Keep this light for now: the primary goal is to prove the non-blocking
    loader UX. Heavy systems (plugins/services) should be added later.
    """
    ctx.log("Starting DataLens...")

    # System specs: collect once at startup so diagnostics + plugins can gate
    # behavior without needing env vars/CLI switches. GPU probing can call
    # external tools, so keep it best-effort and time-bounded.
    try:
        from dataclasses import replace

        from datalens.core.context import get_app_context
        from datalens.services.system_info_service import collect_gpu_info_best_effort, collect_system_info_base

        app_ctx = get_app_context()
        current = app_ctx.workspace_state.snapshot().system_info
        base = current or collect_system_info_base()
        if not getattr(base, "gpu_probe_completed", False):
            ctx.log("Detecting system specs...")
            gpus = collect_gpu_info_best_effort(timeout_s=1.0)
            app_ctx.workspace_state.set_system_info(
                replace(base, gpus=tuple(gpus), gpu_probe_completed=True)
            )
    except Exception:
        # Best-effort diagnostics only; never block startup on this.
        get_logger(__name__).debug(
            "System specs probe failed during startup (best-effort)", exc_info=True
        )
    try:
        from datalens.infra.paths import settings_json_path

        ctx.log(f"Loading settings from: {settings_json_path()}")
    except Exception as exc:
        ctx.log(f"Loading settings... ({exc})")
    settings = load_settings()
    ctx.set_progress(0.25)

    ctx.log("Discovering plugins...")
    try:
        from datalens.infra.paths import datalens_user_data_dir
        from pathlib import Path

        user_data_root = getattr(settings, "user_data_dir", None) or datalens_user_data_dir()
        plugin_discovery = discover_plugins(user_plugins_root_dir=Path(user_data_root) / "plugins")
    except Exception:
        plugin_discovery = discover_plugins()

    try:
        plugin_discovery.registry.apply_definition_overrides(getattr(settings, "plugin_overrides", {}) or {})
    except Exception as exc:
        log = get_logger(__name__)
        log.warning(
            "Failed to apply plugin metadata overrides (best-effort): %s",
            exc,
            extra={"operation": "discover_plugins", "phase": "overrides_error"},
        )
    ctx.set_progress(0.60)
    ctx.log(f"Found {len(plugin_discovery.registry.all())} plugins.")
    if plugin_discovery.issues:
        ctx.log(f"{len(plugin_discovery.issues)} plugin discovery issues (see logs).")

    ctx.set_progress(0.75)
    ctx.log("Preparing UI theme...")
    ctx.set_progress(0.90)
    ctx.log("Ready.")
    ctx.set_progress(1.0)
    return StartupResult(settings=settings, plugin_discovery=plugin_discovery)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv
    args = _parse_args(argv)
    init_logging(log_to_file=bool(getattr(args, "log_to_file", True)))
    log = get_logger(__name__)

    # Import Qt-dependent modules only after argument parsing so `--help` works
    # even in environments without Qt installed.
    from PySide6.QtCore import QTimer

    from datalens.infra.background.loader_runner import run_with_loader
    from datalens.services.plugins.runtime.host import PluginHost
    from datalens.ui.application import DatalensApplication
    from datalens.ui.main_window import MainWindow
    from datalens.ui.theme import AppTheme
    from datalens.ui.welcome_window import WelcomeWindow
    from PySide6.QtWidgets import QMessageBox

    theme = AppTheme()
    app = DatalensApplication(argv, theme=theme, slow_event_threshold_ms=args.slow_event_threshold_ms)
    plugin_host: PluginHost | None = None
    plugin_records: tuple[PluginRecord, ...] = ()

    def show_main(
        *,
        load_last_project: bool,
        last_project_root: object | None,
        enabled_plugin_ids: set[str] | None = None,
        recent_projects: list[object] | None = None,
    ) -> None:
        from pathlib import Path

        main_window = MainWindow(
            recent_projects=[p for p in (recent_projects or []) if isinstance(p, Path)],
            plugins=list(plugin_records),
            enabled_plugin_ids=enabled_plugin_ids,
        )
        main_window.show()
        app._main_window = main_window  # keep alive
        if args.debug_ui:
            from datalens.ui.diagnostics.debug_tools import dump_active_timers, dump_top_level_widgets
            from datalens.core.logging import get_logger

            debug_log = get_logger("datalens.ui.debug")

            def dump() -> None:
                for line in dump_top_level_widgets():
                    debug_log.info("Top-level widget: %s", line, extra={"operation": "ui_debug", "phase": "widgets"})
                timers = dump_active_timers()
                debug_log.info(
                    "Active QTimers: %d",
                    len(timers),
                    extra={"operation": "ui_debug", "phase": "timers"},
                )
                for info in timers[:20]:
                    debug_log.info(
                        "QTimer interval=%sms single=%s (%s)",
                        info.interval_ms,
                        info.single_shot,
                        info.parent_chain,
                        extra={"operation": "ui_debug", "phase": "timers"},
                    )

            QTimer.singleShot(250, dump)

        # Delegate plugin enable + project open sequencing to the main window so
        # startup uses the same loader UX and policy as File->Open/Switch.
        main_window.startup_load(
            enabled_plugin_ids=enabled_plugin_ids,
            load_last_project=load_last_project,
            last_project_root=last_project_root,
        )

    def show_welcome(settings, plugins) -> None:
        welcome = WelcomeWindow(theme=theme, settings=settings, plugins=plugins)
        # Do not keep the welcome window alive after it closes; keeping hidden
        # widget trees around can contribute to sluggishness and hard-to-debug
        # event churn.
        if not welcome.exec():
            app.exit(0)
            return
        updated = welcome.updated_settings()
        try:
            # Apply user shortcut overrides immediately so subsequent plugin enable/open flows
            # use the latest bindings without requiring a restart.
            app.app_context.shortcuts.apply_settings(updated)
        except Exception:
            log.debug("Failed to apply shortcut settings (best-effort)", exc_info=True)
        try:
            # Keep plugin preferences cache warm so plugins/UI can query without disk IO.
            app.app_context.preferences.apply_settings(updated)
        except Exception:
            log.debug("Failed to apply plugin preferences settings (best-effort)", exc_info=True)
        selected_root = None
        try:
            selected_root = welcome.selected_project_root()
        except Exception:
            selected_root = None
        try:
            welcome.close()
            welcome.deleteLater()
        except Exception:
            log.debug("Failed to close welcome window cleanly (best-effort)", exc_info=True)

        show_main(
            load_last_project=True,
            last_project_root=selected_root,
            enabled_plugin_ids=set(updated.enabled_plugins),
            recent_projects=list(getattr(updated, "recent_projects", ()) or ()),
        )

    def on_startup_done(result: object) -> None:
        nonlocal plugin_host, plugin_records
        if isinstance(result, StartupResult):
            settings = result.settings
            plugin_records = tuple(result.plugin_discovery.registry.all())
            plugins = tuple(r.definition for r in plugin_records)
            plugin_host = PluginHost(result.plugin_discovery.registry)
            app.app_context.plugin_host = plugin_host
        else:
            # Defensive fallback: `_startup_task` currently always returns `StartupResult`,
            # but keep this branch so alternate startup tasks can return settings directly.
            settings = result
            plugins = ()
        try:
            from datalens.domain.system.settings import AppSettings

            if isinstance(settings, AppSettings):
                theme.set_opacity(settings.theme_opacity)
                theme.set_settings(getattr(settings, "theme_settings", theme.settings))
                try:
                    app.app_context.shortcuts.apply_settings(settings)
                except Exception:
                    log.debug("Failed to apply shortcut settings on startup (best-effort)", exc_info=True)
                try:
                    app.app_context.preferences.apply_settings(settings)
                except Exception:
                    log.debug("Failed to apply plugin preferences settings on startup (best-effort)", exc_info=True)

                if args.skip_welcome and settings.enabled_plugins:
                    show_main(
                        load_last_project=args.load_last_project,
                        last_project_root=settings.last_project_root,
                        enabled_plugin_ids=set(settings.enabled_plugins),
                        recent_projects=list(getattr(settings, "recent_projects", ()) or ()),
                    )
                    return
        except Exception as exc:
            log.exception("Error processing settings on startup", extra={"operation": "startup", "phase": "error"})

        show_welcome(settings, plugins)

    def on_startup_error(exc: Exception) -> None:
        # Minimal failure behavior for now: print and exit.
        log.error("Startup failed: %s", exc)
        app.exit(1)

    def run_startup() -> None:
        run_with_loader(
            parent=None,
            title="Launching DataLens...",
            task=_startup_task,
            on_result=on_startup_done,
            on_error=on_startup_error,
            dialog_options={
                "spinner_size": 120,
                "title_point_size": 24,
                "subtitle_point_size": 13,
            },
        )

    # Ensure the Qt event loop is running so the loader can paint immediately.
    QTimer.singleShot(0, run_startup)
    exit_code = app.exec()
    try:
        # Best-effort: flush debounced settings writes during shutdown.
        # This runs after the Qt event loop exits, so it will not impact UI responsiveness.
        from datalens.services.settings_store import default_debounced_settings_writer

        default_debounced_settings_writer().flush()
    except Exception:
        log.warning("Failed to flush settings writer on exit (best-effort)", exc_info=True)
    try:
        plugin_host = getattr(app.app_context, "plugin_host", None)
        if plugin_host is not None:
            plugin_host.shutdown(app_ctx=app.app_context)
    except Exception:
        log.warning("Failed to unload plugins on exit (best-effort)", exc_info=True)
    try:
        app.app_context.io.close(flush=True, timeout_seconds=5.0)
    except Exception:
        log.warning("Failed to close IoWriter on exit (best-effort)", exc_info=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
