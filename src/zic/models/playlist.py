from collections.abc import Callable, Iterator

from zic.models.song import Song


class Playlist:
    def __init__(self, *fetch_funcs: Callable) -> None:
        self.fetch_funcs: list[Callable[[set[int]], list[Song]]] = list(fetch_funcs)
        if not self.fetch_funcs:
            raise ValueError(
                "You need to provide at least one function that fetches songs"
            )
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
        if self.current is not None and self.songs is not None:
            self.played.append(self.current)
            self.played_song_ids.add(self.current.id)

        self.current = self._advance()
        return self.current

    def _advance(self) -> Song | None:
        """Returns the next song to play, transparently switching to the
        next fetch source(s) as needed. Recording history is the caller's
        (next()'s) responsibility, done exactly once per public call —
        this loop must never trigger a second append when it hops between
        sources."""
        if self.future:
            return self.future.pop()

        while self.songs is not None:
            try:
                return next(self.songs)
            except StopIteration:
                if self.fetch_funcs:
                    self.fetch_func = self.fetch_funcs.pop(0)
                self.songs = self.fetch_songs()
        return None

    def has_previous(self) -> bool:
        return bool(self.played)

    def previous(self) -> Song | None:
        if not self.has_previous():
            return

        if self.current is not None:
            self.future.append(self.current)

        self.current = self.played.pop()
        return self.current
