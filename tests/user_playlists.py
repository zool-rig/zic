"""User playlists on the API and widget side (the ingest side is in ingest_scan)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from zic.widgets.user_playlists_widget import UserPlaylistsWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def add_playlist(api, name, song_ids):
    playlist_id = api.connection.execute(
        "INSERT INTO user_playlists (name) VALUES (?)", (name,)
    ).lastrowid
    api.connection.executemany(
        "INSERT INTO user_playlist_songs (playlist_id, song_id, position) "
        "VALUES (?, ?, ?)",
        [(playlist_id, song_id, i) for i, song_id in enumerate(song_ids)],
    )
    api.connection.commit()
    return next(p for p in api.get_user_playlists() if p.id == playlist_id)


# --- API ---------------------------------------------------------------


def test_playlists_are_sorted_by_name_with_their_totals(api):
    add_playlist(api, "b", [1, 2])
    add_playlist(api, "A", [])

    assert [(p.name, p.song_count, p.duration) for p in api.get_user_playlists()] == [
        ("A", 0, 0),
        ("b", 2, 360.0),
    ]


def test_songs_keep_the_playlist_order(api):
    playlist = add_playlist(api, "Road", [3, 1, 2])
    assert [s.id for s in api.get_user_playlist_songs(playlist)] == [3, 1, 2]


def test_hidden_songs_are_left_out(api):
    api.connection.execute("UPDATE songs SET hidden = TRUE WHERE id = 1")
    playlist = add_playlist(api, "Road", [3, 1, 2])

    assert [s.id for s in api.get_user_playlist_songs(playlist)] == [3, 2]
    assert playlist.song_count == 2


def test_songs_keep_their_real_album(api):
    playlist = add_playlist(api, "Road", [3, 1])
    albums = [s.album.name for s in api.get_user_playlist_songs(playlist)]
    assert albums == ["Discovery", "Moon Safari"]


def test_queue_plays_the_playlist_then_near_genres_then_random(api):
    # Song 3's album has "french touch": near songs are those of Moon Safari.
    # Talkie Walkie has no genre, so only the random step can reach it.
    playlist = add_playlist(api, "Road", [4, 3])
    queue = api.get_user_playlist_queue(playlist)

    played = [queue.next().id for _ in range(6)]

    assert played[:2] == [4, 3]
    assert set(played[2:5]) == {1, 2, 5}
    assert played[5] == 6
    assert queue.next() is None


def test_queue_starts_from_the_given_song(api):
    playlist = add_playlist(api, "Road", [3, 1, 2])
    song = next(s for s in api.get_user_playlist_songs(playlist) if s.id == 1)

    queue = api.get_user_playlist_queue(playlist, song=song)

    assert [queue.next().id, queue.next().id] == [1, 2]


def test_shuffled_queue_plays_all_the_playlist_first(api):
    playlist = add_playlist(api, "Road", [3, 1, 2, 4])
    queue = api.get_user_playlist_queue(playlist, shuffle=True)

    assert {queue.next().id for _ in range(4)} == {1, 2, 3, 4}


def test_empty_playlist_still_plays_something(api):
    queue = api.get_user_playlist_queue(add_playlist(api, "Empty", []))
    assert queue.next() is not None


# --- widget ------------------------------------------------------------


def test_widget_explains_what_to_do_without_playlists(qapp, api):
    widget = UserPlaylistsWidget(api)
    widget.fill()

    assert not widget.empty_lbl.isHidden()
    assert widget.splitter.isHidden()


def test_widget_lists_playlists_and_shows_the_selected_songs(qapp, api):
    add_playlist(api, "Road", [3, 1])
    widget = UserPlaylistsWidget(api)
    widget.fill()

    assert widget.empty_lbl.isHidden()
    assert widget.list_widget.item(0).text() == "Road\n2 songs · 6 min"
    assert widget.details_widget.isHidden()

    widget.list_widget.setCurrentRow(0)

    assert not widget.details_widget.isHidden()
    assert list(widget.song_widgets) == [3, 1]
    # A track number means nothing in a playlist.
    assert widget.song_widgets[3].title_lbl.text() == "One More Time"


def test_widget_play_signals(qapp, api):
    playlist = add_playlist(api, "Road", [3, 1])
    widget = UserPlaylistsWidget(api)
    widget.fill()
    widget.list_widget.setCurrentRow(0)

    played, shuffled, songs = [], [], []
    widget.play_playlist_requested.connect(played.append)
    widget.shuffle_playlist_requested.connect(shuffled.append)
    widget.play_song_requested.connect(lambda p, s: songs.append((p, s.id)))

    widget.play_btn.click()
    widget.play_random_btn.click()
    widget.song_widgets[1].play_btn.click()

    assert played == [playlist]
    assert shuffled == [playlist]
    assert songs == [(playlist, 1)]


def test_widget_keeps_the_selected_playlist_while_it_exists(qapp, api):
    add_playlist(api, "A", [1])
    road = add_playlist(api, "Road", [3])
    widget = UserPlaylistsWidget(api)
    widget.fill()
    widget.list_widget.setCurrentRow(1)

    widget.fill()
    assert widget.playlist.id == road.id
    assert list(widget.song_widgets) == [3]

    api.connection.execute("DELETE FROM user_playlists WHERE id = ?", (road.id,))
    widget.fill()
    assert widget.playlist is None
    assert widget.details_widget.isHidden()
    assert widget.song_widgets == {}


def test_widget_shows_the_playing_song_on_rebuilt_rows(qapp, api):
    playlist = add_playlist(api, "Road", [3, 1])
    song = api.get_user_playlist_songs(playlist)[1]
    widget = UserPlaylistsWidget(api)

    widget.start_playing_song_display(song)
    widget.fill()
    widget.list_widget.setCurrentRow(0)

    assert not widget.song_widgets[1].sound_wave.isHidden()
    assert widget.song_widgets[3].sound_wave.isHidden()

    widget.stop_current_playing_song_display()
    assert widget.song_widgets[1].sound_wave.isHidden()
