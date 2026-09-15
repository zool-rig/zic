import importlib.metadata

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from zic.api import ZicApi
from zic.config import get_user_config
from zic.utils.qt_utils import make_toolbutton, SignalsOFF
from zic.widgets.rules import VRule, HRule
from zic.widgets.artists_filter_widget import ArtistsFilterWidget
from zic.widgets.genres_filter_widget import GenresFilterWidget
from zic.widgets.album_explorer import AlbumExplorer
from zic.widgets.player_widget import PlayerWidget
from zic.models.album import Album, AlbumCover
from zic.widgets.album_view import AlbumView
from zic.models.song import Song
from zic.models.artist import Artist
from zic.resources import get_resource


class ZicUI(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.api: ZicApi = ZicApi()

        # Layouts
        self.main_v_layout = None
        self.main_h_layout = None
        self.side_bar_v_layout = None
        self.random_btn_h_layout = None
        self.reload_btn_h_layout = None
        self.filter_tab_v_layout = None

        # Widgets
        self.play_random_btn = None
        self.reload_btn = None
        self.filter_tab_frame = None
        self.toggle_artists_btn = None
        self.toggle_genres_btn = None
        self.h_splitter = None
        self.filter_stacked_widget = None
        self.artist_filter_widget = None
        self.genre_filter_widget = None
        self.album_explorer = None
        self.album_view = None
        self.player_widget = None

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()
        # self.set_style_sheet()

        # timer = QTimer(self)
        # timer.timeout.connect(self.set_style_sheet)
        # timer.start(1000)

    def init_layouts(self) -> None:
        self.main_v_layout = QVBoxLayout(self)
        self.main_h_layout = QHBoxLayout()
        self.side_bar_v_layout = QVBoxLayout()
        self.random_btn_h_layout = QHBoxLayout()
        self.reload_btn_h_layout = QHBoxLayout()
        self.filter_tab_v_layout = QVBoxLayout()

    def init_widgets(self) -> None:
        self.play_random_btn = make_toolbutton(
            "icons/shuffle.png", tooltip="Play random"
        )
        self.reload_btn = make_toolbutton("icons/refresh-arrow.png", tooltip="Reload")
        self.filter_tab_frame = QFrame()
        self.toggle_artists_btn = make_toolbutton(
            "icons/artist.png", tooltip="Toggle artists view", checkable=True
        )
        self.toggle_genres_btn = make_toolbutton(
            "icons/tag.png", tooltip="Toggle genres view", checkable=True
        )
        self.h_splitter = QSplitter(Qt.Horizontal)
        self.filter_stacked_widget = QStackedWidget()
        self.artist_filter_widget = ArtistsFilterWidget(self)
        self.genre_filter_widget = GenresFilterWidget(self)
        self.album_explorer = AlbumExplorer(self.api)
        self.album_view = AlbumView(self.api)
        self.player_widget = PlayerWidget(self)  # TODO replace by api if possible

    def set_layout(self) -> None:
        self.main_v_layout.addLayout(self.main_h_layout)
        self.main_h_layout.addLayout(self.side_bar_v_layout)
        self.side_bar_v_layout.addLayout(self.random_btn_h_layout)
        self.random_btn_h_layout.addWidget(self.play_random_btn)
        self.side_bar_v_layout.addLayout(self.reload_btn_h_layout)
        self.reload_btn_h_layout.addWidget(self.reload_btn)
        self.side_bar_v_layout.addWidget(self.filter_tab_frame)
        self.filter_tab_frame.setLayout(self.filter_tab_v_layout)
        self.filter_tab_v_layout.addWidget(self.toggle_artists_btn)
        self.filter_tab_v_layout.addWidget(self.toggle_genres_btn)
        self.main_h_layout.addWidget(VRule())
        self.main_h_layout.addWidget(self.h_splitter)
        self.h_splitter.addWidget(self.filter_stacked_widget)
        self.filter_stacked_widget.addWidget(self.artist_filter_widget)
        self.filter_stacked_widget.addWidget(self.genre_filter_widget)
        self.h_splitter.addWidget(self.album_explorer)
        self.h_splitter.addWidget(self.album_view)
        self.main_v_layout.addWidget(HRule(), Qt.AlignBottom)
        self.main_v_layout.addWidget(self.player_widget)

    def set_connections(self) -> None:
        self.toggle_artists_btn.clicked.connect(
            lambda: self.on_filter_toggled(self.toggle_artists_btn)
        )
        self.toggle_genres_btn.clicked.connect(
            lambda: self.on_filter_toggled(self.toggle_genres_btn)
        )
        self.play_random_btn.clicked.connect(self.on_play_random_btn_clicked)
        self.reload_btn.clicked.connect(self.reload)
        self.album_explorer.album_selected.connect(self.on_album_selected)
        self.album_view.play_album_requested.connect(self.play_album)
        self.album_view.shuffle_album_requested.connect(self.shuffle_album)
        self.album_view.play_song_requested.connect(self.play_song)
        self.player_widget.song_started.connect(self.on_song_started)
        self.player_widget.song_paused.connect(self.on_song_paused)
        self.player_widget.song_finished.connect(self.on_song_finished)
        self.player_widget.song_url_clicked.connect(self.jump_to_song)
        self.player_widget.album_url_clicked.connect(self.jump_to_album)
        self.player_widget.artist_url_clicked.connect(self.jump_to_artists)

    def set_default(self) -> None:
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle(f"ZIC - {importlib.metadata.version('zic-client')}")

        for layout, alignment in (
            (self.main_v_layout, Qt.AlignTop),
            (self.main_h_layout, Qt.AlignLeft),
            (self.side_bar_v_layout, Qt.AlignTop),
            (self.random_btn_h_layout, Qt.AlignCenter),
            (self.filter_tab_v_layout, Qt.AlignTop),
        ):
            layout.setAlignment(alignment)

        self.filter_stacked_widget.hide()
        self.album_view.hide()
        self.h_splitter.setStretchFactor(0, 1)
        self.h_splitter.setStretchFactor(1, 3)
        self.h_splitter.setStretchFactor(2, 1)

    def set_style_sheet(self) -> None:
        qss_path = get_resource("style/style.qss")
        icons_path = get_resource("icons")
        with open(qss_path, "r") as f:
            stylesheet = f.read()
        # Replace placeholder with actual icon path
        stylesheet = stylesheet.replace("{ICON_PATH}", icons_path)
        self.setStyleSheet(stylesheet)

    def closeEvent(self, _: QEvent) -> None:
        self.album_explorer.shutdown()
        self.api.disconnect()
        get_user_config().save()

    def on_filter_toggled(self, button: QToolButton) -> None:
        other_button, index = (
            (self.toggle_genres_btn, 0)
            if button == self.toggle_artists_btn
            else (self.toggle_artists_btn, 1)
        )
        if button.isChecked():
            other_button.setChecked(False)
            self.filter_stacked_widget.show()
            self.filter_stacked_widget.setCurrentIndex(index)
            with SignalsOFF(
                self.artist_filter_widget.list_widget,
                self.genre_filter_widget.list_widget,
            ):
                if other_button == self.toggle_artists_btn:
                    self.artist_filter_widget.list_widget.clearSelection()
                else:
                    self.genre_filter_widget.list_widget.clearSelection()
        else:
            self.filter_stacked_widget.hide()

    def on_play_random_btn_clicked(self) -> None:
        playlist = self.api.get_random_playlist()
        self.player_widget.set_playlist(playlist)
        self.player_widget.play()

    def reload(self) -> None:
        self.api.invalidate_caches()
        self.artist_filter_widget.clear()
        self.genre_filter_widget.clear()

    def on_album_selected(self, album: Album, cover: AlbumCover | None) -> None:
        self.album_view.show()
        self.album_view.set_album(album, cover)

    def play_album(self, album: Album) -> None:
        playlist = self.api.get_album_playlist(album)
        self.player_widget.set_playlist(playlist)
        self.player_widget.play()

    def shuffle_album(self, album: Album) -> None:
        playlist = self.api.get_shuffle_album_playlist(album)
        self.player_widget.set_playlist(playlist)
        self.player_widget.play()

    def play_song(self, album: Album, song: Song) -> None:
        playlist = self.api.get_song_playlist(album, song)
        self.player_widget.set_playlist(playlist)
        self.player_widget.play()

    def on_song_started(self, song: Song) -> None:
        self.album_view.start_playing_song_display(song)
        self.album_explorer.start_playing_album_display(song.album)

    def on_song_paused(self, _: Song) -> None:
        self.album_view.stop_current_playing_song_display()
        self.album_explorer.stop_current_playing_album_display()

    def on_song_finished(self, _: Song) -> None:
        self.album_view.stop_current_playing_song_display()
        self.album_explorer.stop_current_playing_album_display()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key_bindings = {v: k for k, v in get_user_config().key_bindings.items()}
        action_name = key_bindings.get(int(event.key()))
        if action_name is None:
            return
        
        action = {
            "play/pause": self.toggle_play_pause,
            "mute": self.mute_sound,
            "next-song": self.play_next_song,
            "previous-song": self.play_previous_song,
            "reload": self.reload,
            "shuffle": self.on_play_random_btn_clicked,
            "advance": self.advance,
            "rewind": self.rewind,
            "volume_up": self.volume_up,
            "volume_down": self.volume_donw,
        }[action_name]

        action()

    def toggle_play_pause(self) -> None:
        self.player_widget.toggle_play_pause()

    def mute_sound(self) -> None:
        self.player_widget.volume_slider.toggle_mute()

    def play_next_song(self) -> None:
        self.player_widget.next()

    def play_previous_song(self) -> None:
        self.player_widget.previous()

    def advance(self) -> None:
        self.player_widget.playback_widget.advance(10 if QApplication.keyboardModifiers() == Qt.ControlModifier else 5)

    def rewind(self) -> None:
        self.player_widget.playback_widget.rewind(10 if QApplication.keyboardModifiers() == Qt.ControlModifier else 5)

    def volume_up(self) -> None:
        self.player_widget.volume_slider.volume_up(5)

    def volume_donw(self) -> None:
        self.player_widget.volume_slider.volume_down(5)

    def jump_to_song(self, song: Song) -> None:
        self.jump_to_album(song.album)
        QTimer.singleShot(0, lambda: self.album_view.scroll_to_song(song))

    def jump_to_album(self, album: Album) -> None:
        self.album_view.show()
        self.album_view.set_album(album, self.api.get_album_cover_thumbnail(album))
        self.album_view.start_playing_song_display(self.player_widget.current_song)
        self.album_explorer.start_playing_album_display(album)

    def jump_to_artists(self, artists: list[Artist]) -> None:
        self.artist_filter_widget.select_artists(artists)


class GlobalKeyFilter(QObject):
    def __init__(self, app_instance: ZicUI) -> None:
        super().__init__()
        self.app_instance: ZicUI = app_instance

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() in {Qt.Key_Space, Qt.Key_Left, Qt.Key_Right}:
            self.app_instance.keyPressEvent(event)
            return True
        return super().eventFilter(obj, event)
