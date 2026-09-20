from PySide6.QtWidgets import QFrame

from typing import Any


class HRule(QFrame):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setObjectName("Separator")
        self.setFrameShape(QFrame.HLine)


class VRule(QFrame):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setObjectName("Separator")
        self.setFrameShape(QFrame.VLine)
