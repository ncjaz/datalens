from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QWidget,
)

from datalens.core.logging import get_logger
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton


@dataclass(frozen=True, slots=True)
class FileTreeCounts:
    files: int
    dirs: int


class _WatchdogBridge(QObject):
    event_received = Signal(str, str, bool)
    counts_updated = Signal(int, int)


def _scan_counts(root: Path) -> FileTreeCounts:
    file_count = 0
    dir_count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dir_count += len(dirnames)
        file_count += len(filenames)
    return FileTreeCounts(files=file_count, dirs=dir_count)


class FileWatcherPanel(QWidget):
    """
    Test panel: watchdog-backed recursive file watching with live counts.

    This exercises the intended "watchdog thread -> marshal to UI -> debounce/rescan"
    shape we want for ProjectFileWatcher later, without being coupled to projects.
    """

    def __init__(self, *, theme: AppTheme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._log = get_logger("datalens.plugins.widget_test.file_watcher")
        self._disposed = False
        self._in_automated_tests = bool(os.environ.get("PYTEST_CURRENT_TEST")) or os.environ.get("DATALENS_TESTING") == "1"

        self._bridge = _WatchdogBridge()
        self._bridge.event_received.connect(self._on_event_received)
        self._bridge.counts_updated.connect(self._on_counts_updated)

        self._observer = None
        self._stop = threading.Event()
        self._dirty = threading.Event()
        self._scan_thread: threading.Thread | None = None

        self._event_count = 0
        self._last_event = "-"
        self._counts = FileTreeCounts(files=0, dirs=0)

        box = QGroupBox("File watcher (watchdog) — live counts", self)
        box.setStyleSheet("QGroupBox { font-weight: 700; }")
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        root = QGridLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(box)

        layout = QGridLayout(box)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        help_text = QLabel(
            "Pick a folder, press Start, then add/remove files and folders in that tree.\n"
            "Counts update in real-time (debounced rescan on events).",
            box,
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
        layout.addWidget(help_text, 0, 0, 1, 4)

        self._path_edit = QLineEdit(box)
        self._path_edit.setPlaceholderText("Folder to watch…")
        self._path_edit.setText(str(self._default_path()))

        browse = DatalensButton("Browse…", theme, ButtonVariant.SECONDARY, box)
        browse.clicked.connect(self._browse)

        self._start = DatalensButton("Start", theme, ButtonVariant.CONFIRM, box)
        self._start.clicked.connect(self.start_watching)
        self._stop_btn = DatalensButton("Stop", theme, ButtonVariant.CANCEL, box)
        self._stop_btn.clicked.connect(self.stop_watching)
        self._stop_btn.setEnabled(False)
        self._cycle_btn = DatalensButton("Cycle x10", theme, ButtonVariant.SECONDARY, box)
        self._cycle_btn.clicked.connect(self._cycle_start_stop)

        layout.addWidget(QLabel("Path:", box), 1, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._path_edit, 1, 1)
        layout.addWidget(browse, 1, 2)
        layout.addWidget(self._start, 1, 3)
        layout.addWidget(self._stop_btn, 1, 4)
        layout.addWidget(self._cycle_btn, 1, 5)

        self._files_label = QLabel("Files: 0", box)
        self._dirs_label = QLabel("Dirs: 0", box)
        self._events_label = QLabel("Events: 0", box)
        self._last_label = QLabel("Last: -", box)
        self._last_label.setWordWrap(True)

        for lbl in (self._files_label, self._dirs_label, self._events_label, self._last_label):
            lbl.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.90)}; font-size: 11px;")

        layout.addWidget(self._files_label, 2, 1)
        layout.addWidget(self._dirs_label, 2, 2)
        layout.addWidget(self._events_label, 2, 3)
        layout.addWidget(self._last_label, 3, 1, 1, 4)

        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(4, 0)
        layout.setColumnStretch(5, 0)

        self._apply_state()
        try:
            self.destroyed.connect(lambda *_: self._dispose())  # type: ignore[attr-defined]
        except Exception:
            pass

    def _dispose(self) -> None:
        """
        Best-effort shutdown used for lifecycle events (hide/close).

        Avoid touching UI widgets here; the panel may be in the middle of teardown.
        """
        if self._disposed:
            return
        self._disposed = True
        try:
            self._bridge.event_received.disconnect(self._on_event_received)
        except Exception:
            pass
        try:
            self._bridge.counts_updated.disconnect(self._on_counts_updated)
        except Exception:
            pass

        observer = self._observer
        self._observer = None
        self._stop.set()
        self._dirty.set()
        try:
            if observer is not None:
                observer.stop()
                observer.join(timeout=2.0)
        except Exception:
            pass
        try:
            if self._scan_thread is not None:
                self._scan_thread.join(timeout=1.0)
        except Exception:
            pass
        self._scan_thread = None

    def _default_path(self) -> Path:
        try:
            from datalens.infra.paths import datalens_user_data_dir

            return datalens_user_data_dir()
        except Exception:
            return Path.home()

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose folder to watch", self._path_edit.text())
        if directory:
            self._path_edit.setText(directory)

    def _apply_state(self) -> None:
        running = self._observer is not None
        try:
            self._path_edit.setEnabled(not running)
            self._start.setEnabled(not running)
            self._stop_btn.setEnabled(running)
            self._cycle_btn.setEnabled(not running)
        except RuntimeError:
            return

    def start_watching(self) -> None:
        if self._disposed:
            return
        if self._observer is not None:
            return
        if self._in_automated_tests:
            self._log.info(
                "File watcher suppressed during automated tests",
                extra={"operation": "file_watcher", "phase": "suppressed", "plugin_id": "widget_test"},
            )
            return
        root = Path(self._path_edit.text()).expanduser()
        if not root.exists() or not root.is_dir():
            QMessageBox.warning(self, "File watcher", "Please choose an existing folder.")
            return

        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except Exception as exc:
            QMessageBox.critical(self, "File watcher", f"watchdog is not available: {exc}")
            return

        self._stop.clear()
        self._dirty.set()
        self._event_count = 0
        self._last_event = "-"
        self._counts = FileTreeCounts(files=0, dirs=0)
        self._refresh_labels()

        bridge = self._bridge

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event) -> None:  # type: ignore[override]
                try:
                    bridge.event_received.emit(getattr(event, "event_type", "event"), str(event.src_path), bool(event.is_directory))
                except Exception:
                    return

        observer = Observer()
        observer.schedule(Handler(), str(root), recursive=True)
        observer.start()
        self._observer = observer

        self._scan_thread = threading.Thread(target=self._scan_loop, args=(root,), name="WidgetTestFileWatcherScan", daemon=True)
        self._scan_thread.start()

        self._log.info(
            "File watcher started",
            extra={"operation": "file_watcher", "phase": "start", "plugin_id": "widget_test", "path": str(root)},
        )
        self._apply_state()

    def stop_watching(self, *, update_ui: bool = True) -> None:
        observer = self._observer
        if observer is None:
            return
        self._observer = None
        self._stop.set()
        self._dirty.set()
        try:
            observer.stop()
            observer.join(timeout=2.0)
        except Exception:
            pass
        try:
            if self._scan_thread is not None:
                self._scan_thread.join(timeout=1.0)
        except Exception:
            pass
        self._scan_thread = None
        if update_ui:
            self._apply_state()
        self._log.info(
            "File watcher stopped",
            extra={"operation": "file_watcher", "phase": "stop", "plugin_id": "widget_test"},
        )

    def _cycle_start_stop(self) -> None:
        """
        Leak/lifecycle test: start/stop the watcher repeatedly and confirm we
        don't leave our scan thread running.
        """
        if self._in_automated_tests:
            self._log.info(
                "File watcher cycle suppressed during automated tests",
                extra={"operation": "file_watcher", "phase": "cycle_suppressed", "plugin_id": "widget_test"},
            )
            return
        root = Path(self._path_edit.text()).expanduser()
        if not root.exists() or not root.is_dir():
            QMessageBox.warning(self, "File watcher", "Please choose an existing folder.")
            return
        cycles = 10
        self._cycle_btn.setEnabled(False)
        self._event_count = 0
        self._events_label.setText("Events: 0")
        self._last_label.setText("Last: (cycling…)")  # type: ignore[arg-type]

        def step(i: int) -> None:
            if self._disposed or not self.isVisible():
                return
            if i >= cycles:
                leftovers = 0
                try:
                    if self._scan_thread is not None and self._scan_thread.is_alive():
                        leftovers += 1
                except Exception:
                    pass
                self._cycle_btn.setEnabled(True)
                QMessageBox.information(
                    self,
                    "File watcher",
                    f"Cycle complete.\n\ncycles={cycles}\nscan_thread_alive={leftovers}",
                )
                self._log.info(
                    "File watcher cycle complete",
                    extra={"operation": "file_watcher", "phase": "cycle_done", "plugin_id": "widget_test", "cycles": cycles, "scan_thread_alive": leftovers},
                )
                return

            # start, then stop shortly after
            self.start_watching()
            def stop_then_continue() -> None:
                self.stop_watching(update_ui=True)
                QTimer.singleShot(120, self, lambda: step(i + 1))

            QTimer.singleShot(250, self, stop_then_continue)

        self._log.info(
            "File watcher cycle started",
            extra={"operation": "file_watcher", "phase": "cycle_start", "plugin_id": "widget_test", "cycles": cycles},
        )
        QTimer.singleShot(0, self, lambda: step(0))

    def _on_event_received(self, event_type: str, src_path: str, is_dir: bool) -> None:
        self._event_count += 1
        suffix = "dir" if is_dir else "file"
        self._last_event = f"{event_type}: {src_path} ({suffix})"
        self._events_label.setText(f"Events: {self._event_count}")
        self._last_label.setText(f"Last: {self._last_event}")
        self._dirty.set()

    def _scan_loop(self, root: Path) -> None:
        debounce_s = 0.25
        while not self._stop.is_set():
            self._dirty.wait(timeout=0.5)
            if self._stop.is_set():
                return
            if not self._dirty.is_set():
                continue
            self._dirty.clear()
            time.sleep(debounce_s)
            if self._stop.is_set():
                return
            try:
                counts = _scan_counts(root)
            except Exception:
                continue
            self._counts = counts
            try:
                self._bridge.counts_updated.emit(counts.files, counts.dirs)
            except Exception:
                pass

    def _refresh_labels(self) -> None:
        self._files_label.setText(f"Files: {self._counts.files}")
        self._dirs_label.setText(f"Dirs: {self._counts.dirs}")

    def _on_counts_updated(self, files: int, dirs: int) -> None:
        self._counts = FileTreeCounts(files=int(files), dirs=int(dirs))
        self._refresh_labels()

    def closeEvent(self, event) -> None:
        try:
            self.stop_watching(update_ui=False)
        except Exception:
            pass
        try:
            self._dispose()
        except Exception:
            pass
        super().closeEvent(event)

    def hideEvent(self, event) -> None:
        try:
            self.stop_watching(update_ui=False)
        except Exception:
            pass
        try:
            self._dispose()
        except Exception:
            pass
        super().hideEvent(event)


__all__ = ["FileWatcherPanel"]
