"""
Example UI test: capture workspace settings undo/redo smoke check.

This exercises a simple, non-device-dependent setting (Save -> Formats),
verifying that changing the toggle pushes to the workspace undo stack and
that undo/redo also persists via plugin preferences.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QToolButton

from datalens.domain.plugin import PluginId


@pytest.mark.ui
def test_capture_workspace_save_formats_undo_redo(datalens_app):
    from datalens.plugins.capture.service import CaptureService
    from datalens.plugins.capture.ui.workspace import CaptureWorkspaceWidget
    from datalens.ui.widgets.core.toggle import Toggle

    app_ctx = datalens_app.app_context
    prefs = app_ctx.preferences

    workspace = CaptureWorkspaceWidget(parent=None, theme=datalens_app.app_theme, app_ctx=app_ctx, service=CaptureService())
    try:
        workspace.show()
        QTest.qWait(200)

        toggle = workspace.findChild(Toggle, "Capture:SaveFormatsToggle")
        assert toggle is not None, "Expected Capture save formats toggle"

        depth_btn = None
        for btn in toggle.findChildren(QToolButton):
            if (btn.text() or "").strip().lower() == "depth":
                depth_btn = btn
                break
        assert depth_btn is not None, "Expected Depth segment button"

        # Toggle Depth on (pushes one undo command and persists).
        QTest.mouseClick(depth_btn, Qt.LeftButton)
        QTest.qWait(50)
        assert toggle.is_checked("depth") is True

        stored = prefs.get(PluginId("capture"), "save_formats", default=[])
        assert isinstance(stored, list)
        assert "depth" in stored

        workspace.undo_stack.undo()
        QTest.qWait(50)
        assert toggle.is_checked("depth") is False

        stored = prefs.get(PluginId("capture"), "save_formats", default=[])
        assert isinstance(stored, list)
        assert "depth" not in stored

        workspace.undo_stack.redo()
        QTest.qWait(50)
        assert toggle.is_checked("depth") is True

        stored = prefs.get(PluginId("capture"), "save_formats", default=[])
        assert isinstance(stored, list)
        assert "depth" in stored
    finally:
        workspace.close()
        workspace.deleteLater()


@pytest.mark.ui
def test_capture_workspace_scan_mode_undo_redo(datalens_app):
    from datalens.plugins.capture.service import CaptureService
    from datalens.plugins.capture.ui.workspace import CaptureWorkspaceWidget
    from datalens.ui.widgets.core.toggle import Toggle

    app_ctx = datalens_app.app_context
    prefs = app_ctx.preferences

    workspace = CaptureWorkspaceWidget(parent=None, theme=datalens_app.app_theme, app_ctx=app_ctx, service=CaptureService())
    try:
        workspace.show()
        QTest.qWait(200)

        toggle = workspace.findChild(Toggle, "Capture:ScanModeToggle")
        assert toggle is not None, "Expected Capture scan mode toggle"

        auto_btn = None
        for btn in toggle.findChildren(QToolButton):
            if (btn.text() or "").strip().lower() == "auto":
                auto_btn = btn
                break
        assert auto_btn is not None, "Expected Auto scan mode button"

        QTest.mouseClick(auto_btn, Qt.LeftButton)
        QTest.qWait(50)
        assert toggle.current_id == "auto"

        stored = prefs.get(PluginId("capture"), "scan_mode", default="manual")
        assert stored == "auto"

        workspace.undo_stack.undo()
        QTest.qWait(50)
        assert toggle.current_id == "manual"

        stored = prefs.get(PluginId("capture"), "scan_mode", default="manual")
        assert stored == "manual"

        workspace.undo_stack.redo()
        QTest.qWait(50)
        assert toggle.current_id == "auto"

        stored = prefs.get(PluginId("capture"), "scan_mode", default="manual")
        assert stored == "auto"
    finally:
        workspace.close()
        workspace.deleteLater()


@pytest.mark.ui
def test_capture_workspace_depth_auto_scale_undo_redo(datalens_app):
    from datalens.plugins.capture.service import CaptureService
    from datalens.plugins.capture.ui.workspace import CaptureWorkspaceWidget
    from datalens.ui.widgets.core.checkboxes import DatalensCheckBox

    app_ctx = datalens_app.app_context
    prefs = app_ctx.preferences

    workspace = CaptureWorkspaceWidget(parent=None, theme=datalens_app.app_theme, app_ctx=app_ctx, service=CaptureService())
    try:
        workspace.show()
        QTest.qWait(200)

        checkbox = None
        for box in workspace.findChildren(DatalensCheckBox):
            if (box.text() or "").strip().lower() == "auto-scale depth range":
                checkbox = box
                break
        assert checkbox is not None, "Expected depth auto-scale checkbox"

        QTest.mouseClick(checkbox, Qt.LeftButton)
        QTest.qWait(50)
        assert checkbox.isChecked() is False

        stored = prefs.get(PluginId("capture"), "depth_auto_scale", default=True)
        assert stored is False

        workspace.undo_stack.undo()
        QTest.qWait(50)
        assert checkbox.isChecked() is True

        stored = prefs.get(PluginId("capture"), "depth_auto_scale", default=True)
        assert stored is True

        workspace.undo_stack.redo()
        QTest.qWait(50)
        assert checkbox.isChecked() is False

        stored = prefs.get(PluginId("capture"), "depth_auto_scale", default=True)
        assert stored is False
    finally:
        workspace.close()
        workspace.deleteLater()
