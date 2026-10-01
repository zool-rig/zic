from typing import Self

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QWidget

from zic.models.artist import Artist
from zic.utils.qt_utils import SignalsOFF
from zic.widgets.filter_list_widget import FilterListWidget


class ArtistItem(QListWidgetItem):
    def __init__(self, artist: Artist) -> None:
        super().__init__(artist.name)
        self.artist: Artist = artist

    def __lt__(self, other: Self):
        return self.artist.normalized_name < other.artist.normalized_name


class ArtistsFilterWidget(FilterListWidget):
    SORT_ORDER_CONFIG_KEY: str = "artists_descending_order"

    def __init__(self, app: QWidget) -> None:
        super().__init__(app, "Artists")

    def fill(self) -> None:
        for artist in self.app.api.artists():
            item = ArtistItem(artist)
            item.setData(Qt.UserRole, artist.name)
            self.list_widget.addItem(item)

        self.filled = True

        super().fill()

    def on_list_selection_changed(self) -> None:
        items = super().on_list_selection_changed()
        self.app.album_explorer.set_artist_filters([item.artist for item in items])

    def select_artists(self, artists: list[Artist]) -> None:
        # The list is filled lazily on first show: it may still be empty here.
        if not self.filled:
            self.fill()
        # A pending search could hide the artists we're about to select.
        if self.search_edt.text():
            self.search_edt.clear()
            self.filter()

        artist_ids = {artist.id for artist in artists}
        first_item = None
        # Replace the current selection, and apply the filter only once.
        with SignalsOFF(self.list_widget):
            self.list_widget.clearSelection()
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item.artist.id not in artist_ids:
                    continue
                item.setSelected(True)
                first_item = first_item or item
        self.on_list_selection_changed()

        if first_item is not None:
            self.list_widget.scrollToItem(first_item)
