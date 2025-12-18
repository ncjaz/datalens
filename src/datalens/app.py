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

    from datalens.infra.background.loader_runner import LoaderStage, run_with_loader, run_with_loader_sequence
    from datalens.services.plugins.runtime.host import PluginHost
    from datalens.ui.application import DatalensApplication
    from datalens.ui.main_window import MainWindow
    from datalens.ui.theme import AppTheme
    from datalens.ui.welcome_window import WelcomeWindow
    from datalens.services.project_service import open_project_with_plugins

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

        plugin_ids = set(enabled_plugin_ids or set())
        should_open_project = bool(load_last_project and last_project_root)

        if not plugin_ids and not should_open_project:
            return

        def open_project_task(ctx: LoaderContext) -> object:
            project = open_project_with_plugins(
                app_ctx=app.app_context,
                project_root=last_project_root,
                plugin_host=plugin_host,
                plugin_migrate_timeout_seconds=60.0,
                await_plugin_opened=False,
                progress=ctx.log,
            )
            ctx.set_progress(1.0)
            return project

        def on_project_opened(project: object) -> None:
            try:
                main_window.on_project_changed()
            except Exception:
                log.warning("Failed to update main window on project open (best-effort)", exc_info=True)

        def on_project_open_error(exc: Exception) -> None:
            log.error("Failed to open project: %s", exc)
            try:
                main_window.on_project_changed()
            except Exception:
                log.warning("Failed to update main window on project open error (best-effort)", exc_info=True)

        stages: list[LoaderStage] = []

        if plugin_ids:
            def enable_plugins_task(ctx: LoaderContext) -> object:
                if plugin_host is None:
                    return None
                try:
                    preview = ", ".join(sorted(str(pid) for pid in plugin_ids))
                    ctx.log(f"Enabling {len(plugin_ids)} plugin(s): {preview}")
                except Exception:
                    ctx.log("Enabling selected plugins...")
                plugin_host.set_enabled(app_ctx=app.app_context, plugin_ids=plugin_ids)
                ctx.set_progress(1.0)
                return None

            stages.append(LoaderStage(name="Enabling selected plugins...", task=enable_plugins_task, weight=1.0))

        if should_open_project:
            stages.append(LoaderStage(name="Opening project...", task=open_project_task, weight=3.0))

        def on_sequence_done(results: list[object]) -> None:
            # Plugins are enabled in background stages; once complete, re-dispatch
            # workspace focus so the visible workspace receives `on_focus`.
            try:
                main_window.on_plugins_enabled()
            except Exception:
                log.debug("Failed to dispatch plugin focus after enabling (best-effort)", exc_info=True)

            # If a project was opened, it will be the last non-None stage result.
            project: object | None = None
            for item in reversed(results):
                if item is not None:
                    project = item
                    break
            if project is None:
                try:
                    main_window.on_project_changed()
                except Exception:
                    log.warning("Failed to update main window after loader sequence (best-effort)", exc_info=True)
                return
            on_project_opened(project)

        run_with_loader_sequence(
            parent=main_window,
            title="Loading...",
            stages=stages,
            on_result=on_sequence_done,
            on_error=on_project_open_error,
            dialog_options={
                "spinner_size": 80,
                "title_point_size": 18,
                "subtitle_point_size": 12,
            },
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
