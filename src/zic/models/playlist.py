from typing import Callable, Iterator

from zic.models.song import Song


class Playlist:
    def __init__(self, *fetch_funcs: Callable) -> None:
        self.fetch_funcs: list[Callable[[], list[Song]]] = list(fetch_funcs)
        if not self.fetch_funcs:
            raise ValueError("You need to provide at least one function that fetches songs")
        self.fetch_func: Callable[[], list[Song]] = self.fetch_funcs.pop(0)
        self.played_song_ids: set[int] = set()
        self.songs: Iterator | None = self.fetch_songs()
        self.current: Song | None = None
        self.played: list[Song] = []
        self.future: list[Song] = []

    def fetch_songs(self) -> Iterator | None:
        while True:
            new_songs = self.fetch_func(self.played_song_ids)
            if new_songs:
                return iter(new_songs)
            if not self.fetch_funcs:
                return None
            self.fetch_func = self.fetch_funcs.pop(0)

    def next(self) -> Song | None:
        if self.current is not None:
            self.played.append(self.current)
            self.played_song_ids.add(self.current.id)

        if self.future:
            self.current = self.future.pop()
            return self.current

        if self.songs is None:
            return

        try:
            self.current = next(self.songs)
            return self.current
        except StopIteration:
            if self.fetch_funcs:
                self.fetch_func = self.fetch_funcs.pop(0)
            self.songs = self.fetch_songs()
            return self.next()

    def has_previous(self) -> bool:
        return bool(self.played)

    def previous(self) -> Song | None:
        if not self.has_previous():
            return

        if self.current is not None:
            self.future.append(self.current)

        self.current = self.played.pop()
        return self.current
