from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from zic.utils.qt_utils import make_toolbutton, set_label_font_size
from zic.resources import get_resource
from zic.config import get_user_config


class FilterListWidget(QWidget):
    SORT_ORDER_CONFIG_KEY: str = NotImplemented

    def __init__(self, app: QWidget, title: str) -> None:
        super().__init__()
        self.app: QWidget = app
        self.title: str = title
        self.filled: bool = False
        self.sort_down_icon: QIcon = QIcon(get_resource("icons/sort.png"))
        self.sort_up_icon: QIcon = QIcon(get_resource("icons/sort-up.png"))

        # Layouts
        self.main_v_layout = None
        self.top_h_layout = None

        # Widgets
        self.title_lbl = None
        self.search_edt = None
        self.sort_btn = None
        self.list_widget = None

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
        self.title_lbl = QLabel(self.title)
        self.search_edt = QLineEdit()
        self.sort_btn = make_toolbutton(
            "icons/sort.png", tooltip="Sort Order", checkable=True
        )
        self.list_widget = QListWidget()

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.title_lbl)
        self.main_v_layout.addLayout(self.top_h_layout)
        self.top_h_layout.addWidget(self.search_edt)
        self.top_h_layout.addWidget(self.sort_btn)
        self.main_v_layout.addWidget(self.list_widget)

    def set_connections(self) -> None:
        self.search_edt.editingFinished.connect(self.filter)
        self.sort_btn.toggled.connect(self.set_descending_order)
        self.list_widget.itemSelectionChanged.connect(self.on_list_selection_changed)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)

    def set_default(self) -> None:
        self.main_v_layout.setAlignment(Qt.AlignTop)
        self.search_edt.setClearButtonEnabled(True)
        clear_button = self.search_edt.findChildren(QAction)
        if clear_button:
            clear_button[0].triggered.connect(lambda: (self.search_edt.clear(), self.filter(), self.list_widget.clearSelection()))
        self.search_edt.setPlaceholderText("🔍 Search...")
        self.list_widget.setSortingEnabled(True)
        self.set_descending_order(
            getattr(get_user_config(), self.SORT_ORDER_CONFIG_KEY)
        )
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        set_label_font_size(self.title_lbl, 12)
        self.search_edt.setCompleter(QCompleter(self.list_widget.model(), caseSensitivity=Qt.CaseInsensitive))

    def fill(self) -> None:
        self.title_lbl.setText(f"{self.list_widget.count()} - {self.title}")

    def showEvent(self, _: QEvent) -> None:
        if not self.filled:
            self.fill()

    def filter(self) -> None:
        pattern = self.search_edt.text().strip().lower()
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            item.setHidden(False if not pattern else pattern not in item.text().lower())

    def set_descending_order(self, state: bool) -> None:
        if state:
            self.list_widget.sortItems(Qt.DescendingOrder)
            self.sort_btn.setIcon(self.sort_up_icon)
        else:
            self.list_widget.sortItems(Qt.AscendingOrder)
            self.sort_btn.setIcon(self.sort_down_icon)
        setattr(get_user_config(), self.SORT_ORDER_CONFIG_KEY, state)

    def clear(self) -> None:
        self.filled = False
        self.list_widget.clear()

    def on_list_selection_changed(self) -> None:
        return self.list_widget.selectedItems()

    def show_context_menu(self) -> None:
        menu = QMenu(self)

        menu.addAction("Clear selection").triggered.connect(
            self.list_widget.clearSelection
        )

        menu.exec(QCursor.pos())
