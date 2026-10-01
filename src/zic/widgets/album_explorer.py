import sqlite3
from enum import Enum
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QObject,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QColor, QCursor, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from zic.api import ZicApi
from zic.config import get_app_config, get_user_config
from zic.models.album import Album, AlbumCover
from zic.models.artist import Artist
from zic.models.genre import Genre
from zic.utils.qt_utils import (
    SignalsOFF,
    make_toolbutton,
    set_label_font_size,
    style_completer_popup,
)
from zic.utils.query_builder import QueryBuilder
from zic.widgets.cover_thumbnail import DEFAULT_COVER, CoverThumbnail
from zic.widgets.rules import VRule
from zic.widgets.sound_wave import SoundWave
from zic.widgets.strong_menu import StrongMenu
from zic.widgets.toggle_switch import ToggleSwitch

ALBUM_THUMBNAIL_SIZE = 140
ALBUM_ITEM_SIZE = QSize(160, 220)
COVER_ROLE = Qt.UserRole + 1
TEXT_ROLE = Qt.UserRole + 2
PREFETCH_MARGIN_ROWS = 30
PREFETCH_DEBOUNCE_MS = 80


class FilterTag(QFrame):
    """A small tag widget with a label and a close button."""

    clear_clicked = Signal()

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ContainerFrame")
        self.label_text = label
        self.init_ui()

    def init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 2, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignVCenter)

        label = QLabel(self.label_text)
        close_btn = make_toolbutton(
            "icons/close.png",
            tooltip="Remove filter",
            icon_size=QSize(10, 10),
            name="SmallToolButton",
        )
        close_btn.clicked.connect(self.clear_clicked.emit)

        layout.addWidget(label)
        layout.addWidget(close_btn)

        self.setFixedHeight(32)


class FilterTagsContainer(QWidget):
    """Container for filter tags."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tags: dict[str, FilterTag] = {}
        self.init_ui()

    def init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignVCenter)
        self.setLayout(layout)
        self.setFixedHeight(32)
        self.hide()

    def add_tag(self, tag_id: str, label: str, on_clear_callback) -> None:
        """Add a new tag or update existing one."""
        if tag_id not in self.tags:
            tag = FilterTag(label, self)
            tag.clear_clicked.connect(on_clear_callback)
            self.tags[tag_id] = tag
            self.layout().addWidget(tag)
        if self.isHidden():
            self.show()

    def remove_tag(self, tag_id: str) -> None:
        """Remove a tag by id."""
        if tag_id in self.tags:
            tag = self.tags.pop(tag_id)
            self.layout().removeWidget(tag)
            tag.deleteLater()
        if not self.isHidden() and not self.tags:
            self.hide()

    def clear_all(self) -> None:
        """Remove all tags."""
        tag_ids = list(self.tags.keys())
        for tag_id in tag_ids:
            self.remove_tag(tag_id)

    def has_tags(self) -> bool:
        """Check if there are any tags."""
        return len(self.tags) > 0


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
        self.sound_wave = None

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
        self.sound_wave = SoundWave(bars=20, height=20)

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.cover_thumbnail, 0, Qt.AlignHCenter)
        self.main_v_layout.addWidget(self.title_lbl)
        self.main_v_layout.addWidget(self.artist_lbl)
        self.main_v_layout.addWidget(self.sound_wave)

    def set_connections(self) -> None:
        pass

    def set_default(self) -> None:
        self.main_v_layout.setContentsMargins(0, 10, 0, 0)
        self.main_v_layout.setSpacing(4)
        self.main_v_layout.setAlignment(Qt.AlignTop | Qt.AlignCenter)
        for label in (self.title_lbl, self.artist_lbl):
            label.setFixedWidth(ALBUM_THUMBNAIL_SIZE)
            label.setWordWrap(False)
        set_label_font_size(self.title_lbl, 11)
        self.set_elided_text(self.title_lbl, self.album.name)
        self.set_elided_text(self.artist_lbl, self.album.artist.name)
        self.init_shadow()
        self.sound_wave.hide()

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

    def set_cover(self, cover: AlbumCover | None) -> None:
        """Update this item's cover once it has been loaded asynchronously."""
        if cover is None or cover == self.cover:
            return
        self.cover = cover
        self.cover_thumbnail.bytes = cover.thumbnail
        # Rebuild the drop shadow so it picks up the cover's dominant color.
        was_hovered = self.shadow.isEnabled() if self.shadow else False
        self.init_shadow()
        self.shadow.setEnabled(was_hovered)
        self.sound_wave.set_color(self.cover.dominant_color)

    def enterEvent(self, event: QEvent) -> None:
        self.shadow.setEnabled(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self.shadow.setEnabled(False)
        super().leaveEvent(event)

    def set_playing_display(self) -> None:
        self.sound_wave.show()
        self.sound_wave.raise_()
        self.sound_wave.start()

    def stop_playing_display(self) -> None:
        self.sound_wave.hide()
        self.sound_wave.stop()


class CoverLoaderWorker(QObject):
    """
    Loads album cover thumbnails from SQLite off the UI thread.

    Lives on its own QThread (see AlbumExplorer.init_cover_loader). Never
    touches any widget directly: it only reads from the database and emits
    plain data back to the main thread via a Qt signal, which Qt marshals
    across threads automatically (queued connection) because the receiver
    (the model) lives on the main thread.
    """

    covers_loaded = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._connection: sqlite3.Connection | None = None

    def _ensure_connection(self) -> sqlite3.Connection:
        # Opened lazily so the connection is created on the worker thread
        # itself (the slot below only ever runs there), since sqlite3
        # connections should not be shared across threads.
        if self._connection is None:
            db_path = get_app_config().db_path
            self._connection = sqlite3.connect(db_path)
        return self._connection

    @Slot(object)
    def load_covers(self, album_ids: list) -> None:
        if not album_ids:
            return
        conn = self._ensure_connection()
        query = QueryBuilder(
            "SELECT album_id, thumbnail, dominant_color FROM covers_thumbnails WHERE album_id IN"
        )
        query.push_binds(album_ids)
        cur = conn.execute(*query.build())
        result = {row[0]: AlbumCover(row[1], row[2]) for row in cur.fetchall()}
        self.covers_loaded.emit(result)

    def shutdown(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


class AlbumExplorerModel(QAbstractListModel):
    # Emitted with a list of album ids whose covers should be fetched.
    # Connected (cross-thread) to CoverLoaderWorker.load_covers.
    request_covers = Signal(object)

    def __init__(self, api) -> None:
        super().__init__()
        self.api: ZicApi = api
        self._albums: list[Album] = []
        self._covers: dict[int, AlbumCover] = {}
        self._pending_ids: set[int] = set()

    def set_albums(self, albums: list[Album]) -> None:
        self.beginResetModel()
        self._albums = albums
        self._covers = {}
        self._pending_ids = set()
        self.endResetModel()

    def album(self, index: QModelIndex) -> Album | None:
        if not index.isValid() or index.row() >= len(self._albums):
            return None
        return self._albums[index.row()]

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        # All rows are available immediately: album metadata is already
        # fully in memory (see api.albums()). Only cover thumbnails are
        # loaded lazily, so filtering/sorting never has to wait on them.
        if parent is None:
            parent = QModelIndex()
        return 0 if parent.isValid() else len(self._albums)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any | None:
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
        if role == TEXT_ROLE:
            texts = [album.name.lower(), album.artist.normalized_name]
            texts.extend(genre.name.lower() for genre in album.genres)
            return texts
        return None

    def request_covers_for_albums(self, albums: list[Album]) -> None:
        """Queue a cover fetch for the given albums, skipping ones already
        loaded or already in flight."""
        to_request = []
        for album in albums:
            if album.id in self._covers or album.id in self._pending_ids:
                continue
            self._pending_ids.add(album.id)
            to_request.append(album.id)
        if to_request:
            self.request_covers.emit(to_request)

    def on_covers_loaded(self, covers: dict[int, AlbumCover]) -> None:
        """Runs on the main thread (receiver affinity), safe to touch the
        model / emit dataChanged from here."""
        if not covers:
            return

        id_set = set(covers.keys())
        for album_id, cover in covers.items():
            self._covers[album_id] = cover
            self._pending_ids.discard(album_id)

        # Notify the view only for the rows that actually changed, in
        # contiguous runs, so we don't repaint the whole list.
        run_start = None
        for row, album in enumerate(self._albums):
            in_run = album.id in id_set
            if in_run and run_start is None:
                run_start = row
            elif not in_run and run_start is not None:
                self.dataChanged.emit(
                    self.index(run_start, 0), self.index(row - 1, 0), [COVER_ROLE]
                )
                run_start = None
        if run_start is not None:
            self.dataChanged.emit(
                self.index(run_start, 0),
                self.index(len(self._albums) - 1, 0),
                [COVER_ROLE],
            )


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

        if self.artist_ids and album.artist.id not in self.artist_ids:
            return False

        if self.genre_ids:
            for genre in album.genres:
                if genre.id in self.genre_ids:
                    break
            else:
                return False

        if not pattern:
            return True

        for text in self.sourceModel().data(index, TEXT_ROLE):
            for p in pattern.split(" "):
                if p in text:
                    return True
        return False

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


class AlbumCompletionModel(QAbstractListModel):
    def __init__(
        self, source_model: AlbumExplorerModel, text_role: int = TEXT_ROLE
    ) -> None:
        super().__init__()
        self._source = source_model
        self._text_role = text_role
        self._entries: list[tuple[str, int]] = []  # (texte, source_row)

        self._rebuild()
        self._source.modelReset.connect(self._rebuild)
        self._source.rowsInserted.connect(self._rebuild)
        self._source.rowsRemoved.connect(self._rebuild)

    def _rebuild(self, *_) -> None:
        self.beginResetModel()
        seen: dict[str, int] = {}  # texte -> source_row (garde la première occurrence)
        for row in range(self._source.rowCount()):
            for text in self._source.index(row, 0).data(self._text_role) or []:
                if text not in seen:
                    seen[text] = row
        self._entries = list(seen.items())
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        if parent is None:
            parent = QModelIndex()
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any | None:
        if not index.isValid():
            return None
        text, source_row = self._entries[index.row()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return text
        if role == Qt.UserRole:
            return self._source.index(source_row, 0).data(Qt.UserRole)  # -> Album
        return None


class AlbumExplorerView(QListView):
    album_double_clicked = Signal(QModelIndex)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("AlbumExplorerView")
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

        # Debounce cover requests so a single scroll gesture doesn't fire
        # one signal per pixel: we only ask for the visible range once
        # things have settled for a moment.
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.setInterval(PREFETCH_DEBOUNCE_MS)
        self._prefetch_timer.timeout.connect(self._request_visible_covers)

        self._item_widgets: dict[int, AlbumItemWidget] = {}

    def setModel(self, model: QAbstractItemModel) -> None:
        super().setModel(model)
        # Qt deletes index widgets itself when their rows go away (filtering
        # or model reset): drop our references so they never point to a
        # deleted widget.
        model.modelAboutToBeReset.connect(self._item_widgets.clear)
        model.rowsAboutToBeRemoved.connect(self.forget_item_widgets)
        model.modelReset.connect(self.create_item_widgets)
        model.rowsInserted.connect(self.create_item_widgets)
        model.dataChanged.connect(self.on_model_data_changed)

        model.modelReset.connect(self.schedule_prefetch)
        model.rowsInserted.connect(self.schedule_prefetch)
        model.layoutChanged.connect(self.schedule_prefetch)

        self.create_item_widgets()
        self.schedule_prefetch()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)
        # Not QListView.doubleClicked: the first click opens the album view,
        # which can resize the explorer and reflow the grid, so the album
        # under the cursor may differ from the one pressed and Qt then drops
        # the signal. Play the album selected by that first click instead.
        if (
            event.button() == Qt.LeftButton
            and self.indexAt(event.position().toPoint()).isValid()
            and self.currentIndex().isValid()
        ):
            self.album_double_clicked.emit(self.currentIndex())

    def get_widget_for_album(self, album_id: int) -> AlbumItemWidget | None:
        return self._item_widgets.get(album_id)

    def forget_item_widgets(self, parent: QModelIndex, first: int, last: int) -> None:
        model = self.model()
        for row in range(first, last + 1):
            album = model.index(row, 0, parent).data(Qt.UserRole)
            if album is not None:
                self._item_widgets.pop(album.id, None)

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
                album_widget = AlbumItemWidget(album, index.data(COVER_ROLE))
                self.setIndexWidget(index, album_widget)
                self._item_widgets[album.id] = album_widget

    def on_model_data_changed(
        self, top_left: QModelIndex, bottom_right: QModelIndex, roles: list[int]
    ) -> None:
        if roles and COVER_ROLE not in roles:
            return
        model = self.model()
        for row in range(top_left.row(), bottom_right.row() + 1):
            index = model.index(row, 0)
            widget = self.indexWidget(index)
            if widget is None:
                continue
            widget.set_cover(index.data(COVER_ROLE))

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self.schedule_prefetch()

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self.schedule_prefetch()

    def schedule_prefetch(self, *_) -> None:
        self._prefetch_timer.start()

    def _request_visible_covers(self) -> None:
        model = self.model()
        if model is None or model.rowCount() == 0:
            return

        top_index = self.indexAt(self.viewport().rect().topLeft())
        bottom_index = self.indexAt(self.viewport().rect().bottomRight())
        top_row = top_index.row() if top_index.isValid() else 0
        bottom_row = (
            bottom_index.row() if bottom_index.isValid() else model.rowCount() - 1
        )
        if bottom_row < top_row:
            bottom_row = model.rowCount() - 1

        start = max(0, top_row - PREFETCH_MARGIN_ROWS)
        end = min(model.rowCount() - 1, bottom_row + PREFETCH_MARGIN_ROWS)

        albums = []
        for row in range(start, end + 1):
            album = model.index(row, 0).data(Qt.UserRole)
            if album is not None:
                albums.append(album)

        source_model = model
        while isinstance(source_model, QSortFilterProxyModel):
            source_model = source_model.sourceModel()
        source_model.request_covers_for_albums(albums)

    def wheelEvent(self, event: QWheelEvent) -> None:
        scrollbar = self.verticalScrollBar()
        delta = event.angleDelta().y()
        target = scrollbar.value() - delta

        target = max(scrollbar.minimum(), min(target, scrollbar.maximum()))
        scrollbar.setValue(target)
        event.accept()


class SortingMode(Enum):
    NONE = 0
    ALBUM_TITLE = 1
    ARTIST_NAME = 2
    YEAR = 3


class AlbumExplorer(QWidget):
    album_selected = Signal(Album, AlbumCover)
    album_play_requested = Signal(Album)

    def __init__(self, api: QWidget) -> None:
        super().__init__()
        self.api: ZicApi = api
        self.filled: bool = False
        self.sorting_mode = SortingMode(get_user_config().explorer_sorting_mode)
        self.sort_order = (Qt.DescendingOrder, Qt.AscendingOrder)[
            get_user_config().explorer_sort_order
        ]
        self.current_playing_album: AlbumItemWidget | None = None

        # Layouts
        self.main_v_layout = None
        self.top_h_layout = None

        # Widgets
        self.title_lbl = None
        self.search_edt = None
        # self.filter_btn = None
        self.sort_btn = None
        # self.settings_btn = None
        self.tags_container = None
        self.model = None
        self.proxy = None
        self.view = None
        self.completion_model = None

        # Menu
        self.title_toggle = None
        self.artist_toggle = None
        self.year_toggle = None

        # Background cover loading
        self.cover_thread = None
        self.cover_worker = None

        # Current filters
        self._current_artists: list[Artist] = []
        self._current_genres: list[Genre] = []

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()
        self.init_cover_loader()

    def init_layouts(self) -> None:
        self.main_v_layout = QVBoxLayout(self)
        self.top_h_layout = QHBoxLayout()

    def init_widgets(self) -> None:
        self.title_lbl = QLabel("Albums")
        self.search_edt = QLineEdit()
        # self.filter_btn = make_toolbutton("icons/filter.png", tooltip="Filters")
        self.sort_btn = make_toolbutton("icons/sort.png", tooltip="Sorting")
        # self.settings_btn = make_toolbutton("icons/burger-bar.png", tooltip="Settings")
        self.tags_container = FilterTagsContainer()
        self.model = AlbumExplorerModel(self.api)
        self.completion_model = AlbumCompletionModel(self.model)
        self.proxy = AlbumFilterProxy()
        self.view = AlbumExplorerView()
        self.proxy.sorting_mode = self.sorting_mode
        self.proxy.setSourceModel(self.model)
        self.view.setModel(self.proxy)

    def init_cover_loader(self) -> None:
        """
        Sets up the dedicated worker thread that loads cover thumbnails.

        The worker (CoverLoaderWorker) is moved to its own QThread. All
        cross-thread communication goes through Qt signals only:
          - model.request_covers (main thread) -> worker.load_covers (worker thread)
          - worker.covers_loaded (worker thread) -> model.on_covers_loaded (main thread)
        Qt automatically queues these calls onto the receiver's thread, so
        no widget or model state is ever touched from the worker thread.
        """
        self.cover_thread = QThread(self)
        self.cover_worker = CoverLoaderWorker()
        self.cover_worker.moveToThread(self.cover_thread)

        self.model.request_covers.connect(self.cover_worker.load_covers)
        self.cover_worker.covers_loaded.connect(self.model.on_covers_loaded)
        self.cover_thread.finished.connect(self.cover_worker.deleteLater)

        self.cover_thread.start()

    def shutdown(self) -> None:
        """Call this from the parent window's closeEvent to stop the
        worker thread cleanly before the app exits."""
        if self.cover_thread is not None:
            self.cover_thread.quit()
            self.cover_thread.wait()

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.title_lbl)
        self.main_v_layout.addLayout(self.top_h_layout)
        self.top_h_layout.addWidget(self.search_edt)
        self.top_h_layout.addWidget(self.tags_container)
        # self.top_h_layout.addWidget(self.filter_btn)
        self.top_h_layout.addWidget(self.sort_btn)
        # self.top_h_layout.addWidget(self.settings_btn)
        self.top_h_layout.setAlignment(Qt.AlignVCenter)
        self.main_v_layout.addWidget(VRule())
        self.main_v_layout.addWidget(self.view)

    def set_connections(self) -> None:
        self.view.selectionModel().currentChanged.connect(
            self.on_album_selection_changed
        )
        self.view.album_double_clicked.connect(self.on_album_double_clicked)
        self.search_edt.editingFinished.connect(self.on_filter_changed)
        self.sort_btn.clicked.connect(self.show_sort_menu)

    def on_filter_changed(self) -> None:
        # No need to force-load every cover anymore: all rows are already
        # present in the model, so filtering is instant regardless of
        # cover-loading state.
        self.proxy.setFilterFixedString(self.search_edt.text())

    def set_default(self) -> None:
        self.main_v_layout.setAlignment(Qt.AlignTop)
        self.search_edt.setPlaceholderText("🔍 Search...")
        self.search_edt.setClearButtonEnabled(True)
        self.sort_btn.setFixedHeight(32)
        clear_button = self.search_edt.findChildren(QAction)
        if clear_button:
            clear_button[0].triggered.connect(
                lambda: (self.search_edt.clear(), self.on_filter_changed())
            )

        set_label_font_size(self.title_lbl, 12)
        completer = QCompleter(
            self.completion_model,
            completionRole=Qt.DisplayRole,
            caseSensitivity=Qt.CaseInsensitive,
        )
        style_completer_popup(completer)
        self.search_edt.setCompleter(completer)

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
        album = current.data(Qt.UserRole)
        if album is None:
            return
        self.album_selected.emit(
            album,
            current.data(COVER_ROLE),
        )

    def on_album_double_clicked(self, index: QModelIndex) -> None:
        album = index.data(Qt.UserRole)
        if album is not None:
            self.album_play_requested.emit(album)

    def set_artist_filters(self, artists: list[Artist]) -> None:
        self._current_artists = artists
        self.proxy.genre_ids = set()
        self.proxy.artist_ids = {artist.id for artist in artists}
        self.proxy.setFilterFixedString(self.search_edt.text())
        self._update_filter_tags()

    def remove_artist_filter(self, artist: Artist) -> None:
        artists = [a for a in self._current_artists if a != artist]
        self.set_artist_filters(artists)

    def set_genre_filters(self, genres: list[Genre]) -> None:
        self._current_genres = genres
        self.proxy.artist_ids = set()
        self.proxy.genre_ids = {genre.id for genre in genres}
        self.proxy.setFilterFixedString(self.search_edt.text())
        self._update_filter_tags()

    def remove_genre_filter(self, genre: Genre) -> None:
        genres = [g for g in self._current_genres if g != genre]
        self.set_genre_filters(genres)

    def _update_filter_tags(self) -> None:
        """Update the filter tags display based on current filters."""
        self.tags_container.clear_all()

        for artist in self._current_artists:
            self.tags_container.add_tag(
                f"artist_{artist.id}",
                artist.name,
                lambda a=artist: self.remove_artist_filter(a),
            )

        for genre in self._current_genres:
            self.tags_container.add_tag(
                f"genre_{genre.id}",
                genre.name,
                lambda g=genre: self.remove_genre_filter(g),
            )

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

        order_toggle = ToggleSwitch(
            label="Ascending", checked=self.sort_order == Qt.AscendingOrder
        )
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

    def get_item_from_album(self, album: Album) -> AlbumItemWidget | None:
        if self.view is None:
            return

        return self.view.get_widget_for_album(album.id)

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
        self.proxy.invalidate()
        self.proxy.sort(0, self.sort_order)

    def start_playing_album_display(self, album: Album) -> None:
        if self.current_playing_album:
            try:
                self.current_playing_album.stop_playing_display()
            except RuntimeError:
                pass
        widget = self.get_item_from_album(album)
        if widget is None:
            return
        widget.set_playing_display()
        self.current_playing_album = widget

    def stop_current_playing_album_display(self) -> None:
        if self.current_playing_album:
            self.current_playing_album.stop_playing_display()
            self.current_playing_album = None
