from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QCheckBox, QLabel, QVBoxLayout, QWidget

from datalens.domain.system.ui import LoaderUiSettings
from datalens.services.settings_store import default_debounced_settings_writer, default_settings_store


class LoaderPreferencesPage(QWidget):
    """
    Preferences page: Loader.

    Controls what gets mirrored into the loader dialog while long-running work
    is running (without changing what is written to the log file).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = default_settings_store()
        self._writer = default_debounced_settings_writer()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Loader")
        title.setObjectName("PreferencesTitle")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(title)

        settings = self._store.load()
        ui: LoaderUiSettings = getattr(settings, "loader_ui", LoaderUiSettings())

        group = QGroupBox("Messages shown in the loader dialog", self)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(12, 10, 12, 12)
        group_layout.setSpacing(8)

        self._show_ctx = QCheckBox("Show task messages (ctx.log)", group)
        self._show_ctx.setChecked(bool(ui.show_ctx_messages))
        group_layout.addWidget(self._show_ctx)

        self._show_progress = QCheckBox("Show progress messages (log.progress / extra={'progress': True})", group)
        self._show_progress.setChecked(bool(ui.show_log_progress))
        group_layout.addWidget(self._show_progress)

        self._show_info = QCheckBox("Also show INFO logs", group)
        self._show_info.setChecked(bool(ui.show_log_info))
        group_layout.addWidget(self._show_info)

        self._show_warning = QCheckBox("Also show WARNING logs", group)
        self._show_warning.setChecked(bool(ui.show_log_warning))
        group_layout.addWidget(self._show_warning)

        self._show_error = QCheckBox("Also show ERROR logs", group)
        self._show_error.setChecked(bool(ui.show_log_error))
        group_layout.addWidget(self._show_error)

        self._show_critical = QCheckBox("Also show CRITICAL logs", group)
        self._show_critical.setChecked(bool(ui.show_log_critical))
        group_layout.addWidget(self._show_critical)

        hint = QLabel(
            "Tip: keep INFO/WARNING/ERROR mirroring disabled unless you are debugging a slow loader.\n"
            "Use log.progress(...) for user-facing status lines.",
            group,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px;")
        group_layout.addWidget(hint)

        layout.addWidget(group)
        layout.addStretch(1)

        for box in (
            self._show_ctx,
            self._show_progress,
            self._show_info,
            self._show_warning,
            self._show_error,
            self._show_critical,
        ):
            box.stateChanged.connect(self._persist)  # type: ignore[arg-type]

    def _persist(self) -> None:
        ui = LoaderUiSettings(
            show_ctx_messages=bool(self._show_ctx.isChecked()),
            show_log_progress=bool(self._show_progress.isChecked()),
            show_log_info=bool(self._show_info.isChecked()),
            show_log_warning=bool(self._show_warning.isChecked()),
            show_log_error=bool(self._show_error.isChecked()),
            show_log_critical=bool(self._show_critical.isChecked()),
        )

        def mutator(current):
            return replace(current, loader_ui=ui)

        self._writer.request_update(mutator)


__all__ = ["LoaderPreferencesPage"]

