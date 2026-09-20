from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from typing import Callable


class DynLabel(QLabel):
    def __init__(self, factory: Callable[[], str], prefix: str = "") -> None:
        super().__init__()
        self.factory = factory
        self.prefix = prefix

    def showEvent(self, _: QEvent) -> None:
        self.setText(f"{self.prefix}{self.factory()}")
