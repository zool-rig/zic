from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from zic.utils.qt_utils import make_toolbutton
from zic.widgets.rules import VRule
from zic.models.album import Album, AlbumCover
from zic.widgets.cover_thumbnail import CoverThumbnail
from zic.resources import get_resource


ALBUM_THUMBNAIL_SIZE = 140
ALBUM_ITEM_SIZE = QSize(160, 220)
ALBUM_CHUNK_SIZE = 60
COVER_ROLE = Qt.UserRole + 1
with open(get_resource("icons/music.png"), "rb") as f:
    DEFAULT_COVER = f.read()


class AlbumItemWidget(QWidget):
    def __init__(self, album: Album, cover: AlbumCover | None = None) -> None:
        super().__init__()
        self.album: Album = album
        self.cover: AlbumCover | None = cover

        # Layouts
        self.main_v_layout = None

        # Widgets
        self.cover_thumbnail = None
        self.title_lbl = None
        self.artist_lbl = None

        # Effects
        self.shadow = None

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()

    def init_layouts(self) -> None:
        self.main_v_layout = QVBoxLayout(self)

    def init_widgets(self) -> None:
        self.cover_thumbnail = CoverThumbnail(
            bytes_=self.cover.thumbnail if self.cover else DEFAULT_COVER,
            width=ALBUM_THUMBNAIL_SIZE,
            height=ALBUM_THUMBNAIL_SIZE,
        )
        self.title_lbl = QLabel()
        self.artist_lbl = QLabel()

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.cover_thumbnail, 0, Qt.AlignHCenter)
        self.main_v_layout.addWidget(self.title_lbl)
        self.main_v_layout.addWidget(self.artist_lbl)

    def set_connections(self) -> None:
        pass

    def set_default(self) -> None:
        self.main_v_layout.setContentsMargins(0, 0, 0, 0)
        self.main_v_layout.setSpacing(4)
        self.main_v_layout.setAlignment(Qt.AlignTop)
        for label in (self.title_lbl, self.artist_lbl):
            label.setFixedWidth(ALBUM_THUMBNAIL_SIZE)
            label.setWordWrap(False)
        self.set_elided_text(self.title_lbl, f"💿 : {self.album.name}")
        self.set_elided_text(self.artist_lbl, f"🎤 : {self.album.artist.name}")
        self.init_shadow()

    def set_elided_text(self, label: QLabel, text: str) -> None:
        label.setToolTip(text)
        label.setText(
            label.fontMetrics().elidedText(text, Qt.ElideRight, ALBUM_THUMBNAIL_SIZE)
        )

    def init_shadow(self) -> None:
        color = QColor(self.cover.dominant_color) if self.cover else QColor()
        if not color.isValid():
            color = QColor(0, 0, 0, 160)
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(30)
        self.shadow.setOffset(0, 0)
        self.shadow.setColor(color)
        self.shadow.setEnabled(False)
        self.setGraphicsEffect(self.shadow)

    def enterEvent(self, event: QEvent) -> None:
        self.shadow.setEnabled(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self.shadow.setEnabled(False)
        super().leaveEvent(event)


class AlbumExplorerModel(QAbstractListModel):
    def __init__(self, api) -> None:
        super().__init__()
        self.api = api
        self._albums: list[Album] = []
        self._loaded_count: int = 0
        self._covers: dict[int, AlbumCover] = {}

    def set_albums(self, albums: list[Album]) -> None:
        self.beginResetModel()
        self._albums = albums
        self._covers = {}
        self._loaded_count = 0
        self._load_covers(0, min(ALBUM_CHUNK_SIZE, len(self._albums)))
        self._loaded_count = min(ALBUM_CHUNK_SIZE, len(self._albums))
        self.endResetModel()

    def _load_covers(self, start: int, end: int) -> None:
        chunk = self._albums[start:end]
        if chunk:
            self._covers.update(self.api.get_albums_cover_thumbnails(chunk))

    def album(self, index: QModelIndex) -> Album | None:
        if not index.isValid() or index.row() >= self._loaded_count:
            return None
        return self._albums[index.row()]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else self._loaded_count

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        album = self.album(index)
        if album is None:
            return None
        if role == Qt.DisplayRole:
            return ""
        if role == Qt.SizeHintRole:
            return ALBUM_ITEM_SIZE
        if role == Qt.UserRole:
            return album
        if role == COVER_ROLE:
            return self._covers.get(album.id)
        return None

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:
        return not parent.isValid() and self._loaded_count < len(self._albums)

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:
        if parent.isValid():
            return
        remaining = len(self._albums) - self._loaded_count
        to_fetch = min(ALBUM_CHUNK_SIZE, remaining)
        if to_fetch <= 0:
            return
        self._load_covers(self._loaded_count, self._loaded_count + to_fetch)
        self.beginInsertRows(
            QModelIndex(), self._loaded_count, self._loaded_count + to_fetch - 1
        )
        self._loaded_count += to_fetch
        self.endInsertRows()


class AlbumExplorerView(QListView):
    def __init__(self) -> None:
        super().__init__()
        self.setUniformItemSizes(True)
        self.setFlow(QListView.LeftToRight)
        self.setResizeMode(QListView.Adjust)
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setSelectionRectVisible(False)
        self.setSpacing(10)
        self.setWrapping(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

    def setModel(self, model: QAbstractItemModel) -> None:
        super().setModel(model)
        model.modelReset.connect(self.create_item_widgets)
        model.rowsInserted.connect(self.create_item_widgets)
        self.create_item_widgets()

    def create_item_widgets(self, *_) -> None:
        model = self.model()
        if model is None:
            return
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            if self.indexWidget(index) is not None:
                continue
            album = index.data(Qt.UserRole)
            if album is not None:
                self.setIndexWidget(
                    index, AlbumItemWidget(album, index.data(COVER_ROLE))
                )



class AlbumExplorer(QWidget):
    def __init__(self, app: QWidget) -> None:
        super().__init__()
        self.app: QWidget = app
        self.filled: bool = False

        # Layouts
        self.main_v_layout = None
        self.top_h_layout = None

        # Widgets
        self.title_lbl = None
        self.search_edt = None
        self.filter_btn = None
        self.sort_btn = None
        self.settings_btn = None
        self.model = None
        self.view = None

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()

    def init_layouts(self) -> None:
        self.main_v_layout = QVBoxLayout(self)
        self.top_h_layout = QHBoxLayout()

    def init_widgets(self) -> None:
        self.title_lbl = QLabel("Albums")
        self.search_edt = QLineEdit()
        self.filter_btn = make_toolbutton("icons/filter.png", tooltip="Filters")
        self.sort_btn = make_toolbutton("icons/sort.png", tooltip="Sorting")
        self.settings_btn = make_toolbutton("icons/burger-bar.png", tooltip="Settings")
        self.model = AlbumExplorerModel(self.app.api)
        self.view = AlbumExplorerView()
        self.view.setModel(self.model)

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.title_lbl)
        self.main_v_layout.addLayout(self.top_h_layout)
        self.top_h_layout.addWidget(self.search_edt)
        self.top_h_layout.addWidget(self.filter_btn)
        self.top_h_layout.addWidget(self.sort_btn)
        self.top_h_layout.addWidget(self.settings_btn)
        self.main_v_layout.addWidget(VRule())
        self.main_v_layout.addWidget(self.view)

    def set_connections(self) -> None:
        pass

    def set_default(self) -> None:
        self.main_v_layout.setAlignment(Qt.AlignTop)
        self.search_edt.setPlaceholderText("🔍 Search...")
        self.search_edt.setClearButtonEnabled(True)

    def fill(self) -> None:
        albums = self.app.api.albums()
        self.model.set_albums(albums)
        self.title_lbl.setText(f"{len(albums)} - Albums")
        self.filled = True

    def showEvent(self, _: QEvent) -> None:
        if not self.filled:
            self.fill()
