from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

import weakref

from datalens.core.logging import get_logger
from datalens.ui.canvas.canvas_widget import ImageCanvas
from datalens.ui.canvas.layers.vector_layer import VectorLayer, VectorShape, VectorStyle
from datalens.ui.canvas.tools.select_edit_tool import SelectEditTool, SelectionState
from datalens.ui.theme.app_theme import AppTheme

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
    def __init__(self, *, canvas: ImageCanvas, layer: VectorLayer, status_label: QLabel) -> None:
        self._canvas = canvas
        self._layer = layer
        self._status_label = status_label
        self._tool = SelectEditTool(vector_layer=self._layer, on_selection_changed=self._on_selection_changed)
        self._canvas.tools.set_active(self._tool)

    def _on_selection_changed(self, sel: SelectionState | None) -> None:
        if sel is None:
            self._status_label.setText("Selected: (none)")
        elif sel.vertex_index < 0:
            self._status_label.setText(f"Selected: {sel.shape_id} (shape)")
        else:
            self._status_label.setText(f"Selected: {sel.shape_id} vertex {sel.vertex_index}")
        self._canvas.update()

    def delete_selected_vertex(self) -> bool:
        changed = bool(self._tool.delete_selected_vertex())
        if changed:
            self._canvas.update()
        return changed


def _set_active_controller(ctrl: _CanvasTestController | None) -> None:
    global _ACTIVE_CONTROLLER
    _ACTIVE_CONTROLLER = weakref.ref(ctrl) if ctrl is not None else None


def build_canvas_section(parent: QWidget, *, theme: AppTheme) -> QWidget:
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

    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    layout.addLayout(row)

    canvas = ImageCanvas(root)
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

    controller = _CanvasTestController(canvas=canvas, layer=vector_layer, status_label=selection_status)
    _set_active_controller(controller)
    canvas.destroyed.connect(lambda *_: _set_active_controller(None))  # type: ignore[arg-type]

    log.info(
        "Widget test canvas initialized",
        extra={"plugin_id": "widget_test", "operation": "widget_test", "phase": "canvas_ready"},
    )

    return root


__all__ = ["build_canvas_section", "delete_selected_vertex_from_shortcut"]
