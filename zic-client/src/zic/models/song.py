from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

from zic.models.album import Album
from zic.models.genre import Genre


@dataclass(slots=True)
class Song:
    id: int
    path: Path
    title: str
    artist_credit: str
    album: Album
    track_number: int | None
    track_total: int | None
    disc_number: int | None
    disc_total: int | None
    duration: float
    format: str
    bitrate: int | None
    sample_rate: int | None
    content_hash: str | None
    sort_title: str | None
    like_count: int
    play_count: int
    last_played_at: datetime | None
    hidden: bool
    added_to_library_at: datetime
    file_modified_at: datetime | None
    imported_at: datetime
    genre: Genre | None = None

    def __post_init__(self) -> None:
        if isinstance(self.path, str):
            self.path = Path(self.path)
        if isinstance(self.hidden, int):
            self.hidden = bool(self.hidden)
        if isinstance(self.last_played_at, str):
            self.last_played_at = datetime.fromisoformat(self.last_played_at)
        if isinstance(self.added_to_library_at, str):
            self.added_to_library_at = datetime.fromisoformat(self.added_to_library_at)
        if isinstance(self.file_modified_at, str):
            try:
                self.file_modified_at = datetime.fromisoformat(self.file_modified_at)
            except ValueError:
                self.file_modified_at = datetime.fromtimestamp(float(self.file_modified_at))
        if isinstance(self.imported_at, str):
            self.imported_at = datetime.fromisoformat(self.imported_at)

    def play(self) -> None:
        self.play_count += 1
        self.last_played_at = datetime.now()
