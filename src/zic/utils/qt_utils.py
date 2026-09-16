import os

from typing import Any, Type

from PySide6.QtWidgets import (
    QToolButton,
    QLabel,
    QApplication,
    QWidget,
    QHBoxLayout,
)
from PySide6.QtGui import QIcon, QColor
from PySide6.QtCore import Qt

from zic.resources import get_resource


def make_toolbutton(
    icon_name: str, tooltip: str = "", checkable: bool = False
) -> QToolButton:
    button = QToolButton()
    icon_path = get_resource(icon_name)
    button.setIcon(QIcon(icon_path))
    if tooltip:
        button.setToolTip(tooltip)
    if checkable:
        button.setCheckable(checkable)
        black_icon_path = get_resource(icon_name.replace(".", "-black."))
        if black_icon_path and os.path.exists(black_icon_path):

            def toggle_icon(state: bool) -> None:
                button.setIcon(QIcon(black_icon_path if state else icon_path))

            button.toggled.connect(toggle_icon)

    return button


def set_label_font_size(label: QLabel, font_size: int) -> None:
    font = label.font()
    font.setPointSize(font_size)
    label.setFont(font)


def get_most_contrasted_color(color: QColor) -> QColor:
    if color.lightness() > 127:
        return QColor("#0f0f0f")
    else:
        return QColor("#edeef2")


class WaitCursor(object):
    def __enter__(self, *args: Any, **kwargs: Any) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)

    def __exit__(self, *args: Any, **kwargs: Any) -> None:
        QApplication.restoreOverrideCursor()


class SignalsOFF(object):
    def __init__(self, *widgets: QWidget):
        self.widgets: tuple[QWidget] = widgets

    def __enter__(self) -> None:
        for widget in self.widgets:
            widget.blockSignals(True)

    def __exit__(self, *args: Any) -> None:
        for widget in self.widgets:
            widget.blockSignals(False)


def named_widget(
    widget_type: Type[QWidget], name: str, *args: Any, **kwargs: Any
) -> QWidget:
    widget = widget_type(*args, **kwargs)
    widget.setObjectName(name)
    return widget


def labeled(
    widget_type: Type[QWidget], label: str, *args: Any, **kwargs: Any
) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    label_ = QLabel(label)
    content = widget_type(*args, **kwargs)
    layout.addWidget(label_)
    layout.addWidget(content)
    setattr(widget, "layout", layout)
    setattr(widget, "label", label_)
    setattr(widget, "content", content)
    layout.setContentsMargins(0, 0, 0, 0)
    return widget
