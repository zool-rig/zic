import importlib.metadata

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from zic.api import ZicApi
from zic.config import get_user_config
from zic.utils.qt_utils import make_toolbutton
from zic.widgets.rules import VRule, HRule
from zic.widgets.artists_filter_widget import ArtistsFilterWidget
from zic.widgets.genres_filter_widget import GenresFilterWidget
from zic.widgets.album_explorer import AlbumExplorer
from zic.widgets.player_widget import PlayerWidget


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
        self.set_style_sheet()

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
        self.reload_btn = make_toolbutton(
            "icons/refresh-arrow.png", tooltip="Reload"
        )
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
        self.album_explorer = AlbumExplorer(self)
        self.album_view = None  # TODO
        self.player_widget = PlayerWidget(self)

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

    def set_style_sheet(self) -> None:
        pass

    def closeEvent(self, _: QEvent) -> None:
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
