# src/datalens/ui/widgets/core/slider_option.py
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QStyle, QToolButton, QWidget

from datalens.ui.theme.app_theme import AppTheme


class DatalensSlider(QSlider):
    """
    Simple horizontal slider with default Qt styling for DataLens V2.

    This is a plain QSlider without any custom styling - uses Qt's default look.
    For a full-featured slider with value display and reset button, use DatalensSliderOption.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(Qt.Horizontal, parent)


class DatalensSliderOption(QWidget):
    """
    Simple slider control with value label and reset button.

    DEPRECATED: This widget uses the old V1 styled slider.
    For new code, use plain QSlider with a QLabel for the value display.
    This is kept for backward compatibility with the capture plugin.

    Features:
    - Value label (auto-formatted to step precision)
    - Reset-to-default icon button
    - Plain QSlider (no custom styling)
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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Use plain QSlider - no custom styling
        self._slider = QSlider(Qt.Horizontal, self)
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

        self._update_label(self._slider.value())
        self._update_reset_button_state()

    def _apply_theme(self) -> None:
        """Deprecated: No longer applies custom styling."""
        pass

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
        """Deprecated: No longer applies custom colors."""
        pass

    def _update_reset_button_state(self) -> None:
        if not self.isEnabled():
            self._reset_button.setEnabled(False)
            return
        distance = abs(self.value() - float(self._default))
        self._reset_button.setEnabled(bool(distance > self._epsilon))


__all__ = ["DatalensSlider", "DatalensSliderOption"]
