from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from zic.api import SearchResults, ZicApi
from zic.models.album import Album
from zic.models.artist import Artist
from zic.models.genre import Genre
from zic.models.song import Song

SEARCH_DEBOUNCE_MS = 150
SEARCH_MIN_CHARS = 2
POPUP_MIN_WIDTH = 420
POPUP_MAX_HEIGHT = 480
POPUP_WINDOW_MARGIN = 8


def format_result(item: Artist | Album | Genre | Song) -> str:
    match item:
        case Album():
            year = f" ({item.year})" if item.year else ""
            return f"{item.name}{year} — {item.artist.name}"
        case Song():
            return f"{item.title} — {item.artist_credit} · {item.album.name}"
        case _:
            return item.name


class SearchPopup(QFrame):
    """Grouped live search results (artists, albums, genres, songs) shown
    under a line edit while typing. The line edit keeps the focus and its
    own behavior: Enter with no highlighted result is left to it."""

    result_selected = Signal(object)  # Artist | Album | Genre | Song

    def __init__(self, api: ZicApi, line_edit: QLineEdit) -> None:
        super().__init__()
        self.api: ZicApi = api
        self.line_edit: QLineEdit = line_edit

        # Layouts
        self.main_v_layout = None

        # Widgets
        self.list_widget = None
        self.debounce_timer = None

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
        self.list_widget = QListWidget()
        self.debounce_timer = QTimer(self)

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.list_widget)

    def set_connections(self) -> None:
        self.line_edit.installEventFilter(self)
        self.line_edit.textChanged.connect(self.debounce_timer.start)
        self.debounce_timer.timeout.connect(self.update_results)
        self.list_widget.itemClicked.connect(self.activate_item)

    def set_default(self) -> None:
        self.setObjectName("SearchPopup")
        self.list_widget.setObjectName("SearchPopupList")
        self.main_v_layout.setContentsMargins(4, 4, 4, 4)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(SEARCH_DEBOUNCE_MS)
        # Clicking a result must not steal the focus from the line edit,
        # otherwise it would finish its editing (and filter the explorer).
        for widget in (self, self.list_widget, self.list_widget.verticalScrollBar()):
            widget.setFocusPolicy(Qt.NoFocus)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.hide()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is not self.line_edit:
            return super().eventFilter(obj, event)

        if event.type() == QEvent.FocusIn:
            # Build the index now rather than on the first keystroke.
            QTimer.singleShot(0, self.api.search_index)
        elif event.type() == QEvent.FocusOut:
            self.dismiss()
        elif event.type() == QEvent.KeyPress and self.isVisible():
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                self.move_selection(1 if key == Qt.Key_Down else -1)
                return True
            if key == Qt.Key_Escape:
                self.dismiss()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                item = self.list_widget.currentItem()
                if item is not None and item.isSelected():
                    self.activate_item(item)
                    return True
                # No highlighted result: let the line edit filter as usual.
                self.dismiss()
        elif event.type() == QEvent.KeyPress and event.key() in (
            Qt.Key_Return,
            Qt.Key_Enter,
        ):
            # A search still pending would pop up over the filtered explorer.
            self.debounce_timer.stop()
        return super().eventFilter(obj, event)

    def dismiss(self) -> None:
        self.debounce_timer.stop()
        self.hide()

    def update_results(self) -> None:
        text = self.line_edit.text().strip()
        if len(text) < SEARCH_MIN_CHARS or not self.line_edit.hasFocus():
            self.hide()
            return

        results = self.api.search(text)
        if results.is_empty():
            self.hide()
            return

        self.fill(results)
        self.show_below_line_edit()

    def fill(self, results: SearchResults) -> None:
        self.list_widget.clear()
        for title, items in (
            ("Artists", results.artists),
            ("Albums", results.albums),
            ("Genres", results.genres),
            ("Songs", results.songs),
        ):
            if not items:
                continue
            header = QListWidgetItem(title.upper())
            header.setFlags(Qt.NoItemFlags)
            self.list_widget.addItem(header)
            for item in items:
                list_item = QListWidgetItem(format_result(item))
                list_item.setData(Qt.UserRole, item)
                list_item.setToolTip(list_item.text())
                self.list_widget.addItem(list_item)

    def show_below_line_edit(self) -> None:
        # A child of the window rather than a separate popup window: no
        # focus or window manager quirks, it just floats over the content.
        window = self.line_edit.window()
        if self.parent() is not window:
            self.setParent(window)

        pos = self.line_edit.mapTo(window, QPoint(0, self.line_edit.height() + 2))
        width = min(
            max(self.line_edit.width(), POPUP_MIN_WIDTH),
            window.width() - pos.x() - POPUP_WINDOW_MARGIN,
        )
        margins = self.main_v_layout.contentsMargins()
        content_height = sum(
            self.list_widget.sizeHintForRow(row)
            for row in range(self.list_widget.count())
        )
        height = min(
            content_height
            + 2 * self.list_widget.frameWidth()
            + margins.top()
            + margins.bottom(),
            POPUP_MAX_HEIGHT,
            window.height() - pos.y() - POPUP_WINDOW_MARGIN,
        )
        self.setGeometry(pos.x(), pos.y(), width, height)
        self.show()
        self.raise_()

    def move_selection(self, step: int) -> None:
        """Moves the highlighted result, skipping group headers."""
        current = self.list_widget.currentItem()
        if current is not None and current.isSelected():
            row = self.list_widget.currentRow()
        else:
            row = -1 if step > 0 else self.list_widget.count()

        row += step
        while 0 <= row < self.list_widget.count():
            item = self.list_widget.item(row)
            if item.flags() & Qt.ItemIsSelectable:
                self.list_widget.setCurrentItem(item)
                self.list_widget.scrollToItem(item)
                return
            row += step

    def activate_item(self, item: QListWidgetItem) -> None:
        result = item.data(Qt.UserRole)
        if result is None:
            return
        self.dismiss()
        self.result_selected.emit(result)
