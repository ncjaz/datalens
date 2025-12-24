"""
Example UI test: canvas undo/redo smoke check.

This uses the widget_test plugin's canvas demo, clicks the "Run undo self-test"
button, and asserts the status label reports PASS.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton


@pytest.mark.ui
def test_widget_test_canvas_undo_self_test(datalens_app):
    from datalens.plugins.widget_test.ui.workspace import WorkspaceWidget

    workspace = WorkspaceWidget(
        theme=datalens_app.app_theme,
        parent=None,
        shortcut_button_bindings=None,
    )

    try:
        workspace.show()
        QTest.qWait(150)

        btn = workspace.findChild(QPushButton, "WidgetTest:CanvasUndoSelfTest")
        assert btn is not None, "Expected WidgetTest canvas undo self-test button"
        QTest.mouseClick(btn, Qt.LeftButton)
        QTest.qWait(50)

        label = workspace.findChild(QLabel, "WidgetTest:CanvasUndoSelfTestStatus")
        assert label is not None, "Expected WidgetTest canvas undo self-test status label"
        assert "PASS" in (label.text() or ""), f"Expected PASS, got: {label.text()!r}"
    finally:
        workspace.close()
        workspace.deleteLater()

