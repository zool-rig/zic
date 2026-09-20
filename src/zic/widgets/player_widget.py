from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QObject, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices

from zic.utils.qt_utils import make_toolbutton
from zic.models.song import Song
from zic.models.album import Album
from zic.models.artist import Artist
from zic.models.playlist import Playlist
from zic.widgets.cover_thumbnail import CoverThumbnail
from zic.config import get_user_config
from zic.resources import get_resource
from zic.widgets.url_label import UrlLabel


class SongInfoWidget(QWidget):
    LABEL_WIDTH = 260
    LABEL_HEIGHT = 22

    song_url_clicked = Signal(Song)
    album_url_clicked = Signal(Album)
    artist_url_clicked = Signal(list)

    def __init__(self, app: QWidget) -> None:
        super().__init__()
        self.app: QWidget = app
        self.song: Song | None = None

        # Layouts
        self.main_h_layout = None
        self.v_layout = None

        # Widgets
        self.cover_image = None
        self.song_title_lbl = None
        self.album_title_lbl = None
        self.artist_name_lbl = None

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()

    def init_layouts(self) -> None:
        self.main_h_layout = QHBoxLayout(self)
        self.v_layout = QVBoxLayout()

    def init_widgets(self) -> None:
        self.cover_image = CoverThumbnail()
        self.song_title_lbl = UrlLabel("🎵 : -", clickable=False)
        self.album_title_lbl = UrlLabel("💿 : -", clickable=False)
        self.artist_name_lbl = UrlLabel("🎤 : -", clickable=False)

    def set_layout(self) -> None:
        self.main_h_layout.addWidget(self.cover_image)
        self.main_h_layout.addLayout(self.v_layout)
        self.v_layout.addWidget(self.song_title_lbl)
        self.v_layout.addWidget(self.album_title_lbl)
        self.v_layout.addWidget(self.artist_name_lbl)

    def set_connections(self) -> None:
        self.song_title_lbl.clicked.connect(
            lambda _: self.song_url_clicked.emit(self.song)
        )
        self.album_title_lbl.clicked.connect(
            lambda _: self.album_url_clicked.emit(self.song.album)
        )
        self.artist_name_lbl.clicked.connect(
            lambda _: self.artist_url_clicked.emit(
                self.app.api.get_song_artists(self.song)
            )
        )

    def set_default(self) -> None:
        for label in (
            self.song_title_lbl,
            self.album_title_lbl,
            self.artist_name_lbl,
        ):
            label.setFixedSize(self.LABEL_WIDTH, self.LABEL_HEIGHT)

    def set_label_text(self, label: QLabel, text: str) -> None:
        label.setToolTip(text)
        label.setText(
            label.fontMetrics().elidedText(
                text,
                Qt.TextElideMode.ElideRight,
                label.contentsRect().width(),
            )
        )

    def set_current_song(self, song: Song | None) -> None:
        if song is not None:
            cover = self.app.api.get_album_cover_thumbnail(song.album)
            if cover is not None:
                self.cover_image.bytes = cover.thumbnail
            else:
                self.cover_image.clear()
        else:
            self.cover_image.clear()
        self.set_label_text(self.song_title_lbl, f"🎵 : {song.title if song else '-'}")
        self.set_label_text(
            self.album_title_lbl, f"💿 : {song.album.name if song else '-'}"
        )
        self.set_label_text(
            self.artist_name_lbl, f"🎤 : {song.artist_credit if song else '-'}"
        )
        for label in (self.song_title_lbl, self.album_title_lbl, self.artist_name_lbl):
            label.clickable = song is not None
        self.song = song


class LikesWidget(QWidget):
    song_liked = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.count: int = 0

        # Layouts
        self.main_v_layout = None
        self.top_h_layout = None
        self.bot_h_layout = None

        # Widgets
        self.likes_lbl = None
        self.like_btn = None
        self.dislike_btn = None

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
        self.bot_h_layout = QHBoxLayout()

    def init_widgets(self) -> None:
        self.likes_lbl = QLabel("Likes : 0")
        self.like_btn = make_toolbutton("icons/like.png", tooltip="Like")
        self.dislike_btn = make_toolbutton("icons/dislike.png", tooltip="Dislike")

    def set_layout(self) -> None:
        self.main_v_layout.addLayout(self.top_h_layout)
        self.top_h_layout.addWidget(self.likes_lbl)
        self.main_v_layout.addLayout(self.bot_h_layout)
        self.bot_h_layout.addWidget(self.like_btn)
        self.bot_h_layout.addWidget(self.dislike_btn)

    def set_connections(self) -> None:
        self.like_btn.clicked.connect(self.on_song_liked)
        self.dislike_btn.clicked.connect(self.on_song_disliked)

    def set_default(self) -> None:
        self.main_v_layout.setAlignment(Qt.AlignCenter)
        self.top_h_layout.setAlignment(Qt.AlignCenter)

    def set_like_count(self, count: int) -> None:
        self.count = count
        self.likes_lbl.setText(f"Likes : {count}")

    def on_song_liked(self) -> None:
        self.count += 1
        self.likes_lbl.setText(f"Likes : {self.count}")
        self.song_liked.emit(1)

    def on_song_disliked(self) -> None:
        self.count -= 1
        self.likes_lbl.setText(f"Likes : {self.count}")
        self.song_liked.emit(-1)


class PlaybackWidget(QWidget):
    song_resumed = Signal()
    song_paused = Signal()
    song_finished = Signal()
    previous_requested = Signal()
    next_requested = Signal()

    def __init__(self, media_player: QMediaPlayer) -> None:
        super().__init__()
        self.media_player: QMediaPlayer = media_player
        self.current_song: Song | None = None
        self.play_icon: QIcon = QIcon(get_resource("icons/play.png"))
        self.pause_icon: QIcon = QIcon(get_resource("icons/pause.png"))
        self.progress_timer: QTimer = QTimer(self)
        self.playing: bool = False

        # Layouts
        self.main_v_layout = None
        self.top_h_layout = None
        self.bottom_h_layout = None

        # Widgets
        self.previous_btn = None
        self.play_btn = None
        self.next_btn = None
        self.current_time_lbl = None
        self.time_slider = None
        self.total_time_lbl = None

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
        self.bottom_h_layout = QHBoxLayout()

    def init_widgets(self) -> None:
        self.previous_btn = make_toolbutton("icons/previous.png", tooltip="Previous")
        self.play_btn = make_toolbutton(
            "icons/play.png", tooltip="Previous", checkable=True
        )
        self.next_btn = make_toolbutton("icons/next.png", tooltip="Previous")
        self.current_time_lbl = QLabel("00:00")
        self.time_slider = QSlider(Qt.Horizontal)
        self.total_time_lbl = QLabel("00:00")

    def set_layout(self) -> None:
        self.main_v_layout.addLayout(self.top_h_layout)
        self.top_h_layout.addWidget(self.previous_btn)
        self.top_h_layout.addWidget(self.play_btn)
        self.top_h_layout.addWidget(self.next_btn)
        self.main_v_layout.addLayout(self.bottom_h_layout)
        self.bottom_h_layout.addWidget(self.current_time_lbl)
        self.bottom_h_layout.addWidget(self.time_slider)
        self.bottom_h_layout.addWidget(self.total_time_lbl)

    def set_connections(self) -> None:
        self.play_btn.clicked.connect(self.on_play_btn_clicked)
        self.time_slider.sliderMoved.connect(self.on_time_slider_moved)
        self.progress_timer.timeout.connect(self.progress)
        self.media_player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.previous_btn.clicked.connect(self.previous_requested.emit)
        self.next_btn.clicked.connect(self.next_requested.emit)

    def set_default(self) -> None:
        for layout, alignment in (
            (self.main_v_layout, Qt.AlignCenter),
            (self.top_h_layout, Qt.AlignCenter),
            (self.bottom_h_layout, Qt.AlignCenter),
        ):
            layout.setAlignment(alignment)

        self.play_btn.setFixedSize(30, 30)
        self.time_slider.setFixedWidth(300)
        self.time_slider.installEventFilter(self)
        self.progress_timer.setInterval(500)

    def set_current_song(self, song: Song | None) -> None:
        self.current_song = song
        self.current_time_lbl.setText("00:00")
        self.time_slider.setValue(0)
        if song is None:
            self.time_slider.setRange(0, 0)
            self.total_time_lbl.setText("00:00")
            self.media_player.stop()
            return

        seconds = int(song.duration)
        self.time_slider.setRange(0, seconds * 1000)
        self.total_time_lbl.setText(f"{seconds // 60:02d}:{seconds % 60:02d}")

    def play(self) -> None:
        self.play_btn.setChecked(True)
        self.play_btn.setIcon(self.pause_icon)
        self.media_player.play()
        self.progress_timer.start()
        self.playing = True
        self.song_resumed.emit()

    def pause(self) -> None:
        self.play_btn.setChecked(False)
        self.play_btn.setIcon(self.play_icon)
        self.media_player.pause()
        self.progress_timer.stop()
        self.playing = False
        self.song_paused.emit()

    def on_play_btn_clicked(self) -> None:
        if self.play_btn.isChecked():
            self.play()
        else:
            self.pause()

    def on_time_slider_moved(self, elapsed: int) -> None:
        self.seek(elapsed)

    def seek(self, elapsed: int) -> None:
        self.media_player.setPosition(elapsed)
        self.set_elapsed_time(elapsed)
        self.time_slider.setValue(elapsed)

    def set_elapsed_time(self, elapsed: int) -> None:
        seconds = elapsed // 1000
        self.current_time_lbl.setText(f"{seconds // 60:02d}:{seconds % 60:02d}")

    def progress(self) -> None:
        elapsed = self.media_player.position()
        self.set_elapsed_time(elapsed)
        self.time_slider.setValue(elapsed)

    def on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return

        self.pause()
        self.song_finished.emit()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.time_slider and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                option = QStyleOptionSlider()
                self.time_slider.initStyleOption(option)
                handle_rect = self.time_slider.style().subControlRect(
                    QStyle.ComplexControl.CC_Slider,
                    option,
                    QStyle.SubControl.SC_SliderHandle,
                    self.time_slider,
                )
                if handle_rect.contains(event.position().toPoint()):
                    return super().eventFilter(watched, event)

                elapsed = QStyle.sliderValueFromPosition(
                    self.time_slider.minimum(),
                    self.time_slider.maximum(),
                    int(event.position().x()),
                    self.time_slider.width(),
                    self.time_slider.invertedAppearance(),
                )
                self.seek(elapsed)
                return True

        return super().eventFilter(watched, event)

    def advance(self, value: int) -> None:
        elapsed = min(
            self.media_player.position() + value * 1000, self.time_slider.maximum()
        )
        self.seek(elapsed)

    def rewind(self, value: int) -> None:
        elapsed = max(
            self.media_player.position() - value * 1000, self.time_slider.minimum()
        )
        self.seek(elapsed)


class VolumeSlider(QWidget):
    volume_changed = Signal(int)
    muted = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.volume_icon: QIcon = QIcon(get_resource("icons/volume.png"))
        self.mute_icon: QIcon = QIcon(get_resource("icons/mute.png"))

        # Layouts
        self.main_h_layout = None

        # Widgets
        self.mute_btn = None
        self.slider = None

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
        self.mute_btn = make_toolbutton(
            "icons/mute.png" if get_user_config().muted else "icons/volume.png",
            tooltip="Mute",
            checkable=True,
        )
        self.slider = QSlider(Qt.Horizontal)

    def set_layout(self) -> None:
        self.main_h_layout.addWidget(self.mute_btn)
        self.main_h_layout.addWidget(self.slider)

    def set_connections(self) -> None:
        self.slider.sliderMoved.connect(self.on_volume_changed)
        self.mute_btn.clicked.connect(self.on_mute_clicked)

    def set_default(self) -> None:
        self.slider.setValue(get_user_config().volume)
        self.slider.setFixedWidth(150)
        self.mute_btn.setChecked(get_user_config().muted)
        self.main_h_layout.setAlignment(Qt.AlignRight)

    def on_volume_changed(self, value: int) -> None:
        get_user_config().volume = value
        self.volume_changed.emit(value)

    def on_mute_clicked(self) -> None:
        muted = self.mute_btn.isChecked()
        self.mute_btn.setIcon(self.mute_icon if muted else self.volume_icon)
        self.muted.emit(muted)
        get_user_config().muted = muted

    def toggle_mute(self) -> None:
        self.mute_btn.toggle()
        self.on_mute_clicked()

    def volume_up(self, value: int) -> None:
        maximum = self.slider.maximum()
        current_value = self.slider.value()
        new_value = min(current_value + value, maximum)
        if new_value != current_value:
            self.slider.setValue(new_value)
            self.on_volume_changed(new_value)

    def volume_down(self, value: int) -> None:
        minimum = self.slider.minimum()
        current_value = self.slider.value()
        new_value = max(current_value - value, minimum)
        if new_value != current_value:
            self.slider.setValue(new_value)
            self.on_volume_changed(new_value)


class PlayerWidget(QWidget):
    song_started = Signal(Song)
    song_paused = Signal(Song)
    song_finished = Signal(Song)
    song_url_clicked = Signal(Song)
    album_url_clicked = Signal(Album)
    artist_url_clicked = Signal(list)

    def __init__(self, app: QWidget) -> None:
        super().__init__()
        self.app: QWidget = app
        self.playlist: Playlist | None = None
        self._current_song: Song | None = None
        self.current_play_id: int | None = None
        self.media_player: QMediaPlayer = QMediaPlayer()
        self.audio_output: QAudioOutput = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.devices: QMediaDevices = QMediaDevices(self)

        # Layouts
        self.main_h_layout = None

        # Widgets
        self.song_info_widget = None
        self.likes_widget = None
        self.playback_widget = None
        self.volume_slider = None

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
        self.song_info_widget = SongInfoWidget(self.app)
        self.likes_widget = LikesWidget()
        self.playback_widget = PlaybackWidget(self.media_player)
        self.volume_slider = VolumeSlider()

    def set_layout(self) -> None:
        self.main_h_layout.addWidget(self.song_info_widget)
        self.main_h_layout.addWidget(self.likes_widget)
        self.main_h_layout.addStretch()
        self.main_h_layout.addWidget(self.playback_widget)
        self.main_h_layout.addStretch()
        self.main_h_layout.addWidget(self.volume_slider)

    def set_connections(self) -> None:
        self.volume_slider.volume_changed.connect(
            lambda v: self.audio_output.setVolume(v / 100)
        )
        self.volume_slider.muted.connect(self.audio_output.setMuted)
        self.playback_widget.song_finished.connect(self.on_song_finished)
        self.playback_widget.song_finished.connect(self.next)
        self.playback_widget.previous_requested.connect(self.previous)
        self.playback_widget.next_requested.connect(self.next)
        self.likes_widget.song_liked.connect(self.on_current_song_liked)
        self.devices.audioOutputsChanged.connect(self.on_audio_outputs_changed)
        self.playback_widget.song_paused.connect(
            lambda: self.song_paused.emit(self.current_song)
        )
        self.playback_widget.song_resumed.connect(
            lambda: self.song_started.emit(self.current_song)
        )
        self.song_info_widget.song_url_clicked.connect(self.song_url_clicked)
        self.song_info_widget.album_url_clicked.connect(self.album_url_clicked)
        self.song_info_widget.artist_url_clicked.connect(self.artist_url_clicked)

    def on_song_finished(self) -> None:
        if self.current_song is not None:
            self.song_finished.emit(self.current_song)
        self.current_play_id = None

    def set_default(self) -> None:
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Maximum)
        self.setEnabled(False)
        self.audio_output.setVolume(get_user_config().volume / 100)
        self.audio_output.setMuted(get_user_config().muted)

    @property
    def current_song(self) -> Song | None:
        return self._current_song

    @current_song.setter
    def current_song(self, song: Song | None) -> None:
        self._current_song = song
        self.song_info_widget.set_current_song(song)
        self.likes_widget.set_like_count(song.like_count if song is not None else 0)
        if song is not None:
            self.media_player.setSource(
                QUrl.fromLocalFile(self.app.api.get_song_path(self.current_song))
            )
        self.playback_widget.set_current_song(song)

    def set_playlist(self, playlist: Playlist | None) -> None:
        self.playlist = playlist
        self.current_song = self.playlist.next()
        self.setEnabled(self.playlist is not None and self.current_song is not None)

    def play(self) -> None:
        if self.current_song is None:
            raise ValueError(f"No song to play.")
        if self.current_play_id is None:
            self.current_play_id = self.app.api.record_song_play(self.current_song)
        self.playback_widget.play()
        self.song_started.emit(self.current_song)

    def mark_current_play_skipped(self) -> None:
        if self.current_play_id is None:
            return

        self.app.api.mark_play_skipped(self.current_play_id)
        self.current_play_id = None

    def next(self) -> None:
        self.mark_current_play_skipped()
        if self.playlist is None:
            return

        self.current_song = self.playlist.next()
        if self.current_song is not None:
            self.play()

    def previous(self) -> None:
        if self.playlist is None or not self.playlist.has_previous():
            return

        self.mark_current_play_skipped()
        self.current_song = self.playlist.previous()
        if self.current_song is not None:
            self.play()

    def on_current_song_liked(self, value: int) -> None:
        self.current_song.like_count += value
        self.app.api.sync_song(self.current_song)

    def on_audio_outputs_changed(self) -> None:
        new_default = QMediaDevices.defaultAudioOutput()
        if new_default != self.audio_output.device():
            self.audio_output.setDevice(new_default)

    def toggle_play_pause(self) -> None:
        if self.playback_widget.playing:
            self.playback_widget.pause()
        else:
            self.playback_widget.play()
