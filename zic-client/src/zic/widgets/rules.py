from PySide6.QtWidgets import QFrame


class HRule(QFrame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setObjectName("Separator")
        self.setFrameShape(QFrame.HLine)


class VRule(QFrame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setObjectName("Separator")
        self.setFrameShape(QFrame.VLine)
