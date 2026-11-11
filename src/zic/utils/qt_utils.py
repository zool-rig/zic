from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QProxyStyle,
    QStyleOption,
    QToolButton,
    QWidget,
)

from zic.resources import get_resource

# Color of the icons on the accent background of what's checked or selected,
# like the text of the selected items of lists in style.qss.
CHECKED_ICON_COLOR = "#151B24"


def with_checked_variant(icon: QIcon) -> QIcon:
    """The icon, plus a dark version of it for when its button is checked:
    the light icons can't be seen on the accent background."""
    pixmap = icon.pixmap(QSize(256, 256))
    if pixmap.isNull():
        return icon

    checked = QPixmap(pixmap.size())
    checked.setDevicePixelRatio(pixmap.devicePixelRatio())
    checked.fill(Qt.transparent)
    painter = QPainter(checked)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(checked.rect(), QColor(CHECKED_ICON_COLOR))
    painter.end()

    result = QIcon()
    for mode in (QIcon.Normal, QIcon.Active):
        result.addPixmap(pixmap, mode, QIcon.Off)
        result.addPixmap(checked, mode, QIcon.On)
    # Disabled buttons lose the accent background: their light icon stays.
    result.addPixmap(
        QApplication.style().generatedIconPixmap(
            QIcon.Disabled, pixmap, QStyleOption()
        ),
        QIcon.Disabled,
        QIcon.On,
    )
    return result


class CheckableToolButton(QToolButton):
    """Keeps a dark icon when checked, including when its icon changes."""

    def setIcon(self, icon: QIcon) -> None:
        super().setIcon(with_checked_variant(icon))


def make_toolbutton(
    icon_name: str,
    tooltip: str = "",
    checkable: bool = False,
    name: str | None = None,
    icon_size: QSize | None = None,
) -> QToolButton:
    button = CheckableToolButton() if checkable else QToolButton()
    icon_path = get_resource(icon_name)
    button.setIcon(QIcon(icon_path))

    if icon_size:
        button.setIconSize(icon_size)

    if tooltip:
        button.setToolTip(tooltip)

    if checkable:
        button.setCheckable(checkable)

    if name:
        button.setObjectName(name)

    return button


class FadedDisabledIconStyle(QProxyStyle):
    """Draws disabled icons semi-transparent. Qt's default disabled mode
    turns icons gray, which leaves light icons on a dark theme almost
    unchanged."""

    DISABLED_OPACITY = 0.3

    def generatedIconPixmap(
        self, mode: QIcon.Mode, pixmap: QPixmap, option: QStyleOption
    ) -> QPixmap:
        if mode != QIcon.Mode.Disabled:
            return super().generatedIconPixmap(mode, pixmap, option)
        faded = QPixmap(pixmap.size())
        faded.setDevicePixelRatio(pixmap.devicePixelRatio())
        faded.fill(Qt.transparent)
        painter = QPainter(faded)
        painter.setOpacity(self.DISABLED_OPACITY)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return faded


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
