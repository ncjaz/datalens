from __future__ import annotations

"""
Global application stylesheet (QSS).

This is intentionally centralized so UI chrome and common inputs look consistent
across the whole application (including Welcome + Main windows) without each
widget needing bespoke QSS.

Pairing:
- Tokens: `datalens.domain.ui.theme.ThemeSettings`
- Palette + QSS application: `datalens.ui.theme.app_theme.AppTheme.apply_to`
"""

from typing import TYPE_CHECKING

from PySide6.QtGui import QColor

if TYPE_CHECKING:
    from datalens.ui.theme.app_theme import AppTheme


def build_global_qss(*, theme: AppTheme, base: QColor, alt: QColor, button: QColor) -> str:
    """
    Build the global QSS string for the current theme.

    Args:
        theme: AppTheme instance (semantic tokens + helpers).
        base: Derived surface color for QPalette.Base.
        alt: Derived surface color for QPalette.AlternateBase.
        button: Derived surface color for QPalette.Button.
    """
    chrome_bg = theme.background_secondary_color
    chrome_border = theme.with_alpha_hex(theme.text_color, 0.10)

    base_hex = base.name().upper()
    alt_hex = alt.name().upper()
    button_hex = button.name().upper()

    field_border = theme.with_alpha_hex(theme.text_color, 0.18)
    field_border_focus = theme.with_alpha_hex(theme.primary_color, 0.65)
    field_hover = theme.with_alpha_hex(theme.primary_color, 0.12)
    popup_hover = theme.with_alpha_hex(theme.primary_color, 0.30)

    return (
        "QToolTip {"
        f"background-color: {theme.with_alpha_hex(theme.primary_color, 0.85)};"
        "color: #ffffff;"
        "border: 1px solid rgba(255, 255, 255, 40);"
        "padding: 4px 6px;"
        "border-radius: 4px;"
        "}"
        "QMenuBar {"
        f"background-color: {chrome_bg};"
        f"color: {theme.text_color};"
        f"border-bottom: 1px solid {chrome_border};"
        "}"
        "QMenuBar::item {"
        "padding: 5px 10px;"
        "background: transparent;"
        "}"
        "QMenuBar::item:selected {"
        f"background-color: {popup_hover};"
        "}"
        "QMenu {"
        f"background-color: {chrome_bg};"
        f"color: {theme.text_color};"
        f"border: 1px solid {chrome_border};"
        "border-radius: 10px;"
        "padding: 4px;"
        "}"
        "QMenu::item {"
        "padding: 6px 10px;"
        "margin: 2px 4px;"
        "border-radius: 8px;"
        "}"
        "QMenu::item:selected {"
        f"background-color: {popup_hover};"
        "}"
        "QStatusBar {"
        f"background-color: {chrome_bg};"
        f"color: {theme.text_color};"
        f"border-top: 1px solid {chrome_border};"
        "}"
        # Inputs: apply a consistent V1-like style app-wide so plugins can use
        # standard Qt widgets without bespoke QSS.
        "QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox {"
        f"background-color: {base_hex};"
        f"color: {theme.text_color};"
        f"border: 1px solid {field_border};"
        "border-radius: 10px;"
        "padding: 4px 8px;"
        "selection-background-color: rgba(255,255,255,0.15);"
        "}"
        "QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QAbstractSpinBox:hover {"
        f"background-color: {field_hover};"
        "}"
        "QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus {"
        f"border: 1px solid {field_border_focus};"
        "}"
        "QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QAbstractSpinBox:disabled {"
        f"background-color: {alt_hex};"
        f"color: {theme.disabled_text_color()};"
        f"border: 1px solid {theme.disabled_border_color()};"
        "}"
        "QComboBox {"
        f"background-color: {button_hex};"
        f"color: {theme.text_color};"
        f"border: 1px solid {field_border};"
        "border-radius: 10px;"
        "padding: 4px 28px 4px 10px;"
        "}"
        "QComboBox:on {"
        "border-radius: 10px;"
        "}"
        "QComboBox:focus {"
        f"border: 1px solid {field_border_focus};"
        "}"
        "QComboBox::drop-down {"
        "width: 24px;"
        "border: none;"
        "background: transparent;"
        "border-top-right-radius: 10px;"
        "border-bottom-right-radius: 10px;"
        "}"
        "QComboBox QAbstractItemView {"
        f"background-color: {chrome_bg};"
        f"color: {theme.text_color};"
        "border: none;"
        "border-radius: 10px;"
        "outline: 0;"
        "}"
        # The combobox popup is wrapped in a private container frame. We style
        # the container so the popup border + rounding are seamless and we don't
        # see a square, palette-driven "viewport" background inside.
        "QFrame#qt_combobox_popup {"
        f"background-color: {chrome_bg};"
        f"border: 1px solid {field_border};"
        "border-radius: 10px;"
        "padding: 2px;"
        "}"
        # Keep the inner view transparent so the container's background and
        # rounded border remain the single source of truth.
        "QFrame#qt_combobox_popup QAbstractItemView {"
        "background: transparent;"
        "border: none;"
        "outline: 0;"
        f"selection-background-color: {popup_hover};"
        f"selection-color: {theme.text_color};"
        "}"
        "QFrame#qt_combobox_popup QAbstractItemView::viewport {"
        "background: transparent;"
        "}"
        "QFrame#qt_combobox_popup QWidget#qt_scrollarea_viewport {"
        "background: transparent;"
        "}"
        # Item hover/selection: the combobox popup is a separate top-level window
        # (`qt_combobox_popup`), so `QComboBox QAbstractItemView::item:hover`
        # may not match on some platforms. Style both the popup container and
        # the descendant view directly.
        # Item views sometimes apply hover/selection via the concrete view class
        # (QListView/QTreeView), so style both the abstract and concrete variants.
        "QFrame#qt_combobox_popup QAbstractItemView::item:selected {"
         f"background-color: {popup_hover};"
         "}"
        "QFrame#qt_combobox_popup QAbstractItemView::item:hover {"
         f"background-color: {popup_hover};"
         "}"
        "QFrame#qt_combobox_popup QListView::item:selected {"
        f"background-color: {popup_hover};"
        "}"
        "QFrame#qt_combobox_popup QListView::item:hover {"
        f"background-color: {popup_hover};"
        "}"
        "QFrame#qt_combobox_popup QTreeView::item:selected {"
        f"background-color: {popup_hover};"
        "}"
        "QFrame#qt_combobox_popup QTreeView::item:hover {"
        f"background-color: {popup_hover};"
        "}"
        # Fallback for styles that do keep the view in the combobox hierarchy.
        "QComboBox QAbstractItemView::item:selected {"
         f"background-color: {popup_hover};"
         "}"
        "QComboBox QAbstractItemView::item:hover {"
         f"background-color: {popup_hover};"
         "}"
        "QComboBox QListView::item:selected {"
        f"background-color: {popup_hover};"
        "}"
        "QComboBox QListView::item:hover {"
        f"background-color: {popup_hover};"
        "}"
    )


__all__ = ["build_global_qss"]
