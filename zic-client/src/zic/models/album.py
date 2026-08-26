from pydantic import BaseModel

from zic.models.artist import Artist
from zic.models.genre import Genre


class Album(BaseModel):
    id: int
    name: str
    year: int
    row_date: str
    artist: Artist
    is_compilation: bool
    genres: list[Genre]
