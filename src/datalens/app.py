from __future__ import annotations

import argparse
import sys

from datalens.infra.background.loader_context import LoaderContext
from datalens.services.config_service import load_settings


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
    ctx.set_progress(0.33)
    ctx.log("Preparing UI theme…")
    ctx.set_progress(0.66)
    ctx.log("Ready.")
    ctx.set_progress(1.0)
    return settings


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv
    args = _parse_args(argv)

    # Import Qt-dependent modules only after argument parsing so `--help` works
    # even in environments without Qt installed.
    from PySide6.QtCore import QTimer

    from datalens.infra.background.loader_runner import run_with_loader
    from datalens.ui.application import DatalensApplication
    from datalens.ui.main_window import MainWindow
    from datalens.ui.theme import AppTheme
    from datalens.ui.welcome_window import WelcomeWindow
    from datalens.services.project_service import attach_project, load_project

    theme = AppTheme()
    app = DatalensApplication(argv, theme=theme)

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
            print(f"Failed to open project: {exc}", file=sys.stderr)
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

    def show_welcome(settings) -> None:
        welcome = WelcomeWindow(theme=theme, settings=settings)
        app._welcome_window = welcome  # keep alive
        if not welcome.exec():
            app.exit(0)
            return
        updated = welcome.updated_settings()
        show_main(load_last_project=True, last_project_root=updated.last_project_root)

    def on_startup_done(result: object) -> None:
        settings = result
        try:
            from datalens.domain.settings import AppSettings

            if isinstance(settings, AppSettings):
                theme.set_opacity(settings.theme_opacity)

                if args.skip_welcome and settings.enabled_plugins:
                    show_main(
                        load_last_project=args.load_last_project,
                        last_project_root=settings.last_project_root,
                    )
                    return
        except Exception:
            pass

        show_welcome(settings)

    def on_startup_error(exc: Exception) -> None:
        # Minimal failure behavior for now: print and exit.
        print(f"Startup failed: {exc}", file=sys.stderr)
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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
