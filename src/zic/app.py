import importlib.metadata

from PySide6.QtCore import QEvent, QObject, QProcess, QSize, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QMenuBar,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidgetAction,
    QWidget,
)

from zic.api import ZicApi
from zic.config import get_app_config, get_user_config
from zic.models.album import Album, AlbumCover
from zic.models.artist import Artist
from zic.models.song import Song
from zic.resources import get_resource
from zic.utils.qt_utils import SignalsOFF, make_toolbutton, named_widget
from zic.widgets.album_explorer import AlbumExplorer
from zic.widgets.album_view import AlbumView
from zic.widgets.artists_filter_widget import ArtistsFilterWidget
from zic.widgets.dyn_label import DynLabel
from zic.widgets.genres_filter_widget import GenresFilterWidget
from zic.widgets.player_widget import PlayerWidget
from zic.widgets.rules import HRule, VRule


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
        self.menu_bar = None
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

        # Menus
        self.database_menu = None
        self.check_for_new_songs_action = None
        self.rescan_action = None
        self.help_menu = None
        self.about_action = None
        self.compute_genres_action = None

        self.ingest_process = QProcess(self)
        self.compute_genres_process = QProcess(self)

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.init_menu_bar()
        self.set_layout()
        self.set_connections()
        self.set_default()
        self.set_style_sheet()

        # timer = QTimer(self)
        # timer.timeout.connect(self.set_style_sheet)
        # timer.start(2000)

    def init_layouts(self) -> None:
        self.main_v_layout = QVBoxLayout(self)
        self.main_h_layout = QHBoxLayout()
        self.side_bar_v_layout = QVBoxLayout()
        self.random_btn_h_layout = QHBoxLayout()
        self.reload_btn_h_layout = QHBoxLayout()
        self.filter_tab_v_layout = QVBoxLayout()

    def init_widgets(self) -> None:
        self.menu_bar = QMenuBar()
        self.play_random_btn = make_toolbutton(
            "icons/shuffle.png", tooltip="Play random"
        )
        self.reload_btn = make_toolbutton("icons/refresh-arrow.png", tooltip="Reload")
        self.filter_tab_frame = named_widget(QFrame, "ContainerFrame")
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
        self.player_widget = PlayerWidget(self)

    def init_menu_bar(self) -> None:
        self.database_menu = self.menu_bar.addMenu("Database")
        last_ingest_lbl = named_widget(
            DynLabel,
            "LabelAction",
            self.get_last_ingest_date,
            prefix="Last scan : ",
        )
        last_ingest_lbl.setFixedWidth(200)
        action = QWidgetAction(self.database_menu)
        action.setDefaultWidget(last_ingest_lbl)
        self.database_menu.addAction(action)

        self.check_for_new_songs_action = self.database_menu.addAction(
            "Check for new songs"
        )
        self.check_for_new_songs_action.triggered.connect(self.check_for_new_songs)
        self.rescan_action = self.database_menu.addAction("Full rescan")
        self.rescan_action.triggered.connect(
            lambda: self.check_for_new_songs(rescan=True)
        )
        self.compute_genres_action = self.database_menu.addAction(
            "Compute genre positions"
        )
        self.compute_genres_action.triggered.connect(self.compute_genres)

        self.help_menu = self.menu_bar.addMenu("Help")
        self.about_action = self.help_menu.addAction("About")
        self.about_action.triggered.connect(self.show_about_dialog)

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.menu_bar)
        self.main_v_layout.addLayout(self.main_h_layout)
        self.main_h_layout.addLayout(self.side_bar_v_layout)
        self.side_bar_v_layout.addLayout(self.random_btn_h_layout)
        self.random_btn_h_layout.addWidget(self.play_random_btn)
        self.side_bar_v_layout.addLayout(self.reload_btn_h_layout)
        self.reload_btn_h_layout.addWidget(self.reload_btn)
        self.side_bar_v_layout.addWidget(HRule())
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
        self.ingest_process.finished.connect(self.on_ingest_process_finished)
        self.ingest_process.errorOccurred.connect(self.on_ingest_process_failed)
        self.compute_genres_process.finished.connect(self.on_compute_genres_finished)
        self.compute_genres_process.errorOccurred.connect(self.on_compute_genres_failed)

    def set_default(self) -> None:
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle(f"ZIC - {importlib.metadata.version('zic')}")
        self.setWindowIcon(QIcon(get_resource("icons/zic.ico")))

        for layout, alignment in (
            (self.main_h_layout, Qt.AlignLeft),
            (self.side_bar_v_layout, Qt.AlignTop),
            (self.random_btn_h_layout, Qt.AlignCenter),
            (self.filter_tab_v_layout, Qt.AlignTop),
        ):
            layout.setAlignment(alignment)

        # Don't align main_v_layout to top; let it expand to fill available space
        self.main_v_layout.setStretchFactor(self.main_h_layout, 1)

        self.filter_stacked_widget.hide()
        self.album_view.hide()
        self.h_splitter.setStretchFactor(0, 1)
        self.h_splitter.setStretchFactor(1, 3)
        self.h_splitter.setStretchFactor(2, 1)
        self.resize(QSize(1340, 760))

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

        # Clear and refill album explorer
        self.album_explorer.fill()

        # Clear artist and genre filters
        self.artist_filter_widget.clear()
        self.genre_filter_widget.clear()

        # If a filter is visible, refill it immediately
        if self.filter_stacked_widget.isVisible():
            current_index = self.filter_stacked_widget.currentIndex()
            if current_index == 0:
                self.artist_filter_widget.fill()
            else:
                self.genre_filter_widget.fill()

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
        self.player_widget.playback_widget.advance(
            10 if QApplication.keyboardModifiers() == Qt.ControlModifier else 5
        )

    def rewind(self) -> None:
        self.player_widget.playback_widget.rewind(
            10 if QApplication.keyboardModifiers() == Qt.ControlModifier else 5
        )

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

    def show_about_dialog(self) -> None:
        meta = importlib.metadata.metadata("zic")
        keywords = meta.get_all("Keywords", [])

        release_date = None
        for keyword in keywords:
            if keyword.startswith("release-date:"):
                release_date = keyword.split(":")[-1]
                break

        version = importlib.metadata.version("zic")
        description = meta["summary"]

        about_message = f"""
        <div style="text-align:center;">
            <h2 style="margin-bottom:0;">ZIC</h2>
            <p style="color:gray; margin-top:2px;">Version {version}</p>
            <p>{description}</p>
        """

        if release_date is not None:
            about_message += f'<p style="font-size:small; color:gray;">Release date: {release_date}</p>'

        about_message += "</div>"

        QMessageBox.about(self, "About", about_message)

    def check_for_new_songs(self, rescan: bool = False) -> None:
        args = [
            "ingest",
            str(get_app_config().root_dir),
            "--db",
            str(get_app_config().db_path),
        ]
        if rescan:
            args.append("--rescan")
        self.ingest_process.start("zic", args)

    def on_ingest_process_finished(
        self, exit_code: int, exit_status: QProcess.ExitStatus
    ) -> None:
        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            QMessageBox.information(self, "Database", "Database scan finished")
            self.reload()

    def on_ingest_process_failed(self, error: QProcess.ProcessError) -> None:
        QMessageBox.warning(
            self,
            "Database",
            f"Database scan failed : {error.name}\n{self.ingest_process.errorString()}",
        )

    def compute_genres(self) -> None:
        self.compute_genres_process.start(
            "zic", ["genres", "compute", str(get_app_config().db_path)]
        )

    def on_compute_genres_finished(
        self, exit_code: int, exit_status: QProcess.ExitStatus
    ) -> None:
        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            QMessageBox.information(
                self, "Database", "Genre positions computation finished"
            )
            self.reload()

    def on_compute_genres_failed(self, error: QProcess.ProcessError) -> None:
        QMessageBox.warning(
            self,
            "Database",
            f"Genre position computation failed : {error.name}\n{self.compute_genres_process.errorString()}",
        )

    @property
    def text_edits(self) -> list[QWidget]:
        return [
            self.album_explorer.search_edt,
            self.artist_filter_widget.search_edt,
            self.genre_filter_widget.search_edt,
        ]

    def get_last_ingest_date(self) -> str:
        date = self.api.last_ingest_date()
        if date is None:
            return "Never"
        return date.strftime("%d/%m/%Y, %H:%M:%S")


class GlobalKeyFilter(QObject):
    def __init__(self, app_instance: ZicUI) -> None:
        super().__init__()
        self.app_instance: ZicUI = app_instance

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.KeyPress
            and event.key()
            in {
                Qt.Key_Space,
                Qt.Key_Left,
                Qt.Key_Right,
            }
            and not any(widget.hasFocus() for widget in self.app_instance.text_edits)
        ):
            self.app_instance.keyPressEvent(event)
            return True
        return super().eventFilter(obj, event)
