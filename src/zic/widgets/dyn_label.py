from typing import Callable

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QLabel


class DynLabel(QLabel):
    def __init__(self, factory: Callable[[], str], prefix: str = "") -> None:
        super().__init__()
        self.factory = factory
        self.prefix = prefix

    def showEvent(self, _: QEvent) -> None:
        self.setText(f"{self.prefix}{self.factory()}")
