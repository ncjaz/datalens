from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QColor, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from datalens.domain.ui.theme import DEFAULT_THEME, ThemeSettings
from datalens.services.settings_store import default_debounced_settings_writer, default_settings_store


def _normalize_hex(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) != 6:
        return None
    try:
        int(raw, 16)
    except Exception:
        return None
    return f"#{raw.upper()}"


@dataclass(frozen=True)
class _ColorRow:
    edit: QLineEdit


class ThemePreferencesPage(QWidget):
    """
    Preferences page: Theme.

    Persists semantic theme tokens into `settings.json` (AppSettings.theme_settings)
    and applies them immediately to the running QApplication theme.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = default_settings_store()
        self._writer = default_debounced_settings_writer()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Theme")
        title.setObjectName("PreferencesTitle")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(title)

        settings = self._store.load()
        theme: ThemeSettings = getattr(settings, "theme_settings", DEFAULT_THEME)

        colors = QGroupBox("Colors", self)
        colors_form = self._form(colors)
        self._primary = self._color_row(colors_form, "Primary", theme.primary_color)
        self._background = self._color_row(colors_form, "Background", theme.background_color)
        self._secondary = self._color_row(colors_form, "Secondary", theme.secondary_color)
        self._tertiary = self._color_row(colors_form, "Tertiary", theme.tertiary_color)
        self._text = self._color_row(colors_form, "Text", theme.text_color)
        self._grid = self._color_row(colors_form, "Chart grid", theme.chart_grid_color)
        layout.addWidget(colors)

        accents = QGroupBox("Accents", self)
        accents_form = self._form(accents)
        self._confirm = self._color_row(accents_form, "Confirm", theme.accent_confirm)
        self._cancel = self._color_row(accents_form, "Cancel", theme.accent_cancel)
        self._warning = self._color_row(accents_form, "Warning", theme.accent_warning)
        layout.addWidget(accents)

        borders = QGroupBox("Borders", self)
        borders_form = self._form(borders)
        self._primary_border = self._color_row(borders_form, "Primary border", theme.primary_border)
        self._secondary_border = self._color_row(borders_form, "Secondary border", theme.secondary_border)
        self._tertiary_border = self._color_row(borders_form, "Tertiary border", theme.tertiary_border)
        self._confirm_border = self._color_row(borders_form, "Confirm border", theme.accent_confirm_border)
        self._cancel_border = self._color_row(borders_form, "Cancel border", theme.accent_cancel_border)
        self._warning_border = self._color_row(borders_form, "Warning border", theme.accent_warning_border)
        layout.addWidget(borders)

        surfaces = QGroupBox("Surfaces (optional overrides)", self)
        surfaces_form = self._form(surfaces)
        self._surface_base = self._optional_color_row(
            surfaces_form, "Surface base (QPalette.Base)", theme.surface_base
        )
        self._surface_button = self._optional_color_row(
            surfaces_form, "Surface button (QPalette.Button)", theme.surface_button
        )
        self._surface_alt = self._optional_color_row(
            surfaces_form, "Surface alt (QPalette.AlternateBase)", theme.surface_alt
        )
        layout.addWidget(surfaces)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        reset_btn = QPushButton("Reset to defaults", self)
        reset_btn.clicked.connect(self._reset_defaults)
        actions.addWidget(reset_btn, alignment=Qt.AlignLeft)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)

        for edit in (
            self._primary.edit,
            self._background.edit,
            self._secondary.edit,
            self._tertiary.edit,
            self._text.edit,
            self._grid.edit,
            self._confirm.edit,
            self._cancel.edit,
            self._warning.edit,
            self._primary_border.edit,
            self._secondary_border.edit,
            self._tertiary_border.edit,
            self._confirm_border.edit,
            self._cancel_border.edit,
            self._warning_border.edit,
            self._surface_base.edit,
            self._surface_button.edit,
            self._surface_alt.edit,
        ):
            edit.editingFinished.connect(self._persist)  # type: ignore[arg-type]

    def _form(self, group: QGroupBox) -> QFormLayout:
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        return form

    def _apply_theme_to_app(self, theme: ThemeSettings) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app_theme = getattr(app, "app_theme", None)
        if app_theme is None:
            return
        try:
            app_theme.set_settings(theme)
        except Exception:
            return

    def _persist(self) -> None:
        theme = self._theme_from_ui()

        def mutator(current):
            return replace(current, theme_settings=theme, theme_name="custom")

        self._writer.request_update(mutator)
        self._apply_theme_to_app(theme)

    def _theme_from_ui(self) -> ThemeSettings:
        def pick(edit: QLineEdit, default: str) -> str:
            normalized = _normalize_hex(edit.text())
            if normalized is None:
                return default
            edit.setText(normalized)
            return normalized

        def pick_optional(edit: QLineEdit) -> str | None:
            raw = edit.text().strip()
            if not raw:
                return None
            normalized = _normalize_hex(raw)
            if normalized is None:
                return None
            edit.setText(normalized)
            return normalized

        return ThemeSettings(
            primary_color=pick(self._primary.edit, DEFAULT_THEME.primary_color),
            background_color=pick(self._background.edit, DEFAULT_THEME.background_color),
            secondary_color=pick(self._secondary.edit, DEFAULT_THEME.secondary_color),
            tertiary_color=pick(self._tertiary.edit, DEFAULT_THEME.tertiary_color),
            text_color=pick(self._text.edit, DEFAULT_THEME.text_color),
            chart_grid_color=pick(self._grid.edit, DEFAULT_THEME.chart_grid_color),
            accent_confirm=pick(self._confirm.edit, DEFAULT_THEME.accent_confirm),
            accent_cancel=pick(self._cancel.edit, DEFAULT_THEME.accent_cancel),
            accent_warning=pick(self._warning.edit, DEFAULT_THEME.accent_warning),
            primary_border=pick(self._primary_border.edit, DEFAULT_THEME.primary_border),
            secondary_border=pick(self._secondary_border.edit, DEFAULT_THEME.secondary_border),
            tertiary_border=pick(self._tertiary_border.edit, DEFAULT_THEME.tertiary_border),
            accent_confirm_border=pick(self._confirm_border.edit, DEFAULT_THEME.accent_confirm_border),
            accent_cancel_border=pick(self._cancel_border.edit, DEFAULT_THEME.accent_cancel_border),
            accent_warning_border=pick(self._warning_border.edit, DEFAULT_THEME.accent_warning_border),
            surface_base=pick_optional(self._surface_base.edit),
            surface_button=pick_optional(self._surface_button.edit),
            surface_alt=pick_optional(self._surface_alt.edit),
        )

    def _reset_defaults(self) -> None:
        self._primary.edit.setText(DEFAULT_THEME.primary_color)
        self._background.edit.setText(DEFAULT_THEME.background_color)
        self._secondary.edit.setText(DEFAULT_THEME.secondary_color)
        self._tertiary.edit.setText(DEFAULT_THEME.tertiary_color)
        self._text.edit.setText(DEFAULT_THEME.text_color)
        self._grid.edit.setText(DEFAULT_THEME.chart_grid_color)

        self._confirm.edit.setText(DEFAULT_THEME.accent_confirm)
        self._cancel.edit.setText(DEFAULT_THEME.accent_cancel)
        self._warning.edit.setText(DEFAULT_THEME.accent_warning)

        self._primary_border.edit.setText(DEFAULT_THEME.primary_border)
        self._secondary_border.edit.setText(DEFAULT_THEME.secondary_border)
        self._tertiary_border.edit.setText(DEFAULT_THEME.tertiary_border)
        self._confirm_border.edit.setText(DEFAULT_THEME.accent_confirm_border)
        self._cancel_border.edit.setText(DEFAULT_THEME.accent_cancel_border)
        self._warning_border.edit.setText(DEFAULT_THEME.accent_warning_border)

        self._surface_base.edit.setText("")
        self._surface_button.edit.setText("")
        self._surface_alt.edit.setText("")

        self._persist()

    def _color_row(self, form: QFormLayout, label: str, initial_hex: str) -> _ColorRow:
        edit = QLineEdit()
        edit.setText(str(initial_hex))
        edit.setPlaceholderText("#RRGGBB")
        edit.setMaximumWidth(160)
        edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"^#?[0-9A-Fa-f]{6}$")))

        pick_btn = QPushButton("Pick…")
        pick_btn.setFixedWidth(64)

        def pick_color() -> None:
            normalized = _normalize_hex(edit.text()) or "#000000"
            chosen = QColorDialog.getColor(QColor(normalized), self, f"Select {label} color")
            if not chosen.isValid():
                return
            edit.setText(chosen.name().upper())
            self._persist()

        pick_btn.clicked.connect(pick_color)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(edit)
        row.addWidget(pick_btn)
        row.addStretch(1)
        form.addRow(label, row)
        return _ColorRow(edit=edit)

    def _optional_color_row(self, form: QFormLayout, label: str, initial_hex: str | None) -> _ColorRow:
        edit = QLineEdit()
        edit.setText(str(initial_hex) if initial_hex else "")
        edit.setPlaceholderText("derive (leave blank)")
        edit.setMaximumWidth(200)
        edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"^$|#?[0-9A-Fa-f]{6}$")))

        pick_btn = QPushButton("Pick…")
        pick_btn.setFixedWidth(64)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(64)

        def pick_color() -> None:
            current_hex = _normalize_hex(edit.text()) or DEFAULT_THEME.background_color
            chosen = QColorDialog.getColor(QColor(current_hex), self, f"Select {label}")
            if not chosen.isValid():
                return
            edit.setText(chosen.name().upper())
            self._persist()

        def clear_color() -> None:
            edit.setText("")
            self._persist()

        pick_btn.clicked.connect(pick_color)
        clear_btn.clicked.connect(clear_color)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(edit)
        row.addWidget(pick_btn)
        row.addWidget(clear_btn)
        row.addStretch(1)
        form.addRow(label, row)
        return _ColorRow(edit=edit)


__all__ = ["ThemePreferencesPage"]

