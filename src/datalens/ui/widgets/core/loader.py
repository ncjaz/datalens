# src/datalens/ui/widgets/core/loader.py
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter, QPen
from datalens.ui.widgets.core.themed_widget import ThemedWidget
from datalens.ui.theme.app_theme import AppTheme

class SpinnerLoader(ThemedWidget):
    def __init__(self, theme: AppTheme, parent=None):
        super().__init__(theme, parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        self._angle = (self._angle + 5) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        pen = QPen(self.theme.primary_color(), 4)
        p.setPen(pen)
        # draw an arc based on self._angle...
