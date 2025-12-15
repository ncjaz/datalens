from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from datalens.core.logging import get_logger, init_logging
from datalens.infra.background.loader_context import LoaderContext
from datalens.services.config_service import load_settings
from datalens.services.plugins import PluginDiscoveryResult, discover_plugins


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
    return parser.parse_args(argv[1:])


def _startup_task(ctx: LoaderContext) -> object:
    """
    Minimal startup task run in a background thread.

    Keep this light for now: the primary goal is to prove the non-blocking
    loader UX. Heavy systems (plugins/services) should be added later.
    """
    ctx.log("Starting DataLens…")
    ctx.log("Loading settings…")
    settings = load_settings()
    ctx.set_progress(0.25)

    ctx.log("Discovering plugins…")
    plugin_discovery = discover_plugins()
    ctx.set_progress(0.60)
    ctx.log(f"Found {len(plugin_discovery.registry.all())} plugins.")
    if plugin_discovery.issues:
        ctx.log(f"{len(plugin_discovery.issues)} plugin discovery issues (see logs).")

    ctx.set_progress(0.75)
    ctx.log("Preparing UI theme…")
    ctx.set_progress(0.90)
    ctx.log("Ready.")
    ctx.set_progress(1.0)
    return StartupResult(settings=settings, plugin_discovery=plugin_discovery)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv
    args = _parse_args(argv)
    init_logging()
    log = get_logger(__name__)

    # Import Qt-dependent modules only after argument parsing so `--help` works
    # even in environments without Qt installed.
    from PySide6.QtCore import QTimer

    from datalens.infra.background.loader_runner import run_with_loader
    from datalens.services.plugins.host import PluginHost
    from datalens.ui.application import DatalensApplication
    from datalens.ui.main_window import MainWindow
    from datalens.ui.theme import AppTheme
    from datalens.ui.welcome_window import WelcomeWindow
    from datalens.services.project_service import attach_project, load_project

    theme = AppTheme()
    app = DatalensApplication(argv, theme=theme)
    plugin_host: PluginHost | None = None

    def show_main(*, load_last_project: bool, last_project_root: object | None) -> None:
        def show_main_window() -> None:
            main_window = MainWindow()
            main_window.show()
            app._main_window = main_window  # keep alive

        if not (load_last_project and last_project_root):
            show_main_window()
            return

        def open_project_task(ctx: LoaderContext) -> object:
            ctx.log("Opening project...")
            project = load_project(last_project_root, io=app.app_context.io)
            if plugin_host is not None:
                try:
                    current_hook = "on_project_migrate"
                    ctx.log("Running plugin migrations...")
                    migrate_futures = plugin_host.on_project_migrate(app_ctx=app.app_context, project=project)
                    for fut in migrate_futures:
                        fut.result(timeout=60.0)

                    current_hook = "on_project_opened"
                    ctx.log("Initializing plugins...")
                    plugin_host.on_project_opened(app_ctx=app.app_context, project=project)
                except Exception as exc:
                    log.exception(
                        "Plugin project open hook failed",
                        extra={"operation": "plugin_hook", "hook": current_hook, "phase": "error"},
                    )
                    ctx.log(f"Plugin project open failed: {exc}")
                    raise
            ctx.set_progress(1.0)
            return project

        def on_project_opened(project: object) -> None:
            try:
                from datalens.core.context import ProjectContext

                if isinstance(project, ProjectContext):
                    attach_project(app.app_context, project)
            finally:
                show_main_window()

        def on_project_open_error(exc: Exception) -> None:
            log.error("Failed to open project: %s", exc)
            show_main_window()

        run_with_loader(
            parent=None,
            title="Opening Project...",
            task=open_project_task,
            on_result=on_project_opened,
            on_error=on_project_open_error,
            dialog_options={
                "spinner_size": 80,
                "title_point_size": 18,
                "subtitle_point_size": 12,
            },
        )

    def show_welcome(settings, plugins) -> None:
        welcome = WelcomeWindow(theme=theme, settings=settings, plugins=plugins)
        app._welcome_window = welcome  # keep alive
        if not welcome.exec():
            app.exit(0)
            return
        updated = welcome.updated_settings()

        def enable_plugins_task(ctx: LoaderContext) -> object:
            if plugin_host is None:
                return None
            ctx.log("Enabling selected plugins…")
            plugin_host.enable(app_ctx=app.app_context, plugin_ids=set(updated.enabled_plugins))
            ctx.set_progress(1.0)
            return None

        run_with_loader(
            parent=None,
            title="Loading Plugins…",
            task=enable_plugins_task,
            on_result=lambda _: show_main(load_last_project=True, last_project_root=updated.last_project_root),
            on_error=lambda exc: show_main(load_last_project=True, last_project_root=updated.last_project_root),
            dialog_options={
                "spinner_size": 80,
                "title_point_size": 18,
                "subtitle_point_size": 12,
            },
        )

    def on_startup_done(result: object) -> None:
        nonlocal plugin_host
        if isinstance(result, StartupResult):
            settings = result.settings
            plugins = tuple(r.definition for r in result.plugin_discovery.registry.all())
            plugin_host = PluginHost(result.plugin_discovery.registry)
            app.app_context.plugin_host = plugin_host
        else:
            settings = result
            plugins = ()
        try:
            from datalens.domain.settings import AppSettings

            if isinstance(settings, AppSettings):
                theme.set_opacity(settings.theme_opacity)

                if args.skip_welcome and settings.enabled_plugins:
                    def enable_plugins_task(ctx: LoaderContext) -> object:
                        if plugin_host is None:
                            return None
                        ctx.log("Enabling selected plugins…")
                        plugin_host.enable(app_ctx=app.app_context, plugin_ids=set(settings.enabled_plugins))
                        ctx.set_progress(1.0)
                        return None

                    run_with_loader(
                        parent=None,
                        title="Loading Plugins…",
                        task=enable_plugins_task,
                        on_result=lambda _: show_main(
                            load_last_project=args.load_last_project,
                            last_project_root=settings.last_project_root,
                        ),
                        on_error=lambda exc: show_main(
                            load_last_project=args.load_last_project,
                            last_project_root=settings.last_project_root,
                        ),
                        dialog_options={
                            "spinner_size": 80,
                            "title_point_size": 18,
                            "subtitle_point_size": 12,
                        },
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
            title="Launching DataLens…",
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
        app.app_context.io.close(flush=True, timeout_seconds=5.0)
    except Exception:
        pass
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
