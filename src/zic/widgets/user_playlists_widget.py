from PySide6.QtCore import Qt, Signal
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
from zic.ingestor.ingest import PLAYLISTS_DIR
from zic.models.song import Song
from zic.models.user_playlist import UserPlaylist
from zic.utils.formatting import format_songs_info, format_songs_total
from zic.utils.qt_utils import make_toolbutton, set_label_font_size
from zic.widgets.album_view import SongWidget


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
        self.song_widgets: dict[int, SongWidget] = {}

        # Layouts
        self.main_v_layout = None
        self.details_v_layout = None
        self.buttons_h_layout = None
        self.songs_v_layout = None

        # Widgets
        self.empty_lbl = None
        self.splitter = None
        self.list_widget = None
        self.details_widget = None
        self.title_lbl = None
        self.songs_info_lbl = None
        self.play_btn = None
        self.play_random_btn = None
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
        self.details_v_layout = QVBoxLayout()
        self.buttons_h_layout = QHBoxLayout()
        self.songs_v_layout = QVBoxLayout()

    def init_widgets(self) -> None:
        self.empty_lbl = QLabel(
            "No playlist yet. Put songs in a folder of "
            f"{PLAYLISTS_DIR}/ at the root of your library, then check for new "
            "songs: each folder becomes a playlist."
        )
        self.splitter = QSplitter(Qt.Horizontal)
        self.list_widget = QListWidget()
        self.details_widget = QWidget()
        self.title_lbl = QLabel()
        self.songs_info_lbl = QLabel()
        self.play_btn = make_toolbutton("icons/play.png", tooltip="Play")
        self.play_random_btn = make_toolbutton(
            "icons/shuffle.png", tooltip="Play random"
        )
        self.scroll_area = QScrollArea()
        self.scroll_area_widget = QWidget()

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.empty_lbl)
        self.main_v_layout.addWidget(self.splitter)
        self.splitter.addWidget(self.list_widget)
        self.splitter.addWidget(self.details_widget)
        self.details_widget.setLayout(self.details_v_layout)
        self.details_v_layout.addWidget(self.title_lbl)
        self.details_v_layout.addWidget(self.songs_info_lbl)
        self.details_v_layout.addLayout(self.buttons_h_layout)
        self.buttons_h_layout.addWidget(self.play_btn)
        self.buttons_h_layout.addWidget(self.play_random_btn)
        self.details_v_layout.addWidget(self.scroll_area)
        self.scroll_area.setWidget(self.scroll_area_widget)
        self.scroll_area_widget.setLayout(self.songs_v_layout)

    def set_connections(self) -> None:
        self.list_widget.currentItemChanged.connect(self.on_current_item_changed)
        self.play_btn.clicked.connect(
            lambda: self.play_playlist_requested.emit(self.playlist)
        )
        self.play_random_btn.clicked.connect(
            lambda: self.shuffle_playlist_requested.emit(self.playlist)
        )

    def set_default(self) -> None:
        self.buttons_h_layout.setAlignment(Qt.AlignCenter)
        self.songs_v_layout.setAlignment(Qt.AlignTop)
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.songs_info_lbl.setAlignment(Qt.AlignCenter)
        set_label_font_size(self.title_lbl, 12)
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
            item = QListWidgetItem(
                f"{playlist.name}\n"
                f"{format_songs_total(playlist.song_count, playlist.duration)}"
            )
            item.setData(Qt.UserRole, playlist)
            self.list_widget.addItem(item)
            if playlist.id == selected_id:
                self.list_widget.setCurrentItem(item)

        self.empty_lbl.setVisible(not playlists)
        self.splitter.setVisible(bool(playlists))
        if self.playlist is None:
            self.show_playlist(None)

    def on_current_item_changed(self, current: QListWidgetItem | None) -> None:
        self.show_playlist(current.data(Qt.UserRole) if current is not None else None)

    def show_playlist(self, playlist: UserPlaylist | None) -> None:
        self.playlist = playlist
        self.clear_songs()
        self.details_widget.setVisible(playlist is not None)
        if playlist is None:
            return

        songs = self.api.get_user_playlist_songs(playlist)
        self.title_lbl.setText(playlist.name)
        self.songs_info_lbl.setText(format_songs_info(songs))
        for song in songs:
            widget = SongWidget(song, None, show_track_number=False)
            widget.play_song_requested.connect(
                lambda s=song, p=playlist: self.play_song_requested.emit(p, s)
            )
            widget.info_requested.connect(self.show_song_info)
            self.songs_v_layout.addWidget(widget)
            self.song_widgets[song.id] = widget
        self.update_playing_display()

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
