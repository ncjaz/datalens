# src/datalens/ui/widgets/core/slider_option.py
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QStyle, QToolButton, QWidget

from datalens.ui.theme.app_theme import AppTheme


class DatalensSliderOption(QWidget):
    """
    V1-style slider control used for camera/device options.

    Features:
    - Value label (auto-formatted to step precision)
    - Reset-to-default icon button
    - Themed QSlider styling (accented track + handle)
    """

    valueChanged = Signal(float)

    def __init__(
        self,
        theme: AppTheme,
        parent: QWidget,
        minimum: float,
        maximum: float,
        step: float,
        *,
        default_value: Optional[float] = None,
        accent_color: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self._step = float(step) if float(step) > 0 else (self._maximum - self._minimum) / 100.0
        if self._step == 0:
            self._step = 1.0

        if default_value is None:
            default_value = self._minimum
        self._default = max(self._minimum, min(self._maximum, float(default_value)))
        self._epsilon = max(abs(self._step) / 10.0, 1e-6)
        self._value_suffix = ""
        self._accent_color = accent_color or theme.primary_color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._slider = QSlider(Qt.Horizontal, self)
        # The V1 slider handle uses a negative vertical margin in the stylesheet to
        # create a circular "thumb" that sits above the groove. Ensure the widget
        # is tall enough so the thumb doesn't get clipped.
        self._slider.setMinimumHeight(28)
        steps = int(round((self._maximum - self._minimum) / self._step))
        steps = max(1, steps)
        self._slider.setRange(0, steps)
        self._slider.valueChanged.connect(self._on_slider_value_changed)
        layout.addWidget(self._slider, 1)

        self._value_label = QLabel(self)
        self._value_label.setMinimumWidth(60)
        self._value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._value_label)

        self._reset_button = QToolButton(self)
        self._reset_button.setAutoRaise(True)
        self._reset_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self._reset_button.setToolTip("Reset to default value")
        self._reset_button.clicked.connect(self.reset_to_default)
        layout.addWidget(self._reset_button)

        self._apply_theme()
        self._update_label(self._slider.value())
        self._update_reset_button_state()

    def _apply_theme(self) -> None:
        accent = str(self._accent_color or self._theme.primary_color)
        disabled_accent = self._theme.with_alpha_hex(accent, 0.35)

        self._slider.setStyleSheet(
            f"""
            QSlider::groove:horizontal {{
                border-radius: 4px;
                height: 8px;
                background: palette(midlight);
            }}
            QSlider::sub-page:horizontal {{
                border: none;
                background: {accent};
                border-radius: 4px;
            }}
            QSlider::sub-page:horizontal:disabled {{
                border: none;
                background: {disabled_accent};
                border-radius: 4px;
            }}
            QSlider::add-page:horizontal {{
                border: none;
                background: palette(light);
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {accent};
                border: 2px solid palette(base);
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:disabled {{
                background: {disabled_accent};
                border: 2px solid palette(base);
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            """
        )

        # Keep labels readable and consistent with theme.
        disabled_text = self._theme.with_alpha_hex(self._theme.settings.text_color, 0.45)
        self._value_label.setStyleSheet(
            f"QLabel {{ color: {self._theme.settings.text_color}; }}"
            f"QLabel:disabled {{ color: {disabled_text}; }}"
        )

    def _on_slider_value_changed(self, slider_value: int) -> None:
        self._update_label(slider_value)
        self._update_reset_button_state()
        self.valueChanged.emit(self.value())

    def _clamp_slider_value(self, slider_value: int) -> int:
        return max(0, min(self._slider.maximum(), int(slider_value)))

    def _update_label(self, slider_value: int) -> None:
        slider_value = self._clamp_slider_value(slider_value)
        value = self._minimum + slider_value * self._step
        value = max(self._minimum, min(self._maximum, value))
        self._value_label.setText(self._format_value(value))

    def _format_value(self, value: float) -> str:
        step = abs(self._step)
        if step >= 1:
            formatted = f"{value:.0f}"
        elif step >= 0.1:
            formatted = f"{value:.1f}"
        elif step >= 0.01:
            formatted = f"{value:.2f}"
        else:
            formatted = f"{value:.3f}"
        return f"{formatted}{self._value_suffix}" if self._value_suffix else formatted

    def value(self) -> float:
        slider_value = self._slider.value()
        value = self._minimum + slider_value * self._step
        return max(self._minimum, min(self._maximum, float(value)))

    def setValue(self, value: float) -> None:  # noqa: N802 - Qt naming convention
        value = max(self._minimum, min(self._maximum, float(value)))
        slider_value = int(round((value - self._minimum) / self._step))
        slider_value = self._clamp_slider_value(slider_value)
        if slider_value == self._slider.value():
            self._update_label(slider_value)
            self._update_reset_button_state()
            return
        self._slider.blockSignals(True)
        self._slider.setValue(slider_value)
        self._slider.blockSignals(False)
        self._update_label(slider_value)
        self._update_reset_button_state()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 - Qt naming convention
        super().setEnabled(enabled)
        self._slider.setEnabled(bool(enabled))
        self._value_label.setEnabled(bool(enabled))
        self._update_reset_button_state()

    def reset_to_default(self) -> None:
        self.setValue(self._default)
        self.valueChanged.emit(self.value())

    def default_value(self) -> float:
        return float(self._default)

    def set_value_suffix(self, suffix: str) -> None:
        self._value_suffix = str(suffix or "")
        self._update_label(self._slider.value())

    def set_accent_color(self, color: Optional[str]) -> None:
        self._accent_color = str(color) if color else self._theme.primary_color
        self._apply_theme()

    def _update_reset_button_state(self) -> None:
        if not self.isEnabled():
            self._reset_button.setEnabled(False)
            return
        distance = abs(self.value() - float(self._default))
        self._reset_button.setEnabled(bool(distance > self._epsilon))


__all__ = ["DatalensSliderOption"]
