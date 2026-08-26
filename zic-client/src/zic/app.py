import importlib.metadata

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from zic.utils.qt_utils import make_toolbutton


class ZicUI(QDialog):
    def __init__(self) -> None:
        super().__init__()

        # Layouts
        self.main_v_layout = None
        self.main_h_layout = None
        self.side_bar_v_layout = None
        self.random_btn_h_layout = None
        self.filter_tab_v_layout = None

        # Widgets
        self.play_random_btn = None
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
        self.filter_tab_v_layout = QVBoxLayout()

    def init_widgets(self) -> None:
        self.play_random_btn = make_toolbutton("icons/shuffle.png", tooltip="Play random")
        self.filter_tab_frame = QFrame()
        self.toggle_artists_btn = make_toolbutton("icons/artist.png", tooltip="Toggle artists view", checkable=True)
        self.toggle_artists_btn = make_toolbutton("icons/tag.png", tooltip="Toggle genres view", checkable=True)

    def set_layout(self) -> None:
        pass

    def set_connections(self) -> None:
        pass

    def set_default(self) -> None:
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle(f"ZIC - {importlib.metadata.version("zic-client")}")

    def set_style_sheet(self) -> None:
        pass
