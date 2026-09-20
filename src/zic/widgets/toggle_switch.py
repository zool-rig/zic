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
        painter.setBrush(QColor("#c5dd6f" if self.checked else "#588591"))
        painter.drawRect(2, 2, 40, 20)

        # Background border
        painter.setPen(QPen(QColor("#262624"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(2, 2, 40, 20)

        # Cursor
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#95aa49" if self.checked else "#79afbd"))
        pos_x = 25 if self.checked else 5
        painter.drawRect(pos_x, 5, 14, 14)

        # Cursor border
        painter.setPen(QPen(QColor("#262624"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(pos_x, 5, 14, 14)

        return super().paintEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
            self.update()
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
