from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from datalens.core.context import get_app_context
from datalens.core.events import EventHub, PluginPreferencesChanged
from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.domain.plugin.preferences_schema import PathKind, PluginPreferencesSchema, PreferenceField, PreferenceKind
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton
from datalens.ui.widgets.core.checkboxes import DatalensCheckBox
from datalens.ui.widgets.core.toggle import Toggle, ToggleOption
from datalens.ui.widgets.icons import reset_icon
from datalens.ui.widgets.layouts import auto_size_form_layout


log = get_logger(__name__)


@dataclass
class _ControlBinding:
    key: str
    read_value: Callable[[], object | None]
    write_value: Callable[[object], None]
    widget: QWidget


class PluginPreferencesPage(QWidget):
    """
    Preferences -> Plugins page (schema-driven).

    This page supports a "filter" mode so the Preferences dialog can use
    parent/child navigation without allocating one QWidget per plugin page.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filter_plugin_id: str | None = None
        self._bindings: dict[str, list[_ControlBinding]] = {}
        self._unsub: Callable[[], None] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QLabel("Plugin Preferences")
        header.setObjectName("PluginPreferencesHeader")
        header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        root.addWidget(header)

        subtitle = QLabel(
            "Plugin preferences are persisted in settings.json and can be edited even when a plugin is disabled."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("PluginPreferencesSubtitle")
        root.addWidget(subtitle)

        self._content = QWidget(self)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(12)
        self._content_layout.setAlignment(Qt.AlignTop)

        # The PreferencesDialog already wraps pages in a QScrollArea, but keep the
        # content widget separate so we can rebuild without replacing `self`.
        root.addWidget(self._content, 1)

        self._subscribe_events()
        self._rebuild()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            unsub = self._unsub
            self._unsub = None
            if callable(unsub):
                unsub()
        except Exception:
            pass
        super().closeEvent(event)

    def set_filter(self, filter_key: str | None) -> None:
        """
        Filter to a specific plugin id (child selection), or None to show all.
        """
        key = str(filter_key).strip() if filter_key else None
        if key == "":
            key = None
        if key == self._filter_plugin_id:
            return
        self._filter_plugin_id = key
        self._rebuild()

    def focus_item(self, filter_key: str) -> None:
        # For now, we rebuild with a filter (single plugin). Scrolling to an
        # item when showing "all" can be added later if needed.
        self.set_filter(filter_key)

    # ------------------------------------------------------------------
    # Internal: events + rebuild
    # ------------------------------------------------------------------

    def _subscribe_events(self) -> None:
        app_ctx = get_app_context()

        def on_changed(payload: object) -> None:
            if not isinstance(payload, PluginPreferencesChanged):
                return
            pid = str(payload.plugin_id)
            if self._filter_plugin_id is not None and pid != self._filter_plugin_id:
                return
            self._refresh_plugin_values(pid, set(payload.changed_keys))

        try:
            self._unsub = app_ctx.events.subscribe(EventHub.PLUGIN_PREFERENCES_CHANGED, on_changed).unsubscribe
        except Exception:
            self._unsub = None

    def _clear_content(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._bindings.clear()

    def _rebuild(self) -> None:
        self._clear_content()
        app_ctx = get_app_context()

        host = getattr(app_ctx, "plugin_host", None)
        registry = getattr(host, "registry", None) if host is not None else None
        if registry is None:
            msg = QLabel("Plugin registry is not available yet.")
            msg.setWordWrap(True)
            self._content_layout.addWidget(msg)
            return

        records = list(registry.all())
        if self._filter_plugin_id:
            records = [r for r in records if str(r.definition.id) == self._filter_plugin_id]

        if not records:
            msg = QLabel("No plugins found.")
            msg.setWordWrap(True)
            self._content_layout.addWidget(msg)
            return

        for record in sorted(records, key=lambda r: str(r.definition.name).lower()):
            self._content_layout.addWidget(self._build_plugin_panel(record.definition.id))

        self._content_layout.addStretch(1)

    # ------------------------------------------------------------------
    # UI builders
    # ------------------------------------------------------------------

    def _build_plugin_panel(self, plugin_id: PluginId) -> QWidget:
        app_ctx = get_app_context()
        host = getattr(app_ctx, "plugin_host", None)
        registry = getattr(host, "registry", None) if host is not None else None
        record = registry.get(PluginId(str(plugin_id))) if registry is not None else None  # type: ignore[union-attr]
        title = str(getattr(record.definition, "name", "") if record is not None else "") or str(plugin_id)
        description = str(getattr(record.definition, "description", "") if record is not None else "") or ""
        schema: PluginPreferencesSchema | None = getattr(record.definition, "preferences", None) if record is not None else None

        panel = QGroupBox(title, self._content)
        panel.setObjectName(f"PluginPreferencesPanel:{plugin_id}")
        v = QVBoxLayout(panel)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        if description.strip():
            desc = QLabel(description, panel)
            desc.setWordWrap(True)
            desc.setObjectName("PluginPreferencesDescription")
            v.addWidget(desc)

        # Controls
        if schema is None or not schema.sections:
            v.addWidget(QLabel("This plugin does not declare any preferences in its manifest.", panel))
        else:
            for section in schema.sections:
                v.addWidget(self._build_section(plugin_id, schema, section_id=section.id))

        # Actions
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch(1)
        reset_btn = DatalensButton("Reset to Defaults", app_ctx.theme, ButtonVariant.SECONDARY, panel)
        reset_btn.setIcon(reset_icon(app_ctx.theme, size=18))
        reset_btn.clicked.connect(lambda *_: self._reset_plugin(plugin_id))
        actions.addWidget(reset_btn)
        v.addLayout(actions)

        return panel

    def _build_section(self, plugin_id: PluginId, schema: PluginPreferencesSchema, *, section_id: str) -> QWidget:
        section = next((s for s in schema.sections if s.id == section_id), None)
        if section is None:
            return QLabel(f"(Missing section: {section_id})")

        box = QGroupBox(section.title, self._content)
        box.setObjectName(f"PluginPreferencesSection:{plugin_id}:{section.id}")
        box.setCheckable(True)
        box.setChecked(not bool(section.collapsed))

        content = QWidget(box)
        content_layout = QFormLayout(content)
        content_layout.setContentsMargins(0, 8, 0, 0)
        content_layout.setRowWrapPolicy(QFormLayout.DontWrapRows)
        content_layout.setLabelAlignment(Qt.AlignLeft)
        content_layout.setFormAlignment(Qt.AlignTop)

        def _toggle(checked: bool) -> None:
            content.setVisible(bool(checked))

        box.toggled.connect(_toggle)

        v = QVBoxLayout(box)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(6)

        if section.description:
            d = QLabel(section.description, box)
            d.setWordWrap(True)
            d.setObjectName("PluginPreferencesSectionDescription")
            v.addWidget(d)

        v.addWidget(content)

        for field in section.fields:
            row = self._build_field(plugin_id, field, parent=box)
            if row is not None:
                label, widget = row
                content_layout.addRow(label, widget)

        auto_size_form_layout(content_layout, box, scale=1.10)
        return box

    def _build_field(self, plugin_id: PluginId, field: PreferenceField, *, parent: QWidget) -> tuple[QLabel, QWidget] | None:
        app_ctx = get_app_context()
        prefs = app_ctx.preferences

        label = QLabel(field.title, parent)
        label.setToolTip(field.description or "")

        def _write(v: object) -> None:
            try:
                prefs.set(PluginId(str(plugin_id)), field.key, v)
            except Exception:
                log.warning(
                    "Failed to persist plugin preference (best-effort)",
                    exc_info=True,
                    extra={"operation": "plugin_prefs", "phase": "ui_set_error", "plugin_id": str(plugin_id), "key": field.key},
                )

        widget: QWidget
        if field.kind == PreferenceKind.BOOL:
            cb = DatalensCheckBox("", app_ctx.theme, parent)
            cb.setText("")  # label is separate
            cb.setChecked(bool(prefs.get(plugin_id, field.key, default=field.default)))
            cb.toggled.connect(lambda checked: _write(bool(checked)))
            widget = cb

        elif field.kind in (PreferenceKind.ENUM, PreferenceKind.TOGGLE):
            if field.kind == PreferenceKind.TOGGLE and len(field.options) == 2:
                t = Toggle(
                    theme=app_ctx.theme,
                    left=ToggleOption(field.options[0].id, field.options[0].label),
                    right=ToggleOption(field.options[1].id, field.options[1].label),
                    parent=parent,
                )
                current = prefs.get(plugin_id, field.key, default=field.default)
                if isinstance(current, str):
                    try:
                        t.set_current_id(current, emit=False)
                    except Exception:
                        pass
                t.selectionChanged.connect(lambda selected: _write(str(selected)))
                widget = t
            else:
                combo = QComboBox(parent)
                for opt in field.options:
                    combo.addItem(opt.label, opt.id)
                current = prefs.get(plugin_id, field.key, default=field.default)
                if isinstance(current, str):
                    idx = combo.findData(current)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                combo.currentIndexChanged.connect(lambda *_: _write(str(combo.currentData())))
                widget = combo

        elif field.kind == PreferenceKind.INT:
            spin = QSpinBox(parent)
            if field.min_value is not None:
                spin.setMinimum(int(field.min_value))
            if field.max_value is not None:
                spin.setMaximum(int(field.max_value))
            if field.step is not None:
                spin.setSingleStep(max(1, int(field.step)))
            current = prefs.get(plugin_id, field.key, default=field.default)
            if isinstance(current, (int, float)):
                spin.setValue(int(current))
            spin.valueChanged.connect(lambda v: _write(int(v)))
            widget = spin

        elif field.kind == PreferenceKind.FLOAT:
            spin = QDoubleSpinBox(parent)
            spin.setDecimals(4)
            if field.min_value is not None:
                spin.setMinimum(float(field.min_value))
            if field.max_value is not None:
                spin.setMaximum(float(field.max_value))
            if field.step is not None:
                spin.setSingleStep(float(field.step))
            current = prefs.get(plugin_id, field.key, default=field.default)
            if isinstance(current, (int, float)):
                spin.setValue(float(current))
            spin.valueChanged.connect(lambda v: _write(float(v)))
            widget = spin

        elif field.kind in (PreferenceKind.STRING, PreferenceKind.PATH):
            row = QWidget(parent)
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            edit = QLineEdit(row)
            current = prefs.get(plugin_id, field.key, default=field.default)
            if current is not None:
                edit.setText(str(current))
            edit.editingFinished.connect(lambda: _write(edit.text()))
            h.addWidget(edit, 1)
            if field.kind == PreferenceKind.PATH:
                browse = DatalensButton("Browse…", app_ctx.theme, ButtonVariant.SECONDARY, row)
                browse.clicked.connect(lambda *_: self._browse_path(field, edit))
                h.addWidget(browse)
            widget = row

        else:
            # Unknown kinds are ignored in v0.
            return None

        self._bindings.setdefault(str(plugin_id), []).append(
            _ControlBinding(
                key=field.key,
                read_value=lambda pid=plugin_id, k=field.key: prefs.get(pid, k, default=field.default),
                write_value=_write,
                widget=widget,
            )
        )
        return label, widget

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reset_plugin(self, plugin_id: PluginId) -> None:
        try:
            get_app_context().preferences.reset_to_defaults(plugin_id)
        except Exception:
            log.warning(
                "Failed to reset plugin preferences (best-effort)",
                exc_info=True,
                extra={"operation": "plugin_prefs", "phase": "reset_error", "plugin_id": str(plugin_id)},
            )

    def _refresh_plugin_values(self, plugin_id: str, changed_keys: set[str]) -> None:
        bindings = list(self._bindings.get(str(plugin_id), ()))
        if not bindings:
            return

        for b in bindings:
            if changed_keys and b.key not in changed_keys:
                continue
            try:
                value = b.read_value()
            except Exception:
                continue

            # Best-effort update; use widget type checks.
            try:
                if isinstance(b.widget, DatalensCheckBox):
                    b.widget.blockSignals(True)
                    b.widget.setChecked(bool(value))
                    b.widget.blockSignals(False)
                elif isinstance(b.widget, Toggle):
                    if isinstance(value, str):
                        b.widget.set_current_id(value, emit=False)
                elif isinstance(b.widget, QComboBox):
                    if isinstance(value, str):
                        idx = b.widget.findData(value)
                        if idx >= 0:
                            b.widget.setCurrentIndex(idx)
                elif isinstance(b.widget, QSpinBox):
                    if isinstance(value, (int, float)):
                        b.widget.setValue(int(value))
                elif isinstance(b.widget, QDoubleSpinBox):
                    if isinstance(value, (int, float)):
                        b.widget.setValue(float(value))
                else:
                    # String/path rows contain a QLineEdit
                    edit = b.widget.findChild(QLineEdit)
                    if edit is not None and value is not None:
                        edit.blockSignals(True)
                        edit.setText(str(value))
                        edit.blockSignals(False)
            except Exception:
                continue

    def _browse_path(self, field: PreferenceField, target: QLineEdit) -> None:
        start = target.text()
        kind = field.path_kind or PathKind.FILE
        if kind == PathKind.DIR:
            chosen = QFileDialog.getExistingDirectory(self, "Select folder", start)
            if chosen:
                target.setText(str(chosen))
                try:
                    target.editingFinished.emit()
                except Exception:
                    pass
            return

        filename, _ = QFileDialog.getOpenFileName(self, "Select file", start)
        if filename:
            target.setText(str(filename))
            try:
                target.editingFinished.emit()
            except Exception:
                pass


__all__ = ["PluginPreferencesPage"]
