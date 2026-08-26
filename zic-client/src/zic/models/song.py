from pathlib import Path
from pydantic import BaseModel
from datetime import datetime

from zic.models.album import Album
from zic.models.genre import Genre


class Song(BaseModel):
    id: int
    path: Path
    title: str
    artist_credits: str
    album: Album
    track_number: int | None
    track_total: int | None
    disc_number: int | None
    dict_total: int | None
    duration: float
    format: str
    bitrate: int | None
    sample_rate: int | None
    content_hash: str | None
    sort_title: str | None
    like_count: int
    play_count: int
    last_played_at: datetime
    hidden: bool
    added_to_library_at: datetime
    file_modified_at: datetime
    imported_at: datetime
    genre: Genre | None
