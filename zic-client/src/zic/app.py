import importlib.metadata

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *


class ZicUI(QDialog):
    def __init__(self) -> None:
        super().__init__()

        # Layouts

        # Widgets

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()
        self.set_style_sheet()

        # timer = QTimer(self)
        # timer.timeout.connect(self.set_style_sheet)
        # timer.start(1000)

    def init_layouts(self) -> None:
        pass

    def init_widgets(self) -> None:
        pass

    def set_layout(self) -> None:
        pass

    def set_connections(self) -> None:
        pass

    def set_default(self) -> None:
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle(f"ZIC - {importlib.metadata.version("zic-client")}")

    def set_style_sheet(self) -> None:
        pass
