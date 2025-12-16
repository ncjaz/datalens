from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QToolButton, QVBoxLayout, QFrame, QWidget

from datalens.domain.user_profile import UserProfile
from datalens.ui.theme import AppTheme
from datalens.ui.widgets.core.buttons import ButtonVariant, DatalensButton
from datalens.ui.widgets.icons.settings_icon import settings_icon


class ProfileSummary(QFrame):
    """Compact summary row mirroring the V1 welcome profile prompt."""

    editRequested = Signal()

    def __init__(self, theme: AppTheme, profile: UserProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("profileSummary")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(6)

        self._label = QLabel(self)
        self._label.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(self._label, 1)

        self._edit_button = QToolButton(self)
        self._edit_button.setCursor(Qt.PointingHandCursor)
        self._edit_button.setIcon(settings_icon(theme))
        self._edit_button.setIconSize(QSize(24, 24))
        self._edit_button.setToolTip("Edit profile")
        self._edit_button.clicked.connect(self.editRequested.emit)
        layout.addWidget(self._edit_button, 0, Qt.AlignRight)

        self._apply_theme()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.set_profile(profile)

    def set_profile(self, profile: UserProfile) -> None:
        name = profile.normalized().name
        if name:
            self._label.setText(f"Welcome {name}")
        else:
            self._label.setText("Welcome")

    def _apply_theme(self) -> None:
        border = self._theme.with_alpha_hex(self._theme.primary_color, 0.28)
        background = self._theme.with_alpha_hex(self._theme.secondary_color, 0.32)
        self.setStyleSheet(
            "QFrame#profileSummary {"
            f"background-color: {background};"
            f"border: 1px solid {border};"
            "border-radius: 14px;"
            "}"
            "QFrame#profileSummary QLabel {"
            "background-color: transparent;"
            "}"
        )

        base = self._theme.with_alpha_hex(self._theme.primary_color, 0.18)
        hover = self._theme.with_alpha_hex(self._theme.primary_color, 0.30)
        pressed = self._theme.with_alpha_hex(self._theme.primary_color, 0.42)
        disabled = self._theme.with_alpha_hex(self._theme.secondary_color, 0.25)
        self._edit_button.setStyleSheet(
            "QToolButton {"
            f"background-color: {base};"
            "border: none;"
            "border-radius: 14px;"
            "padding: 3px;"
            "}"
            "QToolButton:hover:!disabled {"
            f"background-color: {hover};"
            "}"
            "QToolButton:pressed {"
            f"background-color: {pressed};"
            "}"
            "QToolButton:disabled {"
            f"background-color: {disabled};"
            "}"
        )


class ProfileEditDialog(QDialog):
    """Lightweight dialog for updating the stored user profile."""

    def __init__(self, theme: AppTheme, profile: UserProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setWindowTitle("Edit profile")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Update your details", self)
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        name_edit = QLineEdit(self)
        name_edit.setPlaceholderText("Name")
        name_edit.setText(profile.normalized().name)
        self._name_edit = name_edit
        layout.addWidget(name_edit)

        email_edit = QLineEdit(self)
        email_edit.setPlaceholderText("Email")
        email_edit.setText(profile.normalized().email)
        self._email_edit = email_edit
        layout.addWidget(email_edit)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addStretch(1)

        save_button = DatalensButton("Save", theme, ButtonVariant.CONFIRM, self)
        save_button.clicked.connect(self.accept)
        button_row.addWidget(save_button)

        cancel_button = DatalensButton("Cancel", theme, ButtonVariant.CANCEL, self)
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)

        layout.addLayout(button_row)

    def profile(self) -> UserProfile:
        return UserProfile(
            name=self._name_edit.text(),
            email=self._email_edit.text(),
        ).normalized()

