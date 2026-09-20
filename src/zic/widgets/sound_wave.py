import random

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget


class SoundWave(QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
        color: str = "#00C8FF",
        bars: int = 25,
        bar_width: int = 3,
        spacing: int = 4,
        height: int = 40,
    ) -> None:
        super().__init__(parent)

        self.color = QColor(color)
        self.bars = bars
        self.bar_width = bar_width
        self.spacing = spacing

        self.levels = [0.2] * bars

        # Animation
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)

        self.setMinimumHeight(height)
        self.setMinimumWidth(bars * bar_width + (bars - 1) * spacing)

    def sizeHint(self) -> QSize:
        return QSize(
            self.bars * self.bar_width + (self.bars - 1) * self.spacing,
            40,
        )

    def animate(self) -> None:
        for i in range(self.bars):
            target = random.uniform(0.15, 1.0)

            self.levels[i] += (target - self.levels[i]) * 0.25

        self.update()

    def set_color(self, color: str) -> None:
        self.color = QColor(color)
        self.update()

    def paintEvent(self, _: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self.color)

        center_y = self.height() / 2

        total_width = self.bars * self.bar_width + (self.bars - 1) * self.spacing

        start_x = (self.width() - total_width) / 2

        for i, level in enumerate(self.levels):
            max_height = self.height() * 0.9
            height = max_height * level

            x = start_x + i * (self.bar_width + self.spacing)
            y = center_y - height / 2

            painter.drawRect(
                int(x),
                int(y),
                self.bar_width,
                int(height),
            )

    def start(self) -> None:
        self.timer.start(50)  # ~20 FPS

    def stop(self) -> None:
        self.timer.stop()
