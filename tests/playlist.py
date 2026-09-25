from dataclasses import dataclass

import pytest

from zic.models.playlist import Playlist


@dataclass(frozen=True)
class FakeSong:
    """Stand-in for Song: Playlist only ever reads `.id`."""

    id: int


def test_playlist_requires_at_least_one_fetch_func():
    with pytest.raises(ValueError):
        Playlist()


def test_playlist_consumes_first_source_before_falling_back():
    songs_a = [FakeSong(1), FakeSong(2)]
    songs_b = [FakeSong(3)]
    calls = []

    def fetch_a(exclude_ids):
        calls.append(("a", set(exclude_ids)))
        return songs_a

    def fetch_b(exclude_ids):
        calls.append(("b", set(exclude_ids)))
        return songs_b

    playlist = Playlist(fetch_a, fetch_b)

    assert playlist.next() == songs_a[0]
    assert playlist.next() == songs_a[1]
    assert playlist.next() == songs_b[0]  # source A exhausted, falls through

    assert calls[0] == ("a", set())
    assert calls[1] == ("b", {1, 2})


def test_playlist_skips_empty_sources():
    def fetch_empty(exclude_ids):
        return []

    def fetch_c(exclude_ids):
        return [FakeSong(1)]

    playlist = Playlist(fetch_empty, fetch_empty, fetch_c)
    assert playlist.next() == FakeSong(1)


def test_playlist_returns_none_when_every_source_is_empty():
    def fetch_empty(exclude_ids):
        return []

    playlist = Playlist(fetch_empty, fetch_empty)
    assert playlist.songs is None
    assert playlist.next() is None


def test_playlist_previous_and_next_navigate_history():
    songs = [FakeSong(1), FakeSong(2), FakeSong(3)]

    def fetch(exclude_ids):
        return songs

    playlist = Playlist(fetch)

    assert playlist.next() == songs[0]
    assert playlist.next() == songs[1]
    assert playlist.has_previous() is True

    assert playlist.previous() == songs[0]
    assert playlist.has_previous() is False

    # Moving forward replays the song we just backed off from, from the
    # `future` stack, without re-fetching.
    assert playlist.next() == songs[1]


def test_playlist_previous_without_history_returns_none():
    def fetch(exclude_ids):
        return [FakeSong(1)]

    playlist = Playlist(fetch)
    assert playlist.has_previous() is False
    assert playlist.previous() is None


def test_playlist_next_after_full_exhaustion_does_not_double_count():
    """Regression test for the fix guarding `self.songs is not None`
    before appending to `played`."""
    songs = [FakeSong(1)]

    def fetch(exclude_ids):
        return [s for s in songs if s.id not in exclude_ids]

    playlist = Playlist(fetch)

    assert playlist.next() == songs[0]
    assert playlist.next() is None
    assert playlist.played.count(songs[0]) == 1


def test_playlist_does_not_double_count_song_on_source_transition():
    def fetch_a(exclude_ids):
        return [s for s in [FakeSong(1)] if s.id not in exclude_ids]

    def fetch_b(exclude_ids):
        return [s for s in [FakeSong(2)] if s.id not in exclude_ids]

    playlist = Playlist(fetch_a, fetch_b)

    playlist.next()  # song 1 from source A
    playlist.next()  # source A exhausted -> falls through to song 2 from B

    assert playlist.played.count(FakeSong(1)) == 1
