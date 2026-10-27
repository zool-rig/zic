from types import SimpleNamespace

from zic.widgets.player_widget import is_album_continuation


def make_song(album_id, track_number, disc_number=None):
    """Stand-in for Song: is_album_continuation only reads these fields."""
    return SimpleNamespace(
        album=SimpleNamespace(id=album_id),
        track_number=track_number,
        disc_number=disc_number,
    )


def test_next_track_of_the_album_is_a_continuation():
    assert is_album_continuation(make_song(1, 3), make_song(1, 4))
    assert is_album_continuation(make_song(1, 3, 1), make_song(1, 4, 1))


def test_first_track_of_the_next_disc_is_a_continuation():
    assert is_album_continuation(make_song(1, 12, 1), make_song(1, 1, 2))
    assert not is_album_continuation(make_song(1, 12, 1), make_song(1, 2, 2))


def test_other_album_or_skipped_track_is_not_a_continuation():
    assert not is_album_continuation(make_song(1, 3), make_song(2, 4))
    assert not is_album_continuation(make_song(1, 3), make_song(1, 5))
    assert not is_album_continuation(make_song(1, 4), make_song(1, 3))


def test_unknown_track_numbers_are_not_a_continuation():
    assert not is_album_continuation(make_song(1, None), make_song(1, 1))
    assert not is_album_continuation(make_song(1, 1), make_song(1, None))
