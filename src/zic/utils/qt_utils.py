from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)

from zic.resources import get_resource


def make_toolbutton(
    icon_name: str,
    tooltip: str = "",
    checkable: bool = False,
    name: str | None = None,
    icon_size: QSize | None = None,
) -> QToolButton:
    button = QToolButton()
    icon_path = get_resource(icon_name)
    button.setIcon(QIcon(icon_path))

    if icon_size:
        button.setIconSize(icon_size)

    if tooltip:
        button.setToolTip(tooltip)

    if checkable:
        button.setCheckable(checkable)
        # black_icon_path = get_resource(icon_name.replace(".", "-black."))
        # if black_icon_path and os.path.exists(black_icon_path):

        #     def toggle_icon(state: bool) -> None:
        #         button.setIcon(QIcon(black_icon_path if state else icon_path))

        #     button.toggled.connect(toggle_icon)

    if name:
        button.setObjectName(name)

    return button


def set_label_font_size(label: QLabel, font_size: int) -> None:
    font = label.font()
    font.setPointSize(font_size)
    label.setFont(font)


def style_completer_popup(completer) -> None:
    """Apply dark theme stylesheet to QCompleter popup."""
    popup = completer.popup()
    if popup:
        stylesheet = """
            QListView {
                background-color: #151B24;
                color: #E6E9EE;
                border: 1px solid #2A3342;
                border-radius: 4px;
                outline: none;
            }
            QListView::item {
                padding: 6px 8px;
                border-radius: 4px;
                margin-bottom: 2px;
            }
            QListView::item:hover {
                background-color: #1C2330;
            }
            QListView::item:selected {
                background-color: #35F0E0;
                color: #151B24;
            }
        """
        popup.setStyleSheet(stylesheet)


def get_most_contrasted_color(color: QColor) -> QColor:
    if color.lightness() > 127:
        return QColor("#0f0f0f")
    else:
        return QColor("#edeef2")


class WaitCursor:
    def __enter__(self, *args: Any, **kwargs: Any) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)

    def __exit__(self, *args: object, **kwargs: Any) -> None:
        QApplication.restoreOverrideCursor()


class SignalsOFF:
    def __init__(self, *widgets: QWidget):
        self.widgets: tuple[QWidget] = widgets

    def __enter__(self) -> None:
        for widget in self.widgets:
            widget.blockSignals(True)

    def __exit__(self, *args: object) -> None:
        for widget in self.widgets:
            widget.blockSignals(False)


def named_widget(
    widget_type: type[QWidget], name: str, *args: Any, **kwargs: Any
) -> QWidget:
    widget = widget_type(*args, **kwargs)
    widget.setObjectName(name)
    return widget


def labeled(
    widget_type: type[QWidget], label: str, *args: Any, **kwargs: Any
) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    label_ = QLabel(label)
    content = widget_type(*args, **kwargs)
    layout.addWidget(label_)
    layout.addWidget(content)
    widget.layout = layout
    widget.label = label_
    widget.content = content
    layout.setContentsMargins(0, 0, 0, 0)
    return widget
