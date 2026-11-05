from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from zic.api import ZicApi
from zic.dialogs.song_info_dialog import SongInfoDialog
from zic.dialogs.user_playlist_dialogs import (
    confirm_deletion,
    create_playlist,
    rename_playlist,
)
from zic.ingestor.ingest import PLAYLISTS_DIR
from zic.models.song import Song
from zic.models.user_playlist import UserPlaylist
from zic.utils.formatting import format_songs_total
from zic.utils.qt_utils import make_toolbutton, set_label_font_size
from zic.widgets.add_to_playlist_menu import show_add_to_playlist_menu
from zic.widgets.album_view import SongWidget
from zic.widgets.cover_thumbnail import DEFAULT_COVER, CoverThumbnail

LIST_ICON_SIZE = QSize(48, 48)


class PlaylistSongWidget(SongWidget):
    """A song in a playlist, which can be moved or removed from it."""

    move_requested = Signal(Song, int)
    remove_requested = Signal(Song)

    def init_widgets(self) -> None:
        super().init_widgets()
        self.move_up_btn = make_toolbutton(
            "icons/up-arrow.png",
            tooltip="Move up",
            icon_size=QSize(10, 10),
            name="SmallToolButton",
        )
        self.move_down_btn = make_toolbutton(
            "icons/down-arrow.png",
            tooltip="Move down",
            icon_size=QSize(10, 10),
            name="SmallToolButton",
        )
        self.remove_btn = make_toolbutton(
            "icons/close.png",
            tooltip="Remove from this playlist",
            icon_size=QSize(10, 10),
            name="SmallToolButton",
        )

    def set_layout(self) -> None:
        super().set_layout()
        self.main_h_layout.addWidget(self.move_up_btn)
        self.main_h_layout.addWidget(self.move_down_btn)
        self.main_h_layout.addWidget(self.remove_btn)

    def set_connections(self) -> None:
        super().set_connections()
        self.move_up_btn.clicked.connect(
            lambda: self.move_requested.emit(self.song, -1)
        )
        self.move_down_btn.clicked.connect(
            lambda: self.move_requested.emit(self.song, 1)
        )
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.song))


class UserPlaylistsWidget(QWidget):
    """The list of the user's playlists, and the songs of the selected one."""

    play_playlist_requested = Signal(UserPlaylist)
    shuffle_playlist_requested = Signal(UserPlaylist)
    play_song_requested = Signal(UserPlaylist, Song)
    song_edited = Signal()

    def __init__(self, api: ZicApi) -> None:
        super().__init__()
        self.api: ZicApi = api
        self.playlist: UserPlaylist | None = None
        self.playing_song: Song | None = None
        self.song_widgets: dict[int, PlaylistSongWidget] = {}

        # Layouts
        self.main_v_layout = None
        self.header_h_layout = None
        self.details_v_layout = None
        self.top_h_layout = None
        self.buttons_h_layout = None
        self.songs_v_layout = None

        # Widgets
        self.header_lbl = None
        self.new_btn = None
        self.empty_lbl = None
        self.splitter = None
        self.list_widget = None
        self.details_widget = None
        self.close_btn = None
        self.cover_thumbnail = None
        self.title_lbl = None
        self.songs_info_lbl = None
        self.play_btn = None
        self.play_random_btn = None
        self.rename_btn = None
        self.delete_btn = None
        self.scroll_area = None
        self.scroll_area_widget = None

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()

    def init_layouts(self) -> None:
        self.main_v_layout = QVBoxLayout(self)
        self.header_h_layout = QHBoxLayout()
        self.details_v_layout = QVBoxLayout()
        self.top_h_layout = QHBoxLayout()
        self.buttons_h_layout = QHBoxLayout()
        self.songs_v_layout = QVBoxLayout()

    def init_widgets(self) -> None:
        self.header_lbl = QLabel("Playlists")
        self.new_btn = make_toolbutton("icons/plus.png", tooltip="New playlist")
        self.empty_lbl = QLabel(
            "No playlist yet. Create one, or put songs in a folder of "
            f"{PLAYLISTS_DIR}/ at the root of your library, then check for new "
            "songs: each folder becomes a playlist."
        )
        self.splitter = QSplitter(Qt.Horizontal)
        self.list_widget = QListWidget()
        self.details_widget = QWidget()
        self.close_btn = make_toolbutton("icons/close.png", tooltip="Close")
        self.cover_thumbnail = CoverThumbnail(width=200, height=200)
        self.title_lbl = QLabel()
        self.songs_info_lbl = QLabel()
        self.play_btn = make_toolbutton("icons/play.png", tooltip="Play")
        self.play_random_btn = make_toolbutton(
            "icons/shuffle.png", tooltip="Play random"
        )
        self.rename_btn = make_toolbutton("icons/edit.png", tooltip="Rename")
        self.delete_btn = make_toolbutton("icons/trash.png", tooltip="Delete")
        self.scroll_area = QScrollArea()
        self.scroll_area_widget = QWidget()

    def set_layout(self) -> None:
        self.main_v_layout.addLayout(self.header_h_layout)
        self.header_h_layout.addWidget(self.header_lbl)
        self.header_h_layout.addWidget(self.new_btn)
        self.header_h_layout.addStretch()
        self.main_v_layout.addWidget(self.empty_lbl, 1)
        self.main_v_layout.addWidget(self.splitter)
        self.splitter.addWidget(self.list_widget)
        self.splitter.addWidget(self.details_widget)
        self.details_widget.setLayout(self.details_v_layout)
        self.details_v_layout.addLayout(self.top_h_layout)
        self.top_h_layout.addWidget(self.close_btn)
        self.details_v_layout.addWidget(self.cover_thumbnail, alignment=Qt.AlignHCenter)
        self.details_v_layout.addWidget(self.title_lbl)
        self.details_v_layout.addWidget(self.songs_info_lbl)
        self.details_v_layout.addLayout(self.buttons_h_layout)
        self.buttons_h_layout.addWidget(self.play_btn)
        self.buttons_h_layout.addWidget(self.play_random_btn)
        self.buttons_h_layout.addWidget(self.rename_btn)
        self.buttons_h_layout.addWidget(self.delete_btn)
        self.details_v_layout.addWidget(self.scroll_area)
        self.scroll_area.setWidget(self.scroll_area_widget)
        self.scroll_area_widget.setLayout(self.songs_v_layout)

    def set_connections(self) -> None:
        self.list_widget.currentItemChanged.connect(self.on_current_item_changed)
        self.close_btn.clicked.connect(self.close_details)
        self.new_btn.clicked.connect(self.create_playlist)
        self.rename_btn.clicked.connect(self.rename_playlist)
        self.delete_btn.clicked.connect(self.delete_playlist)
        self.play_btn.clicked.connect(
            lambda: self.play_playlist_requested.emit(self.playlist)
        )
        self.play_random_btn.clicked.connect(
            lambda: self.shuffle_playlist_requested.emit(self.playlist)
        )

    def set_default(self) -> None:
        self.top_h_layout.setAlignment(Qt.AlignRight)
        self.buttons_h_layout.setAlignment(Qt.AlignCenter)
        self.list_widget.setIconSize(LIST_ICON_SIZE)
        self.songs_v_layout.setAlignment(Qt.AlignTop)
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.songs_info_lbl.setAlignment(Qt.AlignCenter)
        set_label_font_size(self.title_lbl, 12)
        set_label_font_size(self.header_lbl, 12)
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setWordWrap(True)
        self.scroll_area.setWidgetResizable(True)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        # Stretch factors only share out later resizes: set the initial ratio.
        self.splitter.setSizes([1000, 3000])
        self.details_widget.hide()

    def fill(self) -> None:
        """Reads the playlists again, keeping the selected one if it's still
        there."""
        selected_id = self.playlist.id if self.playlist is not None else None
        playlists = self.api.get_user_playlists()

        self.playlist = None
        self.list_widget.clear()
        for playlist in playlists:
            item = QListWidgetItem()
            self.set_item_playlist(item, playlist)
            self.list_widget.addItem(item)
            if playlist.id == selected_id:
                self.list_widget.setCurrentItem(item)

        self.empty_lbl.setVisible(not playlists)
        self.splitter.setVisible(bool(playlists))
        if self.playlist is None:
            self.show_playlist(None)

    def create_playlist(self) -> None:
        playlist = create_playlist(self.api, self)
        if playlist is not None:
            self.fill()
            self.select_playlist(playlist.id)

    def rename_playlist(self) -> None:
        if rename_playlist(self.api, self.playlist, self) is not None:
            self.fill()

    def delete_playlist(self) -> None:
        if confirm_deletion(self, self.playlist):
            self.api.delete_user_playlist(self.playlist)
            self.fill()

    def select_playlist(self, playlist_id: int) -> None:
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.data(Qt.UserRole).id == playlist_id:
                self.list_widget.setCurrentItem(item)

    def set_item_playlist(self, item: QListWidgetItem, playlist: UserPlaylist) -> None:
        item.setData(Qt.UserRole, playlist)
        item.setText(
            f"{playlist.name}\n"
            f"{format_songs_total(playlist.song_count, playlist.duration)}"
        )
        pixmap = QPixmap()
        pixmap.loadFromData(self.api.get_user_playlist_cover(playlist) or DEFAULT_COVER)
        icon = QIcon(pixmap)
        # Qt would otherwise tint the image of the selected playlist.
        icon.addPixmap(pixmap, QIcon.Selected)
        item.setIcon(icon)

    def close_details(self) -> None:
        # No current item left, so that selecting this playlist opens it again.
        self.list_widget.setCurrentRow(-1)

    def on_current_item_changed(self, current: QListWidgetItem | None) -> None:
        self.show_playlist(current.data(Qt.UserRole) if current is not None else None)

    def show_playlist(self, playlist: UserPlaylist | None) -> None:
        self.playlist = playlist
        self.clear_songs()
        self.details_widget.setVisible(playlist is not None)
        if playlist is None:
            return

        songs = self.api.get_user_playlist_songs(playlist)
        self.update_details_header()
        for song in songs:
            widget = PlaylistSongWidget(song, None, show_track_number=False)
            widget.play_song_requested.connect(
                lambda s=song, p=playlist: self.play_song_requested.emit(p, s)
            )
            widget.info_requested.connect(self.show_song_info)
            widget.add_to_playlist_requested.connect(self.add_song_to_another_playlist)
            widget.move_requested.connect(self.move_song)
            widget.remove_requested.connect(self.remove_song)
            self.songs_v_layout.addWidget(widget)
            self.song_widgets[song.id] = widget
        self.update_playing_display()
        self.update_move_buttons()

    def add_song_to_another_playlist(self, song: Song) -> None:
        target = show_add_to_playlist_menu(self.api, song, self)
        if target is not None:
            self.refresh_playlist_item(target.id)

    def move_song(self, song: Song, offset: int) -> None:
        self.api.move_song_in_user_playlist(self.playlist, song, offset)
        # Moved in place rather than rebuilt: the list keeps its scroll position.
        widget = self.song_widgets[song.id]
        index = self.songs_v_layout.indexOf(widget)
        self.songs_v_layout.removeWidget(widget)
        self.songs_v_layout.insertWidget(index + offset, widget)
        self.update_move_buttons()

    def remove_song(self, song: Song) -> None:
        self.api.remove_song_from_user_playlist(self.playlist, song)
        widget = self.song_widgets.pop(song.id)
        self.songs_v_layout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()
        self.update_move_buttons()
        self.refresh_playlist_item(self.playlist.id)
        self.playlist = self.list_widget.currentItem().data(Qt.UserRole)
        self.update_details_header()

    def refresh_playlist_item(self, playlist_id: int) -> None:
        playlist = next(p for p in self.api.get_user_playlists() if p.id == playlist_id)
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.data(Qt.UserRole).id == playlist_id:
                self.set_item_playlist(item, playlist)
                return
        # Just created, from the menu of a song.
        self.fill()

    def update_details_header(self) -> None:
        self.cover_thumbnail.bytes = (
            self.api.get_user_playlist_cover(self.playlist) or DEFAULT_COVER
        )
        self.title_lbl.setText(self.playlist.name)
        self.songs_info_lbl.setText(
            format_songs_total(self.playlist.song_count, self.playlist.duration)
        )

    def update_move_buttons(self) -> None:
        last = self.songs_v_layout.count() - 1
        for widget in self.song_widgets.values():
            index = self.songs_v_layout.indexOf(widget)
            widget.move_up_btn.setEnabled(index > 0)
            widget.move_down_btn.setEnabled(index < last)

    def show_song_info(self, song: Song) -> None:
        dialog = SongInfoDialog(self.api, song, self.window())
        dialog.exec()
        if dialog.changed:
            self.song_edited.emit()

    def clear_songs(self) -> None:
        for widget in self.song_widgets.values():
            # deleteLater() alone leaves the widget in the layout (visible and
            # clickable) until the event loop runs: detach it right away.
            self.songs_v_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self.song_widgets.clear()

    def start_playing_song_display(self, song: Song) -> None:
        self.playing_song = song
        self.update_playing_display()

    def stop_current_playing_song_display(self) -> None:
        self.playing_song = None
        self.update_playing_display()

    def update_playing_display(self) -> None:
        for song_id, widget in self.song_widgets.items():
            if self.playing_song is not None and song_id == self.playing_song.id:
                widget.set_playing_display()
            else:
                widget.stop_playing_display()
