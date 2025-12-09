"""
Loader Dialog
=============

This module implements :class:`LoaderDialog`, the themed dialog used during
long-running operations triggered by :func:`run_with_loader`.

The dialog displays:

- An animated spinner (DualRingSpinner)
- A title describing the operation
- An auto-scrolling text log area
- Optional progress updates

The dialog itself performs no background work. Instead, it reacts to signals
emitted by :class:`LoaderWorker` and updates the UI accordingly.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QWidget,
    QSizePolicy,
)

from datalens.ui.widgets.icons.animated.spinner import DualRingSpinner
from datalens.ui.theme.app_theme import AppTheme

logger = logging.getLogger("datalens.loader")


class LoaderDialog(QDialog):
    """
    A modal dialog shown while executing a long-running background task.

    The dialog presents:

    - A themed animated spinner
    - A descriptive title
    - A scrolling text log area
    - (Optional) A progress bar

    The dialog is intended to be used exclusively with
    :func:`run_with_loader`, which wires all signals from the background
    worker into this dialog.

    Parameters
    ----------
    title:
        Displayed above the text log area.
    parent:
        Parent widget for modality and window ownership.
    theme:
        Optional explicit theme. If not provided, the parent is expected to
        expose a ``theme`` attribute.
    """

    def __init__(
        self,
        title: str,
        parent: Optional[QWidget] = None,
        theme: Optional[AppTheme] = None,
    ) -> None:
        super().__init__(parent)

        # -------------------------------------------------------------- #
        # Theme resolution
        # -------------------------------------------------------------- #
        # Theme priority:
        # 1. Explicit theme argument
        # 2. Parent widget has .theme
        # 3. Hard fallback default (not ideal but safe)
        if theme is not None:
            self._theme = theme
        elif parent is not None and hasattr(parent, "theme"):
            self._theme = parent.theme  # type: ignore
        else:
            # Last resort fallback (rare)
            self._theme = AppTheme()

        self._title_text = title

        # -------------------------------------------------------------- #
        # Window behavior
        # -------------------------------------------------------------- #
        self.setWindowTitle("")  # avoid duplicated text
        self.setModal(True)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.CustomizeWindowHint
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowStaysOnTopHint
        )
        # Remove close button so user can't interrupt mid-task
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)

        self.setMinimumSize(480, 360)

        # -------------------------------------------------------------- #
        # UI Layout
        # -------------------------------------------------------------- #
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        # Spinner
        self._spinner = DualRingSpinner(theme=self._theme, parent=self)
        self._spinner.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._spinner.start()
        layout.addWidget(self._spinner, alignment=Qt.AlignHCenter)

        # Title label
        self._title_label = QLabel(self._title_text)
        self._title_label.setAlignment(Qt.AlignHCenter)
        self._apply_title_style()
        layout.addWidget(self._title_label)

        # Log area
        self._log_box = QPlainTextEdit()
        self._log_box.setReadOnly(True)
        self._apply_log_style()
        layout.addWidget(self._log_box, stretch=1)

        # Optional progress bar (inactive by default)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._apply_dialog_style()

    # ================================================================== #
    # Theme / Style Helpers
    # ================================================================== #

    def _apply_dialog_style(self) -> None:
        """
        Apply theme-based styling to the dialog background and container.
        """
        color = QColor(self._theme.secondary_color)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {color.name()};
                border-radius: 8px;
            }}
        """)

    def _apply_title_style(self) -> None:
        """
        Style for title label.
        """
        text_color = QColor(self._theme.text_color)
        self._title_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color.name()};
                font-size: 15px;
                font-weight: 600;
            }}
        """)

    def _apply_log_style(self) -> None:
        """
        Style for the log text area.
        """
        bg = QColor(self._theme.secondary_color)
        fg = QColor(self._theme.text_color)
        border = QColor(self._theme.primary_color)

        self._log_box.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {bg.name()};
                color: {fg.name()};
                border: 1px solid {border.name()};
                border-radius: 4px;
                font-size: 13px;
            }}
        """)

    # ================================================================== #
    # Public API used by LoaderWorker signals
    # ================================================================== #

    def append_message(self, text: str) -> None:
        """
        Append a log message to the text area and auto-scroll to bottom.

        This method is invoked via Qt signals from :class:`LoaderWorker`.

        Parameters
        ----------
        text:
            The log message to append.
        """
        logger.info(text)
        self._log_box.appendPlainText(text)
        self._auto_scroll()

    def _auto_scroll(self) -> None:
        """
        Scroll the log viewer to the most recent appended message.
        """
        cursor = self._log_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._log_box.setTextCursor(cursor)
        self._log_box.ensureCursorVisible()

    def set_progress(self, value: float) -> None:
        """
        Update the optional progress bar.

        Parameters
        ----------
        value:
            Progress value in the range 0–1.

        Notes
        -----
        The progress bar is shown automatically the first time this method
        is invoked.
        """
        if not self._progress_bar.isVisible():
            self._progress_bar.setVisible(True)

        self._progress_bar.setValue(int(value * 100))

    # ================================================================== #
    # Dialog cleanup
    # ================================================================== #

    def closeEvent(self, event) -> None:
        """
        Ensure the spinner stops when the dialog closes.
        """
        self._spinner.stop()
        super().closeEvent(event)
