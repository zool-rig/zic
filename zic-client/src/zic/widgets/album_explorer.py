from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from enum import Enum

from zic.utils.qt_utils import make_toolbutton, set_label_font_size, SignalsOFF
from zic.widgets.rules import VRule
from zic.models.album import Album, AlbumCover
from zic.widgets.cover_thumbnail import CoverThumbnail, DEFAULT_COVER
from zic.models.artist import Artist
from zic.models.genre import Genre
from zic.widgets.toggle_switch import ToggleSwitch
from zic.widgets.strong_menu import StrongMenu
from zic.config import get_user_config
from zic.api import ZicApi


ALBUM_THUMBNAIL_SIZE = 140
ALBUM_ITEM_SIZE = QSize(160, 220)
ALBUM_CHUNK_SIZE = 60
COVER_ROLE = Qt.UserRole + 1


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
        set_label_font_size(self.title_lbl, 11)
        self.set_elided_text(self.title_lbl, self.album.name)
        self.set_elided_text(self.artist_lbl, self.album.artist.name)
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
        self.api: ZicApi = api
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

    def load_all_covers(self) -> None:
        """Load all remaining album covers."""
        if self._loaded_count < len(self._albums):
            self._load_covers(self._loaded_count, len(self._albums))
            self.beginInsertRows(
                QModelIndex(), self._loaded_count, len(self._albums) - 1
            )
            self._loaded_count = len(self._albums)
            self.endInsertRows()

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


class AlbumFilterProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.artist_ids: set[int] = set()
        self.genre_ids: set[int] = set()
        self.sorting_mode: SortingMode = SortingMode.NONE

    def filterAcceptsRow(
        self, source_row: QModelIndex, source_parent: QModelIndex
    ) -> bool:
        pattern = self.filterRegularExpression().pattern().strip().lower()
        if not pattern and not self.artist_ids and not self.genre_ids:
            return True

        index = self.sourceModel().index(source_row, 0, source_parent)
        album: Album = self.sourceModel().data(index, Qt.UserRole)

        if self.artist_ids:
            if album.artist.id not in self.artist_ids:
                return False

        if self.genre_ids:
            for genre in album.genres:
                if genre.id in self.genre_ids:
                    break
            else:
                return False

        if not pattern:
            return True

        return (
            pattern in album.name.lower()
            or pattern in album.artist.normalized_name
            or pattern in {genre.name.lower() for genre in album.genres}
        )

    def lessThan(self, source_left: QModelIndex, source_right: QModelIndex) -> bool:
        left_album: Album = self.sourceModel().data(source_left, Qt.UserRole)
        right_album: Album = self.sourceModel().data(source_right, Qt.UserRole)

        if self.sorting_mode == SortingMode.ALBUM_TITLE:
            return left_album.name.lower() < right_album.name.lower()
        elif self.sorting_mode == SortingMode.ARTIST_NAME:
            return left_album.artist.name.lower() < right_album.artist.name.lower()
        elif self.sorting_mode == SortingMode.YEAR:
            return (left_album.year or 0) < (right_album.year or 0)

        return False


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


class SortingMode(Enum):
    NONE = 0
    ALBUM_TITLE = 1
    ARTIST_NAME = 2
    YEAR = 3


class AlbumExplorer(QWidget):
    album_selected = Signal(Album, AlbumCover)

    def __init__(self, api: QWidget) -> None:
        super().__init__()
        self.api: ZicApi = api
        self.filled: bool = False
        self.sorting_mode = SortingMode(get_user_config().explorer_sorting_mode)
        self.sort_order = (Qt.DescendingOrder, Qt.AscendingOrder)[
            get_user_config().explorer_sort_order
        ]

        # Layouts
        self.main_v_layout = None
        self.top_h_layout = None

        # Widgets
        self.title_lbl = None
        self.search_edt = None
        # self.filter_btn = None
        self.sort_btn = None
        # self.settings_btn = None
        self.model = None
        self.proxy = None
        self.view = None

        # Menu
        self.title_toggle = None
        self.artist_toggle = None
        self.year_toggle = None

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
        # self.filter_btn = make_toolbutton("icons/filter.png", tooltip="Filters")
        self.sort_btn = make_toolbutton("icons/sort.png", tooltip="Sorting")
        # self.settings_btn = make_toolbutton("icons/burger-bar.png", tooltip="Settings")
        self.model = AlbumExplorerModel(self.api)
        self.proxy = AlbumFilterProxy()
        self.view = AlbumExplorerView()
        self.proxy.setSourceModel(self.model)
        self.view.setModel(self.proxy)

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.title_lbl)
        self.main_v_layout.addLayout(self.top_h_layout)
        self.top_h_layout.addWidget(self.search_edt)
        # self.top_h_layout.addWidget(self.filter_btn)
        self.top_h_layout.addWidget(self.sort_btn)
        # self.top_h_layout.addWidget(self.settings_btn)
        self.main_v_layout.addWidget(VRule())
        self.main_v_layout.addWidget(self.view)

    def set_connections(self) -> None:
        self.view.selectionModel().currentChanged.connect(
            self.on_album_selection_changed
        )
        self.search_edt.editingFinished.connect(self.on_filter_changed)
        self.sort_btn.clicked.connect(self.show_sort_menu)

    def on_filter_changed(self) -> None:
        """Handle filter changes by ensuring all albums are loaded."""
        self.model.load_all_covers()
        self.proxy.setFilterFixedString(self.search_edt.text())

    def set_default(self) -> None:
        self.main_v_layout.setAlignment(Qt.AlignTop)
        self.search_edt.setPlaceholderText("🔍 Search...")
        self.search_edt.setClearButtonEnabled(True)
        set_label_font_size(self.title_lbl, 12)

    def fill(self) -> None:
        albums = self.api.albums()
        self.model.set_albums(albums)
        self.title_lbl.setText(f"{len(albums)} - Albums")
        if self.sorting_mode != SortingMode.NONE:
            self.proxy.sort(0, self.sort_order)
        self.filled = True

    def showEvent(self, _: QEvent) -> None:
        if not self.filled:
            self.fill()

    def on_album_selection_changed(self, current: QModelIndex, _: QModelIndex) -> None:
        self.album_selected.emit(
            current.data(Qt.UserRole),
            current.data(COVER_ROLE),
        )

    def set_artist_filters(self, artists: list[Artist]) -> None:
        self.model.load_all_covers()
        self.proxy.genre_ids = set()
        self.proxy.artist_ids = {artist.id for artist in artists}
        self.proxy.setFilterFixedString(self.search_edt.text())

    def set_genre_filters(self, genres: list[Genre]) -> None:
        self.model.load_all_covers()
        self.proxy.artist_ids = set()
        self.proxy.genre_ids = {genre.id for genre in genres}
        self.proxy.setFilterFixedString(self.search_edt.text())

    def show_sort_menu(self) -> None:
        menu = StrongMenu(self)

        self.title_toggle = ToggleSwitch(
            label="Album title", checked=self.sorting_mode == SortingMode.ALBUM_TITLE
        )
        self.title_toggle.toggled.connect(
            lambda state: self.set_sorting_mode(SortingMode.ALBUM_TITLE, state)
        )
        action = QWidgetAction(menu)
        action.setDefaultWidget(self.title_toggle)
        menu.addAction(action)

        self.artist_toggle = ToggleSwitch(
            label="Artist name", checked=self.sorting_mode == SortingMode.ARTIST_NAME
        )
        self.artist_toggle.toggled.connect(
            lambda state: self.set_sorting_mode(SortingMode.ARTIST_NAME, state)
        )
        action = QWidgetAction(menu)
        action.setDefaultWidget(self.artist_toggle)
        menu.addAction(action)

        self.year_toggle = ToggleSwitch(
            label="Year", checked=self.sorting_mode == SortingMode.YEAR
        )
        self.year_toggle.toggled.connect(
            lambda state: self.set_sorting_mode(SortingMode.YEAR, state)
        )
        action = QWidgetAction(menu)
        action.setDefaultWidget(self.year_toggle)
        menu.addAction(action)

        menu.addSeparator()

        order_toggle = ToggleSwitch(label="Ascending", checked=self.sort_order)
        order_toggle.toggled.connect(
            lambda state: self.set_sort_order(
                Qt.AscendingOrder if state else Qt.DescendingOrder
            )
        )
        action = QWidgetAction(menu)
        action.setDefaultWidget(order_toggle)
        menu.addAction(action)

        menu.exec(QCursor.pos())

    def set_sort_order(self, order: int) -> None:
        self.sort_order = order
        get_user_config().explorer_sort_order = [
            Qt.DescendingOrder,
            Qt.AscendingOrder,
        ].index(order)
        self.proxy.sort(0, order)

    def set_sorting_mode(self, mode: SortingMode, state: bool) -> None:
        self.sorting_mode = mode if state else SortingMode.NONE
        self.proxy.sorting_mode = self.sorting_mode
        get_user_config().explorer_sorting_mode = self.sorting_mode
        if state:
            toggles = (self.title_toggle, self.artist_toggle, self.year_toggle)
            modes = (
                SortingMode.ALBUM_TITLE,
                SortingMode.ARTIST_NAME,
                SortingMode.YEAR,
            )
            with SignalsOFF(*toggles):
                for toggle, mode_ in zip(toggles, modes):
                    if mode_ == mode:
                        continue
                    toggle.set_checked(False)
        self.proxy.sort(0, self.sort_order)
