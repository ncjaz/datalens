"""
Regression tests for ImageCanvas event handling.

These tests ensure the canvas never hard-crashes the Qt event loop if a tool
returns an invalid value (e.g., None) from its handlers.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, QEvent
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from datalens.ui.canvas.canvas_widget import ImageCanvas


class _BadToolReturnsNone:
    tool_id = "bad_returns_none"

    def on_activate(self) -> None:
        return None

    def on_deactivate(self) -> None:
        return None

    def on_mouse_event(self, event: QMouseEvent, view, image_pos: QPointF):  # type: ignore[no-untyped-def]
        _ = (event, view, image_pos)
        return None

    def on_wheel_event(self, event: QWheelEvent, view, image_pos: QPointF):  # type: ignore[no-untyped-def]
        _ = (event, view, image_pos)
        return None


@pytest.mark.ui
def test_canvas_does_not_crash_when_tool_returns_none(datalens_app) -> None:
    _ = datalens_app

    canvas = ImageCanvas()
    canvas.resize(300, 200)
    canvas.show()
    QTest.qWait(50)

    try:
        canvas.tools.set_active(_BadToolReturnsNone())
        canvas.setFocus()
        QTest.qWait(10)

        wheel = QWheelEvent(
            QPointF(50.0, 50.0),
            QPointF(50.0, 50.0),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(canvas, wheel)

        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(60, 60))
        QTest.mouseMove(canvas, QPoint(70, 70))
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(70, 70))

    finally:
        canvas.close()
        canvas.deleteLater()
