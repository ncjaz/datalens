from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from datalens.ui.theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton
from datalens.ui.widgets.icons.animated.spinner import DualRingSpinner


class LoaderDialog(QDialog):
    """
    Small frameless loader dialog used for non-blocking startup/background tasks.

    This is the UI counterpart to :func:`datalens.infra.background.loader_runner.run_with_loader`.

    Public slots:
    - ``append_message(text)``: append a new status line
    - ``set_progress(value)``: set progress (0..1)
    """

    def __init__(
        self,
        *,
        title: str = "Loading…",
        header_text: str = "DataLens",
        subtitle_text: str = "Data Viewer, Collection & Annotation",
        title_point_size: int = 20,
        subtitle_point_size: int = 11,
        spinner_size: int | None = 60,
        theme: AppTheme,
        parent: QWidget | None = None,
        max_messages: int = 4,
    ) -> None:
        flags = Qt.Dialog | Qt.FramelessWindowHint
        if parent is None:
            flags |= Qt.WindowStaysOnTopHint
        super().__init__(parent, flags)

        self._theme = theme
        self._messages: deque[str] = deque(maxlen=max(1, int(max_messages)))
        self._message_labels: list[QLabel] = []
        self._error_text: str | None = None

        self.setWindowTitle(title)
        if parent is None:
            self.setModal(False)
        else:
            self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self._card = QFrame(self)
        self._card.setObjectName("LoaderCard")
        self._card.setMinimumWidth(420)
        self._card.setMinimumHeight(420)
        root_layout.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(28, 32, 28, 28)
        card_layout.setSpacing(18)

        self._title = QLabel(header_text, self._card)
        self._title.setObjectName("LoaderTitle")
        title_font = QFont()
        title_font.setPointSize(max(1, int(title_point_size)))
        title_font.setBold(True)
        self._title.setFont(title_font)
        self._title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self._title)

        self._subtitle = QLabel(subtitle_text, self._card)
        self._subtitle.setObjectName("LoaderSubtitle")
        subtitle_font = QFont()
        subtitle_font.setPointSize(max(1, int(subtitle_point_size)))
        self._subtitle.setFont(subtitle_font)
        self._subtitle.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self._subtitle)

        self._spinner = DualRingSpinner(self._theme, self._card)
        if spinner_size is not None:
            size = max(1, int(spinner_size))
            self._spinner.setFixedSize(size, size)
            dialog_size = max(420, size + 300)
            self._card.setMinimumSize(dialog_size, dialog_size)
            self.setMinimumSize(dialog_size, dialog_size)
        self._spinner.start()
        card_layout.addWidget(self._spinner, alignment=Qt.AlignCenter)

        for _ in range(max(1, int(max_messages))):
            label = QLabel("", self._card)
            label.setObjectName("LoaderMessage")
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)
            self._message_labels.append(label)
            card_layout.addWidget(label)

        self._progress = QProgressBar(self._card)
        self._progress.setObjectName("LoaderProgress")
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.hide()
        card_layout.addWidget(self._progress)

        self._error = QLabel("", self._card)
        self._error.setObjectName("LoaderError")
        self._error.setWordWrap(True)
        self._error.setAlignment(Qt.AlignCenter)
        self._error.hide()
        card_layout.addWidget(self._error)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(10)
        actions_row.addStretch(1)
        card_layout.addLayout(actions_row)

        self._copy_error = DatalensButton("Copy error", self._theme, ButtonVariant.SECONDARY, self._card)
        self._copy_error.clicked.connect(self.copy_error_to_clipboard)
        self._copy_error.hide()
        actions_row.addWidget(self._copy_error)

        self._close_button = DatalensButton("Close", self._theme, ButtonVariant.CANCEL, self._card)
        self._close_button.clicked.connect(self.close)
        self._close_button.hide()
        actions_row.addWidget(self._close_button)

        if hasattr(self._theme, "theme_changed"):
            try:
                self._theme.theme_changed.connect(self._apply_theme)
            except Exception:
                pass

        self._apply_theme()
        if spinner_size is not None:
            size = max(1, int(spinner_size))
            dialog_size = max(420, size + 300)
            self.resize(dialog_size, dialog_size)
        else:
            self.resize(420, 420)

    def _apply_theme(self) -> None:
        t = self._theme

        bg = t.with_alpha_hex(t.secondary_color, 0.94)
        border = t.with_alpha_hex(t.tertiary_color, 0.90)
        subtitle = t.with_alpha_hex(t.text_color, 0.75)

        self._card.setStyleSheet(
            f"""
            QFrame#LoaderCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 20px;
            }}
            QLabel#LoaderTitle {{
                color: {t.text_color};
                letter-spacing: 1px;
            }}
            QLabel#LoaderSubtitle {{
                color: {subtitle};
                font-size: 11px;
            }}
            QLabel#LoaderError {{
                color: {t.cancel_color};
                font-size: 12px;
            }}
            QLabel#LoaderMessage {{
                font-size: 11px;
            }}
            QProgressBar#LoaderProgress {{
                background-color: {t.subtle_fill(t.secondary_color)};
                border: 1px solid {border};
                border-radius: 6px;
                height: 10px;
            }}
            QProgressBar#LoaderProgress::chunk {{
                background-color: {t.primary_color};
                border-radius: 6px;
            }}
            """
        )
        self._refresh_messages()

    def append_message(self, text: str) -> None:
        """
        Append a message line to the dialog.

        Safe to call from the UI thread. (Background callers must route through
        Qt signals; :class:`LoaderWorker` already does this.)
        """
        message = (text or "").strip()
        if not message:
            return

        self._messages.appendleft(message)
        self._refresh_messages()

    def _refresh_messages(self) -> None:
        t = self._theme
        fade_steps = [1.0, 0.72, 0.48, 0.25]
        for index, label in enumerate(self._message_labels):
            if index < len(self._messages):
                label.setText(self._messages[index])
                opacity = fade_steps[index] if index < len(fade_steps) else 0.25
                label.setStyleSheet(
                    f"font-size: 11px; color: {t.with_alpha_hex(t.text_color, opacity)};"
                )
            else:
                label.setText("")

    def set_progress(self, value: float) -> None:
        """
        Set progress from 0..1 (float).

        If the task never calls progress, the bar remains hidden.
        """
        try:
            v = float(value)
        except Exception:
            return

        if v <= 1.0:
            percent = int(max(0.0, min(1.0, v)) * 100)
        else:
            percent = int(max(0.0, min(100.0, v)))

        if not self._progress.isVisible():
            self._progress.show()

        self._progress.setValue(percent)

    def show_error(self, text: str) -> None:
        self._error_text = text
        self._error.setText(text)
        self._error.show()
        self._close_button.show()
        self._copy_error.show()

    def error_text(self) -> str | None:
        return self._error_text

    def copy_error_to_clipboard(self) -> None:
        if not self._error_text:
            return
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                return
            clipboard = app.clipboard()
            clipboard.setText(self._error_text)
        except Exception:
            return

    def closeEvent(self, event) -> None:
        try:
            self._spinner.stop()
        except Exception:
            pass
        super().closeEvent(event)
