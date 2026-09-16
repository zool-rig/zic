from PySide6.QtWidgets import QMenu
from PySide6.QtCore import QEvent


class StrongMenu(QMenu):
    def mouseReleaseEvent(self, event: QEvent) -> None:
        event.ignore()
