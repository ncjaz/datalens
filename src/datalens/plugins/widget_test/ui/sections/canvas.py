from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import weakref

from datalens.api.tools import ToolDefinition, ToolKind
from datalens.core.logging import get_logger
from datalens.ui.canvas.canvas_widget import ImageCanvas
from datalens.ui.canvas.layers.vector_layer import VectorLayer, VectorShape, VectorStyle
from datalens.ui.canvas.tools.edit_events import CanvasEditEvent, CanvasEditKind
from datalens.ui.canvas.undo import VectorLayerUndoAdapter
from datalens.ui.canvas.tools.select_edit_tool import SelectEditTool, SelectionState
from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.icons.settings_icon import settings_icon
from datalens.ui.widgets.tools_toolbar import ToolsToolbar

log = get_logger(__name__)

_ACTIVE_CONTROLLER: weakref.ReferenceType[_CanvasTestController] | None = None


def delete_selected_vertex_from_shortcut() -> bool:
    """
    Called by the widget_test plugin shortcut callback (Delete key).

    Returns True if a vertex/shape was changed.
    """
    global _ACTIVE_CONTROLLER
    ctrl = _ACTIVE_CONTROLLER() if _ACTIVE_CONTROLLER is not None else None
    if ctrl is None:
        return False
    return bool(ctrl.delete_selected_vertex())


class _CanvasTestController:
    def __init__(
        self,
        *,
        canvas: ImageCanvas,
        layer: VectorLayer,
        status_label: QLabel,
        self_test_label: QLabel,
        undo_stack: QUndoStack | None = None,
        activate_tool: bool = True,
    ) -> None:
        self._canvas = canvas
        self._layer = layer
        self._status_label = status_label
        self._self_test_label = self_test_label
        self._undo_stack = undo_stack
        self._undo = VectorLayerUndoAdapter(layer=self._layer, stack=undo_stack) if undo_stack is not None else None
        self._tool = SelectEditTool(
            vector_layer=self._layer,
            on_selection_changed=self._on_selection_changed,
            on_edit=self._on_edit,
        )
        if activate_tool:
            self._canvas.tools.set_active(self._tool)
        if undo_stack is not None:
            try:
                undo_stack.indexChanged.connect(lambda *_: self._canvas.update())  # type: ignore[arg-type]
            except Exception:
                pass

    def _on_selection_changed(self, sel: SelectionState | None) -> None:
        if sel is None:
            self._status_label.setText("Selected: (none)")
        elif sel.vertex_index < 0:
            self._status_label.setText(f"Selected: {sel.shape_id} (shape)")
        else:
            self._status_label.setText(f"Selected: {sel.shape_id} vertex {sel.vertex_index}")
        self._canvas.update()

    def _on_edit(self, event) -> None:
        if self._undo is None:
            return
        self._undo.handle_edit(event)

    def delete_selected_vertex(self) -> bool:
        changed = bool(self._tool.delete_selected_vertex())
        if changed:
            self._canvas.update()
        return changed

    @property
    def tool(self) -> SelectEditTool:
        return self._tool

    def run_undo_self_test(self) -> bool:
        """
        Programmatic smoke test for canvas undo/redo.

        This is intentionally simple: apply one edit, undo it, redo it, and
        verify the layer state matches expectations.
        """
        layer = self._layer
        undo = self._undo
        stack = self._undo_stack
        if undo is None or stack is None:
            self._self_test_label.setText("Undo self-test: unavailable (no undo stack)")
            return False

        shape_id = "poly_1"
        shape = layer.get_shape(shape_id)
        if shape is None or not shape.points:
            self._self_test_label.setText("Undo self-test: failed (missing poly_1)")
            return False

        original = QPointF(float(shape.points[0].x()), float(shape.points[0].y()))
        moved = QPointF(float(original.x()) + 18.0, float(original.y()) + 12.0)

        pts = list(shape.points)
        pts[0] = QPointF(float(moved.x()), float(moved.y()))
        layer.upsert_shape(VectorShape(shape_id=shape.shape_id, points=tuple(pts), closed=shape.closed, style=shape.style))

        undo.handle_edit(
            CanvasEditEvent(
                kind=CanvasEditKind.VERTEX_MOVED,
                layer_id=layer.layer_id,
                shape_id=shape_id,
                vertex_index=0,
                from_pos=original,
                to_pos=moved,
            )
        )

        after_apply = layer.get_shape(shape_id)
        if after_apply is None or not after_apply.points:
            self._self_test_label.setText("Undo self-test: failed (shape missing after apply)")
            return False
        if (float(after_apply.points[0].x()) != float(moved.x())) or (float(after_apply.points[0].y()) != float(moved.y())):
            self._self_test_label.setText("Undo self-test: failed (apply mismatch)")
            return False

        stack.undo()
        after_undo = layer.get_shape(shape_id)
        if after_undo is None or not after_undo.points:
            self._self_test_label.setText("Undo self-test: failed (shape missing after undo)")
            return False
        if (float(after_undo.points[0].x()) != float(original.x())) or (float(after_undo.points[0].y()) != float(original.y())):
            self._self_test_label.setText("Undo self-test: failed (undo mismatch)")
            return False

        stack.redo()
        after_redo = layer.get_shape(shape_id)
        if after_redo is None or not after_redo.points:
            self._self_test_label.setText("Undo self-test: failed (shape missing after redo)")
            return False
        if (float(after_redo.points[0].x()) != float(moved.x())) or (float(after_redo.points[0].y()) != float(moved.y())):
            self._self_test_label.setText("Undo self-test: failed (redo mismatch)")
            return False

        self._self_test_label.setText("Undo self-test: PASS")
        return True


def _set_active_controller(ctrl: _CanvasTestController | None) -> None:
    global _ACTIVE_CONTROLLER
    _ACTIVE_CONTROLLER = weakref.ref(ctrl) if ctrl is not None else None


def build_canvas_section(parent: QWidget, *, theme: AppTheme, undo_stack: QUndoStack | None = None) -> QWidget:
    root = QWidget(parent)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    header = QLabel("Canvas (v0)", root)
    header.setStyleSheet("font-weight: 700;")
    layout.addWidget(header)

    hint = QLabel(
        "Ctrl+Wheel zooms. Middle-mouse drag pans. Click an edge to insert a vertex. "
        "Click+drag a vertex to move it. Click inside a polygon to select it, then drag inside the fill to move it. "
        "Press Delete to remove the selected vertex (or delete the whole shape when a shape is selected).",
        root,
    )
    hint.setWordWrap(True)
    hint.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.75)}; font-size: 11px;")
    layout.addWidget(hint)

    selection_status = QLabel("Selected: (none)", root)
    selection_status.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.85)}; font-size: 11px;")
    layout.addWidget(selection_status)

    self_test_row = QHBoxLayout()
    self_test_row.setContentsMargins(0, 0, 0, 0)
    self_test_row.setSpacing(10)

    self_test_btn = QPushButton("Run undo self-test", root)
    self_test_btn.setObjectName("WidgetTest:CanvasUndoSelfTest")
    self_test_btn.setToolTip("Applies one edit, then undo/redo and verifies state.")
    self_test_row.addWidget(self_test_btn, 0)

    self_test_status = QLabel("Undo self-test: (not run)", root)
    self_test_status.setObjectName("WidgetTest:CanvasUndoSelfTestStatus")
    self_test_status.setStyleSheet(f"color: {theme.with_alpha_hex(theme.text_color, 0.80)}; font-size: 11px;")
    self_test_row.addWidget(self_test_status, 1)

    layout.addLayout(self_test_row)

    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    layout.addLayout(row)

    canvas = ImageCanvas(root)
    canvas.setObjectName("WidgetTest:Canvas")
    canvas.setMinimumHeight(260)
    row.addWidget(canvas, 1)

    # Small procedural image (no file I/O; safe for the UI thread).
    img = QImage(640, 360, QImage.Format.Format_RGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            # simple gradient + a warm accent region
            r = int(20 + (x / img.width()) * 60)
            g = int(20 + (y / img.height()) * 60)
            b = int(30 + ((x + y) / (img.width() + img.height())) * 70)
            if 240 < x < 420 and 120 < y < 260:
                r = min(255, r + 80)
                g = min(255, g + 40)
            img.setPixel(x, y, (r << 16) | (g << 8) | b)

    canvas.set_base_image(img, fit=True)

    shapes = [
        VectorShape(
            shape_id="poly_1",
            points=(
                QPointF(160.0, 110.0),
                QPointF(260.0, 90.0),
                QPointF(330.0, 160.0),
                QPointF(230.0, 210.0),
            ),
            closed=True,
            style=VectorStyle(
                stroke_hex=theme.primary_color,
                stroke_width_px=2,
                stroke_alpha=0.95,
                fill_hex=theme.primary_color,
                fill_alpha=0.12,
                fill_on_select_only=True,
            ),
        ),
        VectorShape(
            shape_id="line_1",
            points=(QPointF(60.0, 300.0), QPointF(580.0, 300.0)),
            closed=False,
            style=VectorStyle(stroke_hex=theme.tertiary_color, stroke_width_px=2, stroke_alpha=0.8),
        ),
    ]

    vector_layer = VectorLayer(layer_id="vector.v0", shapes=shapes)
    canvas.add_layer(vector_layer, z=10, visible=True)

    controller = _CanvasTestController(
        canvas=canvas,
        layer=vector_layer,
        status_label=selection_status,
        self_test_label=self_test_status,
        undo_stack=undo_stack,
        activate_tool=False,
    )
    _set_active_controller(controller)
    canvas.destroyed.connect(lambda *_: _set_active_controller(None))  # type: ignore[arg-type]
    self_test_btn.clicked.connect(lambda *_: controller.run_undo_self_test())  # type: ignore[arg-type]

    tool_defs = [
        ToolDefinition(
            tool_id=controller.tool.tool_id,
            label="Select/Edit",
            tooltip="Select and edit vector shapes",
            icon_factory=lambda t: settings_icon(t, size=22),
            kind=ToolKind.MODE,
            default_order=0,
            section="tools",
            canvas_types=frozenset({"image_2d"}),
            create=lambda _host, tool=controller.tool: tool,
        )
    ]
    toolbar = ToolsToolbar(
        tool_definitions=tool_defs,
        canvas_type="image_2d",
        canvas_host=canvas,
        theme=theme,
        plugin_id="widget_test",
        preferences=None,
        parent=root,
    )
    row.addWidget(toolbar, 0, Qt.AlignmentFlag.AlignTop)

    log.info(
        "Widget test canvas initialized",
        extra={"plugin_id": "widget_test", "operation": "widget_test", "phase": "canvas_ready"},
    )

    return root


__all__ = ["build_canvas_section", "delete_selected_vertex_from_shortcut"]
