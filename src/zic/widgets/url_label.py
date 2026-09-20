from PySide6.QtWidgets import QLabel, QApplication
from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtGui import QMouseEvent


class UrlLabel(QLabel):
    clicked = Signal(str)

    def __init__(self, text: str, clickable: bool = True) -> None:
        super().__init__(text)
        self.clickable = clickable

    def enterEvent(self, _: QEvent) -> None:
        if self.clickable:
            font = self.font()
            font.setUnderline(True)
            self.setFont(font)
            QApplication.setOverrideCursor(Qt.PointingHandCursor)

    def leaveEvent(self, _: QEvent) -> None:
        if self.clickable:
            font = self.font()
            font.setUnderline(False)
            self.setFont(font)
            QApplication.restoreOverrideCursor()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.clickable:
            if event.button() == Qt.LeftButton:
                self.clicked.emit(self.text())
