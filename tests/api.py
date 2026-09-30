import pytest

from zic.api import AlbumSongOrder


def _album(api, name):
    return next(a for a in api.albums() if a.name == name)


def _first_song(api, album_name):
    return api.get_album_songs(_album(api, album_name))[0]


# --- caching -----------------------------------------------------------

def test_albums_are_cached_until_invalidated(api):
    first = api.albums()
    second = api.albums()
    assert first is second

    api.invalidate_albums_cache()
    third = api.albums()
    assert third is not first
    assert third == first


def test_albums_expose_their_genres(api):
    album = _album(api, "Moon Safari")
    assert {g.name for g in album.genres} == {"electronic", "french touch"}


def test_talkie_walkie_has_no_genres(api):
    album = _album(api, "Talkie Walkie")
    assert album.genres == []


def test_songs_album_exposes_all_album_genres(api):
    album = _album(api, "Moon Safari")
    for song in api.get_album_songs(album):
        assert {g.name for g in song.album.genres} == {"electronic", "french touch"}


# --- get_album_songs ordering -------------------------------------------

def test_get_album_songs_track_num_order(api):
    songs = api.get_album_songs(_album(api, "Moon Safari"))
    assert [s.track_number for s in songs] == [1, 2, 3]


def test_get_album_songs_song_id_order_wraps_around(api):
    album = _album(api, "Moon Safari")
    reference_song = next(s for s in api.get_album_songs(album) if s.track_number == 3)

    ordered = api.get_album_songs(album, order_mode=AlbumSongOrder.SONG_ID, song=reference_song)

    assert [s.track_number for s in ordered] == [3, 1, 2]


def test_get_album_songs_song_id_order_requires_a_song(api):
    album = _album(api, "Moon Safari")
    with pytest.raises(ValueError):
        api.get_album_songs(album, order_mode=AlbumSongOrder.SONG_ID)


# --- discography / near genres -------------------------------------------

def test_get_rest_discography_from_album_returns_other_albums_by_same_artist(api):
    moon_safari = _album(api, "Moon Safari")
    rest = api.get_rest_discography_from_album(moon_safari)

    assert {s.album.name for s in rest} == {"Talkie Walkie"}


def test_get_rest_discography_respects_exclude_ids(api):
    moon_safari = _album(api, "Moon Safari")
    talkie_walkie_song = _first_song(api, "Talkie Walkie")

    rest = api.get_rest_discography_from_album(moon_safari, exclude_ids={talkie_walkie_song.id})
    assert rest == []


def test_get_near_genres_orders_by_distance(api):
    genres = {g.name: g for g in api.genres()}
    near = api.get_near_genres(genres["electronic"], max_genres=2)
    assert [g.name for g in near] == ["french touch", "rock"]


def test_get_near_songs_from_album_empty_when_no_genres(api):
    assert api.get_near_songs_from_album(_album(api, "Talkie Walkie")) == []


def test_get_near_songs_from_album_matches_on_album_genres(api):
    # Discovery is only "french touch": Moon Safari shares that genre at the
    # album level, so its songs must be found too.
    songs = api.get_near_songs_from_album(_album(api, "Discovery"))
    assert {s.album.name for s in songs} == {"Moon Safari", "Discovery"}


def test_get_near_songs_from_album_respects_exclude_ids(api):
    album = _album(api, "Moon Safari")
    all_near = api.get_near_songs_from_album(album)
    some_id = all_near[0].id

    filtered = api.get_near_songs_from_album(album, exclude_ids={some_id})
    assert some_id not in {s.id for s in filtered}


# --- playlists -----------------------------------------------------------

def test_get_album_playlist_starts_with_the_albums_own_songs(api):
    album = _album(api, "Moon Safari")
    playlist = api.get_album_playlist(album)

    played = [playlist.next() for _ in range(3)]

    assert [s.track_number for s in played] == [1, 2, 3]
    assert all(s.album.id == album.id for s in played)


# --- plays / likes ---------------------------------------------------------

def test_record_song_play_increments_play_count(api):
    song = _first_song(api, "Discovery")
    assert song.play_count == 0

    play_id = api.record_song_play(song)

    assert song.play_count == 1
    assert song.last_played_at is not None
    assert isinstance(play_id, int)


def test_mark_play_skipped_sets_completed_false(api):
    song = _first_song(api, "Discovery")
    play_id = api.record_song_play(song)

    api.mark_play_skipped(play_id)

    row = api.connection.execute("SELECT completed FROM plays WHERE id = ?", (play_id,)).fetchone()
    assert row[0] == 0


def test_sync_song_persists_like_and_play_counts(api):
    song = _first_song(api, "Discovery")
    song.like_count += 3
    api.record_song_play(song)

    api.sync_song(song)

    row = api.connection.execute(
        "SELECT like_count, play_count, last_played_at FROM songs WHERE id = ?", (song.id,)
    ).fetchone()
    assert row[0] == 3
    assert row[1] == 1
    assert row[2] is not None


def test_get_song_artists_returns_ordered_artists(api):
    song = _first_song(api, "Moon Safari")
    assert [a.name for a in api.get_song_artists(song)] == ["Air"]


# --- metadata --------------------------------------------------------------

def test_last_ingest_date_none_when_never_ingested(api):
    assert api.last_ingest_date() is None


def test_last_ingest_date_parses_stored_metadata(api):
    api.connection.execute(
        "INSERT INTO metadata (key, value) VALUES ('last_ingest', '2024-01-02T03:04:05+00:00')"
    )
    api.connection.commit()

    result = api.last_ingest_date()
    assert (result.year, result.month, result.day) == (2024, 1, 2)


# --- paths -------------------------------------------------------------

def test_get_song_path_joins_root_dir_and_relative_path(api, tmp_path):
    song = _first_song(api, "Moon Safari")
    assert api.get_song_path(song) == str(tmp_path / song.path)
