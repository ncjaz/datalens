from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QWidget

from datalens.ui.menus.menubar import DatalensMenuBar


class MainWindow(QMainWindow):
    """Minimal main application window placeholder."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DataLens")
        self.resize(1200, 800)
        self._close_in_progress = False

        menubar = DatalensMenuBar(self)
        menubar.newProjectRequested.connect(self._on_new_project_requested)
        self.setMenuBar(menubar)

        label = QLabel("Main Window (placeholder)")
        label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(label)

    def _on_new_project_requested(self) -> None:
        QMessageBox.information(self, "New Project", "New Project is not implemented yet.")

    def closeEvent(self, event) -> None:
        """
        Ensure project persistence flushes run off the UI thread on app close.

        This uses the shared loader infrastructure so the UI remains responsive
        while background flush/close work runs.
        """
        if self._close_in_progress:
            super().closeEvent(event)
            return

        try:
            app = QApplication.instance()
            app_ctx = getattr(app, "app_context", None) if app is not None else None
        except Exception:
            app_ctx = None

        # No active project: nothing to flush.
        if app_ctx is None or getattr(app_ctx, "active_project", None) is None:
            super().closeEvent(event)
            return

        event.ignore()
        self._close_in_progress = True

        from datalens.infra.background.loader_context import LoaderContext
        from datalens.infra.background.loader_runner import run_with_loader
        from datalens.services.project_service import close_project_blocking

        def task(ctx: LoaderContext) -> object:
            ctx.log("Flushing project...")
            close_project_blocking(app_ctx)
            ctx.log("Done.")
            return object()

        def on_done(_: object) -> None:
            self._close_in_progress = False
            QTimer.singleShot(0, self.close)

        def on_error(exc: Exception) -> None:
            self._close_in_progress = False
            QMessageBox.critical(self, "Failed to Close Project", str(exc))

        run_with_loader(
            parent=self,
            title="Closing Project...",
            task=task,
            on_result=on_done,
            on_error=on_error,
            dialog_options={"spinner_size": 80, "title_point_size": 18, "subtitle_point_size": 12},
        )
