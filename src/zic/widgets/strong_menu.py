from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QMenu


class StrongMenu(QMenu):
    def mouseReleaseEvent(self, event: QEvent) -> None:
        event.ignore()
