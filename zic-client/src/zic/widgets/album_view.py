from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from functools import partial

from zic.models.album import Album, AlbumCover
from zic.models.song import Song
from zic.utils.qt_utils import make_toolbutton, set_label_font_size
from zic.widgets.cover_thumbnail import CoverThumbnail, DEFAULT_COVER
from zic.api import ZicApi


class SongWidget(QWidget):
    play_song_requested = Signal(Song)

    def __init__(self, song: Song) -> None:
        super().__init__()
        self.song: Song = song

        # Layouts
        self.main_h_layout = None

        # Widgets
        self.play_btn = None
        self.title_lbl = None
        self.duration_lbl = None
        self.artist_credit_lbl = None
        self.info_btn = None

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()

    def init_layouts(self) -> None:
        self.main_h_layout = QHBoxLayout(self)

    def init_widgets(self) -> None:
        self.play_btn = make_toolbutton("icons/play.png", tooltip="Play")
        self.title_lbl = QLabel(
            f"{self.song.track_number} - {self.song.title}"
            if self.song.track_number is not None else
            self.song.title
        )
        seconds = int(self.song.duration)
        self.duration_lbl = QLabel(f"{seconds // 60:02d}:{seconds % 60:02d}")
        self.artist_credit_lbl = QLabel(self.song.artist_credit)
        self.info_btn = make_toolbutton("icons/artist.png", tooltip="Info")  # TODO icon

    def set_layout(self) -> None:
        self.main_h_layout.addWidget(self.play_btn)
        self.main_h_layout.addWidget(self.title_lbl)
        self.main_h_layout.addStretch()
        self.main_h_layout.addWidget(self.duration_lbl)
        self.main_h_layout.addWidget(QLabel("-"))
        self.main_h_layout.addWidget(self.artist_credit_lbl)
        self.main_h_layout.addWidget(QLabel("-"))
        self.main_h_layout.addWidget(self.info_btn)

    def set_connections(self) -> None:
        self.play_btn.clicked.connect(lambda: self.play_song_requested.emit(self.song))

    def set_default(self) -> None:
        self.main_h_layout.setAlignment(Qt.AlignLeft)


class AlbumView(QWidget):
    play_album_requested = Signal(Album)
    shuffle_album_requested = Signal(Album)
    play_song_requested = Signal(Album, Song)

    def __init__(self, api: ZicApi) -> None:
        super().__init__()
        self.api: ZicApi = api
        self.album: Album | None = None
        self.cover: AlbumCover | None = None
        self.songs: list[Song] = []

        # Layouts
        self.main_v_layout = None
        self.cover_h_layout = None
        self.cover_v_layout = None
        self.buttons_h_layout = None
        self.songs_v_layout = None

        # Widgets
        self.cover_thumbnail = None
        self.title_lbl = None
        self.artist_lbl = None
        self.genres_lbl = None
        self.play_btn = None
        self.play_random_btn = None
        self.info_btn = None
        self.scroll_area = None
        self.scroll_area_widget = None
        self.song_widgets: list[SongWidget] = []

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()

    def init_layouts(self) -> None:
        self.main_v_layout = QVBoxLayout(self)
        self.cover_h_layout = QHBoxLayout()
        self.cover_v_layout = QVBoxLayout()
        self.buttons_h_layout = QHBoxLayout()
        self.songs_v_layout = QVBoxLayout()

    def init_widgets(self) -> None:
        self.cover_thumbnail = CoverThumbnail(width=250, height=250)
        self.title_lbl = QLabel()
        self.artist_lbl = QLabel()
        self.genres_lbl = QLabel()
        self.play_btn = make_toolbutton("icons/play.png", tooltip="Play")
        self.play_random_btn = make_toolbutton(
            "icons/shuffle.png", tooltip="Play random"
        )
        self.info_btn = make_toolbutton("icons/artist.png", tooltip="Info")  # TODO icon
        self.scroll_area = QScrollArea()
        self.scroll_area_widget = QWidget()

    def set_layout(self) -> None:
        self.main_v_layout.addLayout(self.cover_h_layout)
        self.cover_h_layout.addLayout(self.cover_v_layout)
        self.cover_v_layout.addWidget(self.cover_thumbnail)
        self.cover_v_layout.addWidget(self.title_lbl)
        self.cover_v_layout.addWidget(self.artist_lbl)
        self.cover_v_layout.addWidget(self.genres_lbl)
        self.cover_v_layout.addLayout(self.buttons_h_layout)
        self.buttons_h_layout.addWidget(self.play_btn)
        self.buttons_h_layout.addWidget(self.play_random_btn)
        self.buttons_h_layout.addWidget(self.info_btn)
        self.main_v_layout.addWidget(self.scroll_area)
        self.scroll_area.setWidget(self.scroll_area_widget)
        self.scroll_area_widget.setLayout(self.songs_v_layout)

    def set_connections(self) -> None:
        self.play_btn.clicked.connect(lambda: self.play_album_requested.emit(self.album))
        self.play_random_btn.clicked.connect(lambda: self.shuffle_album_requested.emit(self.album))

    def set_default(self) -> None:
        for layout, alignment in (
            (self.main_v_layout, Qt.AlignTop),
            (self.buttons_h_layout, Qt.AlignCenter),
            (self.songs_v_layout, Qt.AlignTop),
            (self.cover_h_layout, Qt.AlignCenter),
            (self.cover_v_layout, Qt.AlignTop),
            (self.title_lbl, Qt.AlignCenter),
            (self.artist_lbl, Qt.AlignCenter),
            (self.genres_lbl, Qt.AlignCenter),
        ):
            layout.setAlignment(alignment)

        set_label_font_size(self.title_lbl, 12)
        self.scroll_area.setWidgetResizable(True)

    def set_album(self, album: Album, cover: AlbumCover | None) -> None:
        self.album = album
        self.cover = cover
        self.cover_thumbnail.bytes = (
            cover.thumbnail if cover is not None else DEFAULT_COVER
        )
        self.title_lbl.setText(album.name)
        self.artist_lbl.setText(album.artist.name)
        self.genres_lbl.setText(", ".join(g.name for g in album.genres))
        self.songs = self.api.get_album_songs(self.album)
        self.clear_songs()
        for song in self.songs:
            widget = SongWidget(song)
            widget.play_song_requested.connect(partial(self.play_song_requested.emit, self.album, song))
            self.songs_v_layout.addWidget(widget)
            self.song_widgets.append(widget)

    def clear_songs(self) -> None:
        for song_widget in self.song_widgets:
            song_widget.deleteLater()
        self.song_widgets.clear()
