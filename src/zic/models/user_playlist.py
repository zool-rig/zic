from dataclasses import dataclass


@dataclass
class UserPlaylist:
    """A playlist made by the user, in the app or as a folder of the library's
    _playlists/. Not to be confused with Playlist, the queue of songs being
    played."""

    id: int
    name: str
    song_count: int
    duration: float
    folder: str | None = None  # None if it was created in the app


class UserPlaylistNameError(ValueError):
    pass
