from dataclasses import dataclass


@dataclass
class UserPlaylist:
    """A playlist made by the user, as a folder of the library's _playlists/.
    Not to be confused with Playlist, the queue of songs being played."""

    id: int
    name: str
    song_count: int
    duration: float
