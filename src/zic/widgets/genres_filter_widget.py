from typing import Self

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QWidget

from zic.models.genre import Genre
from zic.widgets.filter_list_widget import FilterListWidget


class GenreItem(QListWidgetItem):
    def __init__(self, genre: Genre) -> None:
        super().__init__(genre.name)
        self.genre: Genre = genre

    def __lt__(self, other: Self):
        return self.genre.name < other.genre.name


class GenresFilterWidget(FilterListWidget):
    SORT_ORDER_CONFIG_KEY: str = "genres_descending_order"

    def __init__(self, app: QWidget) -> None:
        super().__init__(app, "Genres")

    def fill(self) -> None:
        for genre in self.app.api.genres():
            item = GenreItem(genre)
            item.setData(Qt.UserRole, genre.name)
            self.list_widget.addItem(item)

        self.filled = True

        super().fill()

    def on_list_selection_changed(self) -> None:
        items = super().on_list_selection_changed()
        self.app.album_explorer.set_genre_filters([item.genre for item in items])

    def select_genres(self, genres: list[Genre]) -> None:
        genre_ids = {genre.id for genre in genres}
        self.select_items(lambda item: item.genre.id in genre_ids)
