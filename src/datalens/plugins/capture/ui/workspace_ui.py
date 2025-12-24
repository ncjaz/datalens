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
    title.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {theme.text_color};")
    controls_layout.addWidget(title)

    device_group = QGroupBox("Device", controls)
    device_layout = QFormLayout(device_group)
    device_layout.setContentsMargins(12, 12, 12, 12)
    device_layout.setHorizontalSpacing(12)
    device_layout.setVerticalSpacing(8)
    device_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

    self._device_combo = QComboBox(device_group)
    self._device_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
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

    self._scan_mode_toggle = Toggle(
        theme,
        ToggleOption("manual", "Manual"),
        ToggleOption("auto", "Auto"),
        exclusive=True,
        parent=device_group,
    )
    self._scan_mode_toggle.set_size("small")
    self._scan_mode_toggle.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    self._scan_mode_toggle.apply_theme(theme)
    self._scan_mode_toggle.set_current_id("manual", emit=False)
    self._scan_mode_toggle.setObjectName("Capture:ScanModeToggle")
    self._scan_mode_toggle.selectionChanged.connect(lambda mode: self._on_scan_mode_changed(str(mode)))
    device_layout.addRow("Scanning", self._scan_mode_toggle)

    self._rs_format_label = QLabel("RGB Format", device_group)
    self._rs_format_combo = QComboBox(device_group)
    self._rs_format_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    self._rs_format_combo.currentIndexChanged.connect(lambda *_: self._on_rs_format_changed())
    device_layout.addRow(self._rs_format_label, self._rs_format_combo)

    self._rs_resolution_label = QLabel("Resolution", device_group)
    self._rs_resolution_combo = QComboBox(device_group)
    self._rs_resolution_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    self._rs_resolution_combo.currentIndexChanged.connect(lambda *_: self._on_rs_resolution_changed())
    device_layout.addRow(self._rs_resolution_label, self._rs_resolution_combo)

    self._rs_fps_label = QLabel("Frame Rate", device_group)
    self._rs_fps_combo = QComboBox(device_group)
    self._rs_fps_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    self._rs_fps_combo.currentIndexChanged.connect(lambda *_: self._on_rs_fps_changed())
    device_layout.addRow(self._rs_fps_label, self._rs_fps_combo)

    self._rs_depth_label = QLabel("Depth Sensor", device_group)
    self._rs_depth_toggle = Toggle(
        theme,
        ToggleOption("disabled", "Disabled"),
        ToggleOption("enabled", "Enabled"),
        exclusive=True,
        parent=device_group,
    )
    self._rs_depth_toggle.set_size("small")
    self._rs_depth_toggle.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    self._rs_depth_toggle.apply_theme(theme)
    self._rs_depth_toggle.set_current_id("disabled", emit=False)
    self._rs_depth_toggle.selectionChanged.connect(lambda *_: self._on_depth_stream_toggled())
    device_layout.addRow(self._rs_depth_label, self._rs_depth_toggle)

    self._rs_depth_align_label = QLabel("Depth Alignment", device_group)
    self._rs_depth_align_toggle = Toggle(
        theme,
        ToggleOption("aligned", "Aligned to RGB"),
        ToggleOption("standard", "Standard"),
        exclusive=True,
        parent=device_group,
    )
    self._rs_depth_align_toggle.set_size("small")
    self._rs_depth_align_toggle.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    self._rs_depth_align_toggle.apply_theme(theme)
    self._rs_depth_align_toggle.set_current_id("aligned", emit=False)
    self._rs_depth_align_toggle.selectionChanged.connect(lambda *_: self._on_depth_alignment_changed())
    device_layout.addRow(self._rs_depth_align_label, self._rs_depth_align_toggle)

    for w in (
        self._rs_format_label,
        self._rs_format_combo,
        self._rs_resolution_label,
        self._rs_resolution_combo,
        self._rs_fps_label,
        self._rs_fps_combo,
        self._rs_depth_label,
        self._rs_depth_toggle,
        self._rs_depth_align_label,
        self._rs_depth_align_toggle,
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
    self._output_dir_edit.editingFinished.connect(lambda *_: self._on_output_dir_changed())

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
    # Make toggle more compact (V1-style sizing: less prominent, more widget-like)
    self._save_formats.set_size("small")
    self._save_formats.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Don't stretch
    self._save_formats.apply_theme(theme)
    self._save_formats.set_checked("rgb", True, emit=False)
    self._save_formats.set_checked("depth", False, emit=False)
    self._save_formats.setObjectName("Capture:SaveFormatsToggle")
    self._save_formats.optionToggled.connect(lambda opt_id, checked: self._on_save_format_toggled(str(opt_id), bool(checked)))

    save_layout.addRow("Formats", self._save_formats)

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
        ToggleOption("overlay", "Overlay"),
        ToggleOption("depth", "Depth"),
        exclusive=True,
        parent=stream_row,
    )
    # Make toggle more compact (V1-style sizing: less prominent, more widget-like)
    self._stream_mode_toggle.set_size("tiny")
    self._stream_mode_toggle.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Don't stretch
    self._stream_mode_toggle.apply_theme(theme)
    self._stream_mode_toggle.setObjectName("Capture:StreamModeToggle")
    self._stream_mode_toggle.selectionChanged.connect(lambda mode: self._set_stream_mode(str(mode)))
    self._stream_mode_toggle.set_current_id("rgb", emit=False)

    stream_row_layout.addWidget(stream_label, 0)
    stream_row_layout.addWidget(self._stream_mode_toggle, 0)  # Changed from 1 to 0 to not stretch
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

    # Container for all settings (title will change based on mode)
    self._settings_container = QWidget(controls)
    settings_container_layout = QVBoxLayout(self._settings_container)
    settings_container_layout.setContentsMargins(0, 0, 0, 0)
    settings_container_layout.setSpacing(8)

    # Depth Settings Group (collapsible, secondary accent color background)
    self._depth_settings_group = QGroupBox("Depth Settings", self._settings_container)
    self._depth_settings_group.setCheckable(True)
    self._depth_settings_group.setChecked(True)
    # Apply secondary accent color background with low opacity for visual distinction
    depth_bg = theme.with_alpha_hex(theme.secondary_color, 0.2)
    self._depth_settings_group.setStyleSheet(f"QGroupBox {{ background-color: {depth_bg}; }}")
    depth_settings_layout = QVBoxLayout(self._depth_settings_group)
    depth_settings_layout.setContentsMargins(12, 12, 12, 12)
    depth_settings_layout.setSpacing(8)

    self._depth_options_scroll = QScrollArea(self._depth_settings_group)
    self._depth_options_scroll.setWidgetResizable(True)
    self._depth_options_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self._depth_options_scroll.setFrameShape(QFrame.NoFrame)

    self._depth_options_widget = QWidget(self._depth_options_scroll)
    self._depth_options_layout = QFormLayout(self._depth_options_widget)
    self._depth_options_layout.setContentsMargins(0, 0, 0, 0)
    self._depth_options_layout.setHorizontalSpacing(12)
    self._depth_options_layout.setVerticalSpacing(8)
    self._depth_options_scroll.setWidget(self._depth_options_widget)
    depth_settings_layout.addWidget(self._depth_options_scroll, 1)

    settings_container_layout.addWidget(self._depth_settings_group, 1)
    self._depth_settings_group.setVisible(False)

    # RGB Settings Group (collapsible, tertiary accent color background)
    self._rgb_settings_group = QGroupBox("RGB Settings", self._settings_container)
    self._rgb_settings_group.setCheckable(True)
    self._rgb_settings_group.setChecked(True)
    # Apply tertiary accent color background with low opacity for visual distinction
    rgb_bg = theme.with_alpha_hex(theme.tertiary_color, 0.2)
    self._rgb_settings_group.setStyleSheet(f"QGroupBox {{ background-color: {rgb_bg}; }}")
    rgb_settings_layout = QVBoxLayout(self._rgb_settings_group)
    rgb_settings_layout.setContentsMargins(12, 12, 12, 12)
    rgb_settings_layout.setSpacing(8)

    self._rgb_options_scroll = QScrollArea(self._rgb_settings_group)
    self._rgb_options_scroll.setWidgetResizable(True)
    self._rgb_options_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self._rgb_options_scroll.setFrameShape(QFrame.NoFrame)

    self._rgb_options_widget = QWidget(self._rgb_options_scroll)
    self._rgb_options_layout = QFormLayout(self._rgb_options_widget)
    self._rgb_options_layout.setContentsMargins(0, 0, 0, 0)
    self._rgb_options_layout.setHorizontalSpacing(12)
    self._rgb_options_layout.setVerticalSpacing(8)
    self._rgb_options_scroll.setWidget(self._rgb_options_widget)
    rgb_settings_layout.addWidget(self._rgb_options_scroll, 1)

    settings_container_layout.addWidget(self._rgb_settings_group, 1)

    self._rs_option_widgets = {}
    controls_layout.addWidget(self._settings_container, 1)

    computed_width = auto_size_layout(controls_layout, controls, scale=1.15)
    controls_scroll.setMinimumWidth(computed_width + 20)

    splitter.addWidget(preview_group)
    splitter.addWidget(controls_scroll)
    splitter.setStretchFactor(0, 3)
    splitter.setStretchFactor(1, 1)

    root.addWidget(splitter, 1)


__all__ = ["CaptureWorkspaceUi", "build"]
