from PySide6.QtWidgets import QFrame


class HRule(QFrame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setObjectName("Separator")
        self.setFrameShape(QFrame.HLine)
        self.setLineWidth(2)


class VRule(QFrame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setObjectName("Separator")
        self.setFrameShape(QFrame.VLine)
        self.setLineWidth(2)
