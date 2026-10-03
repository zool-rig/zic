from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class _ToggleSwitch(QFrame):
    toggled = Signal(bool)
    clicked = Signal()

    def __init__(self, checked: bool = False) -> None:
        super().__init__()
        self._checked = checked
        self.setFixedSize(44, 24)

    @property
    def checked(self) -> bool:
        return self._checked

    @checked.setter
    def checked(self, checked: bool) -> None:
        self._checked = checked
        self.update()
        self.toggled.emit(checked)

    def is_checked(self) -> bool:
        return self.checked

    def set_checked(self, checked: bool) -> None:
        self.checked = checked

    def toggle(self) -> None:
        self.checked = not self.checked

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # Background
        painter.setBrush(QColor("#00BFAE" if self.checked else "#151B24"))
        painter.drawRoundedRect(2, 2, 40, 20, 6, 6)

        # Background border
        painter.setPen(QPen(QColor("#2A3342"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(2, 2, 40, 20, 6, 6)

        # Cursor
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#35F0E0" if self.checked else "#1C2330"))
        pos_x = 25 if self.checked else 5
        painter.drawRoundedRect(pos_x, 5, 14, 14, 4, 4)

        # Cursor border
        painter.setPen(QPen(QColor("#2A3342"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(pos_x, 5, 14, 14, 4, 4)

        return super().paintEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
            self.clicked.emit()
        return super().mousePressEvent(event)


class ToggleSwitch(QWidget):
    toggled = Signal(bool)
    clicked = Signal()

    def __init__(self, label: str = "", checked: bool = False) -> None:
        super().__init__()
        self.switch = _ToggleSwitch(checked)
        self.label_widget = QLabel(label)
        self._layout = QHBoxLayout()
        self._layout.addWidget(self.label_widget)
        self._layout.addWidget(self.switch)
        self._layout.setContentsMargins(2, 0, 0, 0)
        self.setLayout(self._layout)

        self.switch.toggled.connect(self.toggled.emit)
        self.switch.clicked.connect(self.clicked.emit)

    @property
    def checked(self) -> bool:
        return self.switch.checked

    @checked.setter
    def checked(self, checked: bool) -> None:
        self.switch.checked = checked

    def is_checked(self) -> bool:
        return self.switch.is_checked()

    def set_checked(self, checked: bool) -> None:
        self.switch.set_checked(checked)

    def toggle(self) -> None:
        self.switch.toggle()

    def get_label(self) -> str:
        return self.label_widget.text()

    @property
    def label(self) -> str:
        return self.get_label()
