"""User playlists on the API and widget side (the ingest side is in ingest_scan)."""

import io
import os

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from zic.utils.covers import make_cover_mosaic
from zic.widgets.add_to_playlist_menu import (
    build_add_to_playlist_menu,
    show_add_to_playlist_menu,
)
from zic.widgets.album_view import AlbumView
from zic.widgets.cover_thumbnail import DEFAULT_COVER
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


def thumbnail(color):
    buffer = io.BytesIO()
    Image.new("RGB", (100, 100), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def add_covers(api, colors_by_album):
    for album_id, color in colors_by_album.items():
        api.connection.execute(
            "INSERT INTO covers_thumbnails (album_id, thumbnail, mime_type) "
            "VALUES (?, ?, 'image/jpeg')",
            (album_id, thumbnail(color)),
        )


def is_close(pixel, color, tolerance=25):
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, color, strict=True))


RED, GREEN, BLUE, WHITE = (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)
# The middle of each tile.
TILES = [(50, 50), (150, 50), (50, 150), (150, 150)]


def tiles_of(mosaic):
    image = Image.open(io.BytesIO(mosaic))
    assert image.size == (200, 200)
    return [image.getpixel(tile) for tile in TILES]


@pytest.mark.parametrize(
    ("colors", "expected"),
    [
        ([RED], [RED, RED, RED, RED]),
        ([RED, GREEN], [RED, GREEN, GREEN, RED]),
        ([RED, GREEN, BLUE], [RED, GREEN, BLUE, RED]),
        ([RED, GREEN, BLUE, WHITE], [RED, GREEN, BLUE, WHITE]),
    ],
)
def test_mosaic_fills_its_four_tiles(colors, expected):
    tiles = tiles_of(make_cover_mosaic([thumbnail(c) for c in colors]))
    assert all(is_close(*pair) for pair in zip(tiles, expected, strict=True))


def test_mosaic_ignores_unreadable_covers():
    assert make_cover_mosaic([]) is None
    assert make_cover_mosaic([b"not an image"]) is None
    assert make_cover_mosaic([b"not an image", thumbnail(RED)]) is not None


def test_playlist_cover_uses_its_albums_and_stays_the_same(api):
    # Song 6's album (Talkie Walkie, id 3) isn't in the playlist.
    add_covers(api, {1: RED, 2: GREEN, 3: BLUE})
    playlist = add_playlist(api, "Road", [1, 2, 3])

    cover = api.get_user_playlist_cover(playlist)

    assert not any(is_close(tile, BLUE) for tile in tiles_of(cover))
    assert api.get_user_playlist_cover(playlist) == cover


def test_playlist_without_covers_has_no_image(api):
    assert api.get_user_playlist_cover(add_playlist(api, "Road", [1])) is None


def song_ids(api, playlist):
    return [s.id for s in api.get_user_playlist_songs(playlist)]


def song_of(api, song_id):
    return next(
        s for a in api.albums() for s in api.get_album_songs(a) if s.id == song_id
    )


def test_add_song_goes_last_and_only_once(api):
    playlist = add_playlist(api, "Road", [3, 1])

    api.add_song_to_user_playlist(playlist, song_of(api, 2))
    api.add_song_to_user_playlist(playlist, song_of(api, 3))

    assert song_ids(api, playlist) == [3, 1, 2]


def test_add_song_to_an_empty_playlist(api):
    playlist = add_playlist(api, "Empty", [])
    api.add_song_to_user_playlist(playlist, song_of(api, 2))
    assert song_ids(api, playlist) == [2]


def test_remove_song_leaves_the_library_alone(api):
    playlist = add_playlist(api, "Road", [3, 1, 2])

    api.remove_song_from_user_playlist(playlist, song_of(api, 1))

    assert song_ids(api, playlist) == [3, 2]
    assert song_of(api, 1).id == 1


def test_move_song_and_stop_at_the_ends(api):
    playlist = add_playlist(api, "Road", [3, 1, 2])

    api.move_song_in_user_playlist(playlist, song_of(api, 2), -1)
    assert song_ids(api, playlist) == [3, 2, 1]

    api.move_song_in_user_playlist(playlist, song_of(api, 3), 1)
    assert song_ids(api, playlist) == [2, 3, 1]

    api.move_song_in_user_playlist(playlist, song_of(api, 2), -1)
    api.move_song_in_user_playlist(playlist, song_of(api, 1), 1)
    assert song_ids(api, playlist) == [2, 3, 1]


def test_move_song_skips_over_hidden_songs(api):
    playlist = add_playlist(api, "Road", [3, 1, 2])
    third = song_of(api, 2)
    api.connection.execute("UPDATE songs SET hidden = TRUE WHERE id = 1")

    api.move_song_in_user_playlist(playlist, third, -1)

    assert song_ids(api, playlist) == [2, 3]


def test_playlists_of_a_song(api):
    road = add_playlist(api, "Road", [1])
    add_playlist(api, "Other", [2])
    assert api.get_user_playlist_ids_of_song(song_of(api, 1)) == {road.id}


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


def test_widget_close_hides_the_songs_and_allows_reopening(qapp, api):
    add_playlist(api, "Road", [3, 1])
    widget = UserPlaylistsWidget(api)
    widget.fill()
    widget.list_widget.setCurrentRow(0)

    widget.close_btn.click()

    assert widget.details_widget.isHidden()
    assert widget.playlist is None
    assert widget.song_widgets == {}

    widget.list_widget.setCurrentRow(0)

    assert not widget.details_widget.isHidden()
    assert list(widget.song_widgets) == [3, 1]


def test_widget_shows_the_playlist_image(qapp, api):
    add_covers(api, {1: RED})
    add_playlist(api, "Covered", [1])
    add_playlist(api, "Plain", [3])
    widget = UserPlaylistsWidget(api)
    widget.fill()

    assert not widget.list_widget.item(0).icon().isNull()
    assert not widget.list_widget.item(1).icon().isNull()

    widget.list_widget.setCurrentRow(0)
    assert widget.cover_thumbnail.bytes != DEFAULT_COVER

    widget.list_widget.setCurrentRow(1)
    assert widget.cover_thumbnail.bytes == DEFAULT_COVER


def open_playlist(api, name, ids):
    add_playlist(api, name, ids)
    widget = UserPlaylistsWidget(api)
    widget.fill()
    widget.list_widget.setCurrentRow(0)
    return widget


def displayed_ids(widget):
    layout = widget.songs_v_layout
    return [layout.itemAt(i).widget().song.id for i in range(layout.count())]


def test_widget_moves_songs_and_updates_its_buttons(qapp, api):
    widget = open_playlist(api, "Road", [3, 1, 2])

    assert not widget.song_widgets[3].move_up_btn.isEnabled()
    assert not widget.song_widgets[2].move_down_btn.isEnabled()

    widget.song_widgets[1].move_up_btn.click()

    assert displayed_ids(widget) == [1, 3, 2]
    assert song_ids(api, widget.playlist) == [1, 3, 2]
    assert not widget.song_widgets[1].move_up_btn.isEnabled()
    assert widget.song_widgets[3].move_up_btn.isEnabled()

    widget.song_widgets[3].move_down_btn.click()

    assert displayed_ids(widget) == [1, 2, 3]
    assert not widget.song_widgets[3].move_down_btn.isEnabled()


def test_widget_removes_a_song_and_updates_the_totals(qapp, api):
    widget = open_playlist(api, "Road", [3, 1])

    widget.song_widgets[3].remove_btn.click()

    assert displayed_ids(widget) == [1]
    assert song_ids(api, widget.playlist) == [1]
    assert widget.list_widget.item(0).text() == "Road\n1 song · 3 min"
    assert widget.songs_info_lbl.text() == "1 song · 3 min"
    assert not widget.song_widgets[1].move_up_btn.isEnabled()
    assert not widget.song_widgets[1].move_down_btn.isEnabled()


def test_widget_removes_the_last_song_without_closing(qapp, api):
    widget = open_playlist(api, "Road", [3])

    widget.song_widgets[3].remove_btn.click()

    assert displayed_ids(widget) == []
    assert not widget.details_widget.isHidden()
    assert widget.songs_info_lbl.text() == "0 songs · 0 min"


def test_add_menu_lists_playlists_and_disables_those_with_the_song(qapp, api):
    road = add_playlist(api, "Road", [1])
    other = add_playlist(api, "Other", [2])

    menu = build_add_to_playlist_menu(api, song_of(api, 1))

    actions = {a.text(): a for a in menu.actions()}
    assert set(actions) == {"Road", "Other"}
    assert not actions["Road"].isEnabled()
    assert actions["Other"].isEnabled()
    assert actions["Other"].data() == other
    assert road != other


def test_add_menu_says_when_there_is_no_playlist(qapp, api):
    menu = build_add_to_playlist_menu(api, song_of(api, 1))

    (action,) = menu.actions()
    assert not action.isEnabled()
    assert "_playlists" in action.text()


def choose_first_action(monkeypatch):
    # The real menu would wait for a click.
    monkeypatch.setattr(
        "zic.widgets.add_to_playlist_menu.choose_action", lambda m: m.actions()[0]
    )


def test_add_menu_adds_the_chosen_song(qapp, api, monkeypatch):
    other = add_playlist(api, "Other", [2])
    choose_first_action(monkeypatch)

    target = show_add_to_playlist_menu(api, song_of(api, 1), None)

    assert target == other
    assert song_ids(api, other) == [2, 1]


def test_add_menu_closed_without_choosing_adds_nothing(qapp, api, monkeypatch):
    other = add_playlist(api, "Other", [2])
    monkeypatch.setattr(
        "zic.widgets.add_to_playlist_menu.choose_action", lambda m: None
    )

    assert show_add_to_playlist_menu(api, song_of(api, 1), None) is None
    assert song_ids(api, other) == [2]


def test_album_rows_can_add_to_a_playlist(qapp, api, monkeypatch):
    other = add_playlist(api, "Other", [])
    choose_first_action(monkeypatch)
    view = AlbumView(api)
    view.set_album(next(a for a in api.albums() if a.name == "Discovery"), None)

    view.widget_song_map[3].add_to_playlist_btn.click()

    assert song_ids(api, other) == [3]


def test_playlist_rows_refresh_the_playlist_they_add_to(qapp, api, monkeypatch):
    add_playlist(api, "A other", [1])
    add_playlist(api, "Road", [3])
    choose_first_action(monkeypatch)
    widget = UserPlaylistsWidget(api)
    widget.fill()
    widget.list_widget.setCurrentRow(1)

    widget.song_widgets[3].add_to_playlist_btn.click()

    assert widget.list_widget.item(0).text() == "A other\n2 songs · 6 min"
