from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from datalens.ui.theme.app_theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton
from datalens.ui.widgets.core.checkboxes import DatalensCheckBox
from datalens.ui.widgets.core.icon_button import create_icon_button
from datalens.ui.widgets.core.splitter import DatalensResizableSplitter
from datalens.ui.widgets.core.toggle import Toggle, ToggleOption
from datalens.ui.widgets.icons.refresh_icon import refresh_icon
from datalens.ui.widgets.layouts import auto_size_form_layout, auto_size_layout


class CaptureWorkspaceUi(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

    def build_ui(self, *, theme: AppTheme) -> None:
        build(self, theme=theme)


def build(self, *, theme: AppTheme) -> None:
    root = QVBoxLayout(self)
    root.setContentsMargins(18, 18, 18, 18)
    root.setSpacing(0)

    splitter = DatalensResizableSplitter(
        orientation=Qt.Horizontal,
        theme=theme,
        plugin_id="capture",
        state_key="workspace_splitter",
        parent=self,
    )

    preview_group = QGroupBox("Camera Preview", splitter)
    preview_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    preview_group.setMinimumWidth(320)
    preview_group_layout = QVBoxLayout(preview_group)
    preview_group_layout.setContentsMargins(10, 10, 10, 10)
    preview_group_layout.setSpacing(10)

    self._preview_frame = QFrame(preview_group)
    self._preview_frame.setObjectName("CapturePreviewFrame")
    self._preview_frame.setFrameShape(QFrame.NoFrame)
    preview_layout = QVBoxLayout(self._preview_frame)
    preview_layout.setContentsMargins(10, 10, 10, 10)
    preview_layout.setSpacing(10)

    self._preview_label = QLabel("No camera connected", self._preview_frame)
    self._preview_label.setAlignment(Qt.AlignCenter)
    self._preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    self._preview_label.setScaledContents(False)
    self._preview_label.setMinimumHeight(360)
    self._preview_label.setMinimumWidth(300)
    preview_layout.addWidget(self._preview_label, 1)
    preview_group_layout.addWidget(self._preview_frame, 1)

    controls_scroll = QScrollArea(splitter)
    controls_scroll.setObjectName("CaptureControlsScroll")
    controls_scroll.setWidgetResizable(True)
    controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    controls_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    controls_scroll.setFrameShape(QFrame.NoFrame)
    controls_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    controls = QWidget(controls_scroll)
    controls_scroll.setWidget(controls)

    controls_layout = QVBoxLayout(controls)
    controls_layout.setContentsMargins(0, 0, 0, 0)
    controls_layout.setSpacing(12)

    title = QLabel("Capture", controls)
    title.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {theme.settings.text_color};")
    controls_layout.addWidget(title)

    device_group = QGroupBox("Device", controls)
    device_layout = QFormLayout(device_group)
    device_layout.setContentsMargins(12, 12, 12, 12)
    device_layout.setHorizontalSpacing(12)
    device_layout.setVerticalSpacing(8)
    device_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

    self._device_combo = QComboBox(device_group)
    self._device_combo.currentIndexChanged.connect(lambda *_: self._on_device_selected())

    self._refresh_btn = create_icon_button(
        theme,
        device_group,
        checkable=True,
    )
    self._refresh_btn.setObjectName("CaptureRefreshButton")
    self._refresh_btn.setIcon(refresh_icon(theme, size=18))
    self._refresh_btn.setChecked(False)

    camera_row = QWidget(device_group)
    camera_row_layout = QHBoxLayout(camera_row)
    camera_row_layout.setContentsMargins(0, 0, 0, 0)
    camera_row_layout.setSpacing(6)
    camera_row_layout.addWidget(self._device_combo, 1)
    camera_row_layout.addWidget(self._refresh_btn, 0, alignment=Qt.AlignVCenter)

    device_layout.addRow("Camera", camera_row)

    self._rs_format_label = QLabel("RGB Format", device_group)
    self._rs_format_combo = QComboBox(device_group)
    self._rs_format_combo.currentIndexChanged.connect(lambda *_: self._on_rs_format_changed())
    device_layout.addRow(self._rs_format_label, self._rs_format_combo)

    self._rs_resolution_label = QLabel("Resolution", device_group)
    self._rs_resolution_combo = QComboBox(device_group)
    self._rs_resolution_combo.currentIndexChanged.connect(lambda *_: self._on_rs_resolution_changed())
    device_layout.addRow(self._rs_resolution_label, self._rs_resolution_combo)

    self._rs_fps_label = QLabel("Frame Rate", device_group)
    self._rs_fps_combo = QComboBox(device_group)
    self._rs_fps_combo.currentIndexChanged.connect(lambda *_: self._on_rs_fps_changed())
    device_layout.addRow(self._rs_fps_label, self._rs_fps_combo)

    self._rs_depth_label = QLabel("Depth Sensor", device_group)
    self._rs_depth_checkbox = DatalensCheckBox("Enable depth stream", theme, device_group)
    self._rs_depth_checkbox.setChecked(False)
    self._rs_depth_checkbox.toggled.connect(lambda *_: self._on_depth_stream_toggled())
    device_layout.addRow(self._rs_depth_label, self._rs_depth_checkbox)

    for w in (
        self._rs_format_label,
        self._rs_format_combo,
        self._rs_resolution_label,
        self._rs_resolution_combo,
        self._rs_fps_label,
        self._rs_fps_combo,
        self._rs_depth_label,
        self._rs_depth_checkbox,
    ):
        w.setVisible(False)

    auto_size_form_layout(device_layout, device_group, scale=1.15)
    controls_layout.addWidget(device_group)

    save_group = QGroupBox("Save", controls)
    save_layout = QFormLayout(save_group)
    save_layout.setContentsMargins(12, 12, 12, 12)
    save_layout.setHorizontalSpacing(12)
    save_layout.setVerticalSpacing(8)
    save_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

    self._output_dir_edit = QLineEdit(save_group)
    self._output_dir_edit.setPlaceholderText("Choose a folder to save captures")
    self._output_dir_edit.setClearButtonEnabled(True)

    self._browse_output_btn = DatalensButton("Browse…", theme, ButtonVariant.SECONDARY, save_group)
    self._browse_output_btn.clicked.connect(lambda *_: self._browse_output_dir())

    output_row = QWidget(save_group)
    output_row_layout = QHBoxLayout(output_row)
    output_row_layout.setContentsMargins(0, 0, 0, 0)
    output_row_layout.setSpacing(8)
    output_row_layout.addWidget(self._output_dir_edit, 1)
    output_row_layout.addWidget(self._browse_output_btn, 0)

    save_layout.addRow("Folder", output_row)

    self._save_formats = Toggle(
        theme,
        ToggleOption("rgb", "RGB"),
        ToggleOption("depth", "Depth"),
        exclusive=False,
        parent=save_group,
    )
    self._save_formats.set_checked("rgb", True, emit=False)
    self._save_formats.set_checked("depth", False, emit=False)
    self._save_formats.optionToggled.connect(lambda *_: self._refresh_controls())

    save_layout.addRow("Formats", self._save_formats)

    hint = QLabel(
        "Creates `rgb/` and `depth/` folders on the first capture.\n"
        "If a project is open and the folder is inside the project root, files are registered into the media index.",
        save_group,
    )
    hint.setWordWrap(True)
    hint.setStyleSheet(f"color: {theme.with_alpha_hex(theme.settings.text_color, 0.70)}; font-size: 11px;")
    save_layout.addRow("", hint)

    auto_size_form_layout(save_layout, save_group, scale=1.15)
    controls_layout.addWidget(save_group)

    capture_group = QGroupBox("Capture", controls)
    capture_layout = QVBoxLayout(capture_group)
    capture_layout.setContentsMargins(12, 12, 12, 12)
    capture_layout.setSpacing(10)

    stream_row = QWidget(capture_group)
    stream_row_layout = QHBoxLayout(stream_row)
    stream_row_layout.setContentsMargins(0, 0, 0, 0)
    stream_row_layout.setSpacing(10)

    stream_label = QLabel("Stream", stream_row)
    self._stream_mode = "rgb"
    self._stream_mode_toggle = Toggle(
        theme,
        ToggleOption("rgb", "RGB"),
        ToggleOption("depth", "Depth"),
        exclusive=True,
        parent=stream_row,
    )
    self._stream_mode_toggle.selectionChanged.connect(lambda mode: self._set_stream_mode(str(mode)))
    self._stream_mode_toggle.set_current_id("rgb", emit=False)

    stream_row_layout.addWidget(stream_label, 0)
    stream_row_layout.addWidget(self._stream_mode_toggle, 1)
    capture_layout.addWidget(stream_row)

    self._start_stop = DatalensButton("Start", theme, ButtonVariant.CONFIRM, capture_group)
    self._start_stop.clicked.connect(lambda *_: self._on_start_stop_clicked())
    self._start_stop_variant = ButtonVariant.CONFIRM

    self._capture_btn = DatalensButton("Capture", theme, ButtonVariant.PRIMARY, capture_group)
    self._capture_btn.clicked.connect(lambda *_: self._on_capture_clicked())

    buttons_row = QHBoxLayout()
    buttons_row.setSpacing(10)
    buttons_row.addWidget(self._start_stop, 1)
    buttons_row.addWidget(self._capture_btn, 1)
    capture_layout.addLayout(buttons_row)

    auto_size_layout(capture_layout, capture_group, scale=1.15)
    controls_layout.addWidget(capture_group)

    self._settings_group = QGroupBox("RGB Settings", controls)
    self._settings_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    settings_group_layout = QVBoxLayout(self._settings_group)
    settings_group_layout.setContentsMargins(12, 12, 12, 12)
    settings_group_layout.setSpacing(10)

    self._rgb_options_scroll = QScrollArea(self._settings_group)
    self._rgb_options_scroll.setWidgetResizable(True)
    self._rgb_options_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self._rgb_options_scroll.setFrameShape(QFrame.NoFrame)

    self._rgb_options_widget = QWidget(self._rgb_options_scroll)
    self._rgb_options_layout = QFormLayout(self._rgb_options_widget)
    self._rgb_options_layout.setContentsMargins(0, 0, 0, 0)
    self._rgb_options_layout.setHorizontalSpacing(12)
    self._rgb_options_layout.setVerticalSpacing(8)
    self._rgb_options_scroll.setWidget(self._rgb_options_widget)

    self._depth_options_scroll = QScrollArea(self._settings_group)
    self._depth_options_scroll.setWidgetResizable(True)
    self._depth_options_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self._depth_options_scroll.setFrameShape(QFrame.NoFrame)

    self._depth_options_widget = QWidget(self._depth_options_scroll)
    self._depth_options_layout = QFormLayout(self._depth_options_widget)
    self._depth_options_layout.setContentsMargins(0, 0, 0, 0)
    self._depth_options_layout.setHorizontalSpacing(12)
    self._depth_options_layout.setVerticalSpacing(8)
    self._depth_options_scroll.setWidget(self._depth_options_widget)

    settings_group_layout.addWidget(self._rgb_options_scroll, 1)
    settings_group_layout.addWidget(self._depth_options_scroll, 1)
    self._depth_options_scroll.setVisible(False)

    self._rs_option_widgets = {}
    controls_layout.addWidget(self._settings_group, 1)

    computed_width = auto_size_layout(controls_layout, controls, scale=1.15)
    controls_scroll.setMinimumWidth(computed_width + 20)

    splitter.addWidget(preview_group)
    splitter.addWidget(controls_scroll)
    splitter.setStretchFactor(0, 3)
    splitter.setStretchFactor(1, 1)

    root.addWidget(splitter, 1)


__all__ = ["CaptureWorkspaceUi", "build"]
