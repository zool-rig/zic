from dataclasses import dataclass, field
from typing import NamedTuple

from zic.models.artist import Artist
from zic.models.genre import Genre


class AlbumCover(NamedTuple):
    thumbnail: bytes
    dominant_color: str | None


@dataclass(slots=True)
class Album:
    id: int
    name: str
    year: int | None
    raw_date: str | None
    _artist_id: int = field(repr=False, compare=False)
    _artist_name: str = field(repr=False, compare=False)
    _artist_normalized_name: str = field(repr=False, compare=False)
    artist: Artist = field(init=False)
    is_compilation: bool
    genres: list[Genre]

    def __post_init__(self) -> None:
        self.artist = Artist(
            self._artist_id, self._artist_name, self._artist_normalized_name
        )
