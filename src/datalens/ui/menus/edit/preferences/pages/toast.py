from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from datalens.domain.system.ui import ToastKind, ToastTypeUiVisibility, ToastUiSettings
from datalens.services.settings_store import default_debounced_settings_writer, default_settings_store


class ToastPreferencesPage(QWidget):
    """
    Preferences page: Toast.

    Controls when toast notifications are allowed to appear.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = default_settings_store()
        self._writer = default_debounced_settings_writer()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Toast")
        title.setObjectName("PreferencesTitle")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(title)

        settings = self._store.load()
        ui: ToastUiSettings = getattr(settings, "toast_ui", ToastUiSettings())

        group = QGroupBox("Visibility rules", self)
        grid = QGridLayout(group)
        grid.setContentsMargins(12, 10, 12, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        headers = [
            ("Success", ToastKind.SUCCESS),
            ("Warning", ToastKind.WARNING),
            ("Error", ToastKind.ERROR),
            ("Info", ToastKind.INFO),
        ]

        grid.addWidget(QLabel("", group), 0, 0)  # corner
        for col, (label, _) in enumerate(headers, start=1):
            h = QLabel(label, group)
            h.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            h.setStyleSheet("font-weight: 700;")
            grid.addWidget(h, 0, col)

        self._minimized_boxes: dict[ToastKind, QCheckBox] = {}
        self._inactive_boxes: dict[ToastKind, QCheckBox] = {}

        def row_label(text: str, row: int) -> None:
            lbl = QLabel(text, group)
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            grid.addWidget(lbl, row, 0)

        row_label("Show when minimized", 1)
        row_label("Show when hidden (behind other windows)", 2)

        for col, (_, kind) in enumerate(headers, start=1):
            policy = ui.for_kind(kind)

            show_min = QCheckBox(group)
            show_min.setChecked(bool(policy.show_when_minimized))
            show_min.setToolTip("Allow this toast type to appear while the main window is minimized.")
            grid.addWidget(show_min, 1, col, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
            self._minimized_boxes[kind] = show_min

            show_inactive = QCheckBox(group)
            show_inactive.setChecked(bool(policy.show_when_inactive))
            show_inactive.setToolTip(
                "Allow this toast type to appear while the main window is not the active window."
            )
            grid.addWidget(show_inactive, 2, col, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
            self._inactive_boxes[kind] = show_inactive

        hint = QLabel(
            "Tip: When disabled, new toasts are queued and existing toasts are hidden until the window becomes eligible again.\n"
            "Hidden toasts still expire on their normal timers.\n"
            "Hidden uses whether the main window is the active window (focus).",
            group,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px;")
        grid.addWidget(hint, 3, 0, 1, 5)

        layout.addWidget(group)
        layout.addStretch(1)

        for kind in ToastKind:
            self._minimized_boxes[kind].stateChanged.connect(self._persist)  # type: ignore[arg-type]
            self._inactive_boxes[kind].stateChanged.connect(self._persist)  # type: ignore[arg-type]

    def _persist(self) -> None:
        def policy_for(kind: ToastKind) -> ToastTypeUiVisibility:
            return ToastTypeUiVisibility(
                show_when_minimized=bool(self._minimized_boxes[kind].isChecked()),
                show_when_inactive=bool(self._inactive_boxes[kind].isChecked()),
            )

        toast_ui = ToastUiSettings(
            success=policy_for(ToastKind.SUCCESS),
            warning=policy_for(ToastKind.WARNING),
            error=policy_for(ToastKind.ERROR),
            info=policy_for(ToastKind.INFO),
        )

        def mutator(current):
            return replace(current, toast_ui=toast_ui)

        self._writer.request_update(mutator)

        # Best-effort: apply immediately to the ToastManager singleton.
        try:
            from datalens.ui.widgets.notifications.toast_manager import ToastManager

            ToastManager.get_instance().apply_ui_settings(toast_ui)
        except Exception:
            pass


__all__ = ["ToastPreferencesPage"]
