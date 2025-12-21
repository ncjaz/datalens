from __future__ import annotations

"""
Popup rounding helpers.

Qt stylesheets can round *painted* corners, but many popup widgets (QMenu,
QComboBox popup) are still rectangular native windows. On Windows this can leave
sharp outer corners even when the interior is styled.

We apply a window mask to popups to make the *window shape* rounded too.
"""

from typing import Final

from PySide6.QtCore import QObject, QEvent, QRect, Qt
from PySide6.QtGui import QPainterPath, QRegion
from PySide6.QtWidgets import QApplication, QWidget


def _rounded_region(rect: QRect, radius: int) -> QRegion:
    r = max(0, int(radius))
    if r <= 0:
        return QRegion(rect)
    path = QPainterPath()
    path.addRoundedRect(rect, float(r), float(r))
    return QRegion(path.toFillPolygon().toPolygon())


class _PopupRoundingFilter(QObject):
    _COMBOBOX_POPUP_OBJECT_NAME: Final[str] = "qt_combobox_popup"
    _COMBOBOX_POPUP_CLASSNAME: Final[str] = "QComboBoxPrivateContainer"

    def __init__(self, *, radius: int) -> None:
        super().__init__()
        self._radius = max(0, int(radius))

    def _should_round(self, w: QWidget) -> bool:
        if not w.isWindow():
            return False

        # Combobox popup is a private QFrame with this objectName.
        if w.objectName() == self._COMBOBOX_POPUP_OBJECT_NAME:
            return True

        # QMenu and friends are popup windows; rounding improves UX consistency.
        #
        # Important: do NOT check `flags & Qt.Popup` because `Qt.WindowType` is a
        # value within the WindowType mask (not a single independent bit). A
        # bitwise test will incorrectly match normal windows (e.g. `Qt.Window`)
        # and can effectively "de-frame" the entire app by applying a mask.
        return w.windowType() == Qt.Popup

    def _apply_mask(self, w: QWidget) -> None:
        if not self._should_round(w):
            return
        # Avoid masking zero-sized widgets.
        rect = w.rect()
        if rect.width() <= 1 or rect.height() <= 1:
            return
        w.setMask(_rounded_region(rect, self._radius))

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if isinstance(obj, QWidget):
            # Qt's combobox popup is a private container widget that (on some
            # platforms / Qt builds) does not have a stable objectName. We set
            # one so our global QSS can reliably style the popup list.
            if (
                obj.objectName() != self._COMBOBOX_POPUP_OBJECT_NAME
                and obj.metaObject().className() == self._COMBOBOX_POPUP_CLASSNAME
            ):
                obj.setObjectName(self._COMBOBOX_POPUP_OBJECT_NAME)
            if event.type() in (QEvent.Show, QEvent.Resize, QEvent.LayoutRequest, QEvent.Polish):
                self._apply_mask(obj)
        return super().eventFilter(obj, event)


def install_popup_rounding(app: QApplication, *, radius: int = 10) -> None:
    """
    Install a global event filter that applies rounded window masks to popups.

    This is best-effort. If a platform ignores masks for certain popup types,
    the interior QSS rounding still applies.
    """
    if getattr(app, "_datalens_popup_rounding_installed", False):
        return

    flt = _PopupRoundingFilter(radius=radius)
    app.installEventFilter(flt)
    # Keep a strong ref so the filter isn't GC'd.
    setattr(app, "_datalens_popup_rounding_filter", flt)
    setattr(app, "_datalens_popup_rounding_installed", True)


__all__ = ["install_popup_rounding"]
