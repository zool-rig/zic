from PySide6.QtWidgets import QLabel
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap

from zic.resources import get_resource

with open(get_resource("icons/music.png"), "rb") as f:
    DEFAULT_COVER = f.read()


class CoverThumbnail(QLabel):
    def __init__(
        self,
        path: str | None = None,
        bytes_: bytes | None = None,
        width: int = 60,
        height: int = 60,
    ) -> None:
        super().__init__()
        self._path: str | None = None
        self._bytes: bytes | None = None
        self._width: int = width
        self._height: int = height
        self._qimage: QImage | None = None
        self._pixmap: QPixmap | None = None

        if bytes_ is not None:
            self.bytes = bytes_
        elif path:
            self.path = path
        self.setFixedSize(self._width, self._height)

    @property
    def width(self) -> int:
        return self._width

    @width.setter
    def width(self, width: int) -> None:
        self._width = width
        self.setFixedWidth(self._width)

    @property
    def height(self) -> int:
        return self._height

    @height.setter
    def height(self, height: int) -> None:
        self._height = height
        self.setFixedHeight(self._height)

    def display_image(self) -> None:
        if self._qimage is None:
            raise ValueError("Can't load image, please provide a path or bytes.")
        self._pixmap = QPixmap.fromImage(self._qimage).scaled(
            QSize(self.width, self.height), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(self._pixmap)

    @property
    def path(self) -> str:
        return self._path

    @path.setter
    def path(self, path: str) -> None:
        self._path = path
        self._qimage = QImage(self._path)
        self.display_image()

    @property
    def bytes(self) -> bytes | None:
        return self._bytes

    @bytes.setter
    def bytes(self, bytes_: bytes) -> None:
        self._bytes = bytes_
        self._qimage = QImage.fromData(self._bytes)
        self.display_image()
