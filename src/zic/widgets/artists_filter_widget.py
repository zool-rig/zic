from PySide6.QtWidgets import QListWidgetItem, QWidget
from PySide6.QtCore import Qt

from typing import Self

from zic.widgets.filter_list_widget import FilterListWidget
from zic.models.artist import Artist


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
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.artist not in artists:
                continue
            item.setSelected(True)
