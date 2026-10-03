import os

import pytest

from zic.api import AlbumEdit, SongEdit
from zic.utils.tags import TagWriteError, format_number_pair, read_tags, write_tags

# A few silent MPEG-1 Layer III frames: enough for mutagen to read and tag.
MP3_BYTES = (b"\xff\xfb\x90\x00" + b"\x00" * 413) * 40


@pytest.fixture
def library_files(api, tmp_path):
    """Creates the seeded songs' files under the library root, tagged like
    the DB. Daft Punk files have an album artist tag, Air files don't."""
    rows = api.connection.execute(
        "SELECT songs.path, songs.title, songs.artist_credit, songs.track_number, "
        "albums.name, artists.name FROM songs "
        "JOIN albums ON albums.id = songs.album_id "
        "JOIN artists ON artists.id = albums.artist_id"
    ).fetchall()
    for rel_path, title, artist, track, album, album_artist in rows:
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(MP3_BYTES)
        tags = {"title": title, "artist": artist, "album": album, "tracknumber": f"{track}/3"}
        if album_artist == "Daft Punk":
            tags["albumartist"] = album_artist
        write_tags(path, tags)
    return tmp_path


def _album(api, name):
    return next(a for a in api.albums() if a.name == name)


def _song(api, title):
    return next(
        s for a in api.albums() for s in api.get_album_songs(a) if s.title == title
    )


def _tags(root, song):
    return read_tags(root / song.path)


# --- tags ------------------------------------------------------------------

def test_format_number_pair():
    assert format_number_pair(3, 12) == "3/12"
    assert format_number_pair(3, None) == "3"
    assert format_number_pair(None, 12) is None


def test_write_tags_removes_empty_values_and_keeps_others(tmp_path):
    path = tmp_path / "a.mp3"
    path.write_bytes(MP3_BYTES)
    write_tags(path, {"title": "T", "artist": "A"})
    write_tags(path, {"artist": None})
    assert read_tags(path) == {"title": "T"}


def test_write_tags_rejects_unknown_keys(tmp_path):
    with pytest.raises(ValueError):
        write_tags(tmp_path / "a.mp3", {"comment": "x"})


# --- songs -----------------------------------------------------------------

def test_update_song_writes_tags_and_db(api, library_files):
    song = _song(api, "Sexy Boy")
    assert api.update_song(song, SongEdit("Sexy Boy (Remastered)", "Air", 7, 1))

    tags = _tags(library_files, song)
    assert tags["title"] == "Sexy Boy (Remastered)"
    assert tags["tracknumber"] == "7"  # the DB knows no track total here
    assert tags["discnumber"] == "1"

    updated = _song(api, "Sexy Boy (Remastered)")
    assert (updated.track_number, updated.disc_number) == (7, 1)
    assert updated.sort_title == "sexy boy (remastered)"


def test_update_song_records_the_rewritten_file_as_scanned(api, library_files):
    song = _song(api, "Talisman")
    api.update_song(song, SongEdit("Talisman!", "Air", 3, None))

    path = library_files / song.path
    mtime, size = api.connection.execute(
        "SELECT file_modified_at, file_size FROM songs WHERE id = ?", (song.id,)
    ).fetchone()
    assert mtime == f"{path.stat().st_mtime:.6f}"
    assert size == path.stat().st_size


def test_update_song_without_changes_leaves_the_file_alone(api, library_files):
    song = _song(api, "Talisman")
    before = (library_files / song.path).stat().st_mtime_ns
    assert not api.update_song(song, SongEdit("Talisman", "Air", 3, None))
    assert (library_files / song.path).stat().st_mtime_ns == before


def test_update_song_artist_pins_the_album_artist(api, library_files):
    # Air files have no album artist tag: the ingestor would derive the
    # album from the new song artist, so the current one gets pinned.
    song = _song(api, "Sexy Boy")
    api.update_song(song, SongEdit("Sexy Boy", "Air feat. Beck", 2, None))

    tags = _tags(library_files, song)
    assert tags["artist"] == "Air feat. Beck"
    assert tags["albumartist"] == "Air"
    assert {a.name for a in api.get_song_artists(song)} == {"Air", "Beck"}


def test_update_song_requires_a_title(api, library_files):
    with pytest.raises(ValueError):
        api.update_song(_song(api, "Talisman"), SongEdit("  ", "Air", 3, None))


def test_update_song_read_only_file_changes_nothing(api, library_files):
    song = _song(api, "Talisman")
    os.chmod(library_files / song.path, 0o444)
    with pytest.raises(TagWriteError):
        api.update_song(song, SongEdit("Other", "Air", 3, None))
    assert _song(api, "Talisman")


def test_hide_and_show_song(api, library_files):
    album = _album(api, "Moon Safari")
    song = _song(api, "Talisman")

    api.set_song_hidden(song, True)
    assert song.id not in {s.id for s in api.get_album_songs(album)}
    assert [s.id for s in api.get_hidden_album_songs(album)] == [song.id]

    api.set_song_hidden(song, False)
    assert song.id in {s.id for s in api.get_album_songs(album)}
    assert api.get_hidden_album_songs(album) == []


# --- albums ----------------------------------------------------------------

def test_update_album_writes_every_file_and_db(api, library_files):
    album = _album(api, "Moon Safari")
    album_id = api.update_album(
        album, AlbumEdit("Moon Safari (Deluxe)", "Air & Friends", 1999, ["Downtempo", "electronic"])
    )
    assert album_id == album.id

    for song in api.get_album_songs(_album(api, "Moon Safari (Deluxe)")):
        tags = _tags(library_files, song)
        assert tags["album"] == "Moon Safari (Deluxe)"
        assert tags["albumartist"] == "Air & Friends"
        assert tags["date"] == "1999"
        assert tags["genre"] == "downtempo; electronic"

    updated = _album(api, "Moon Safari (Deluxe)")
    assert updated.year == 1999
    assert updated.artist.name == "Air & Friends"
    assert {g.name for g in updated.genres} == {"downtempo", "electronic"}
    # Still used by Discovery.
    assert "french touch" in {g.name for g in api.genres()}


def test_update_album_also_tags_hidden_songs(api, library_files):
    album = _album(api, "Moon Safari")
    hidden = _song(api, "Talisman")
    api.set_song_hidden(hidden, True)

    api.update_album(album, AlbumEdit("Moon Safari", "Air", 2000, []))
    assert _tags(library_files, hidden)["date"] == "2000"


def test_update_album_removes_orphan_genres_and_artists(api, library_files):
    api.update_album(_album(api, "Discovery"), AlbumEdit("Discovery", "Daft Punk", 2001, []))
    api.update_album(_album(api, "Moon Safari"), AlbumEdit("Moon Safari", "Air", 1998, ["electronic"]))
    assert "french touch" not in {g.name for g in api.genres()}

    # Songs still credit "Daft Punk": only the unused new artist would go.
    api.update_album(_album(api, "Discovery"), AlbumEdit("Discovery", "Thomas", 2001, []))
    api.update_album(_album(api, "Discovery"), AlbumEdit("Discovery", "Daft Punk", 2001, []))
    assert "Thomas" not in {a.name for a in api.artists()}


def test_update_album_renamed_like_another_merges_into_it(api, library_files):
    talkie = _album(api, "Talkie Walkie")
    moon = _album(api, "Moon Safari")
    assert api.find_album("moon  SAFARI", "AIR", exclude=talkie) == moon
    # Same name, other artist: a different album.
    assert api.find_album("Moon Safari", "Daft Punk", exclude=talkie) is None

    album_id = api.update_album(talkie, AlbumEdit("Moon Safari", "Air", 1998, []))

    assert album_id == moon.id
    assert "Talkie Walkie" not in {a.name for a in api.albums()}
    merged = _album(api, "Moon Safari")
    assert "Cherry Blossom Girl" in {s.title for s in api.get_album_songs(merged)}
    # The target's genres are kept.
    assert {g.name for g in merged.genres} == {"electronic", "french touch"}


def test_update_album_without_changes_returns_early(api, library_files):
    album = _album(api, "Discovery")
    edit = AlbumEdit("Discovery", "Daft Punk", 2001, ["French Touch"])
    assert api.update_album(album, edit) is None
    assert "date" not in _tags(library_files, api.get_album_songs(album)[0])


def test_update_album_missing_file_changes_nothing(api, library_files):
    album = _album(api, "Discovery")
    (library_files / api.get_album_songs(album)[0].path).unlink()
    with pytest.raises(TagWriteError):
        api.update_album(album, AlbumEdit("Discovery 2", "Daft Punk", 2001, []))
    assert _album(api, "Discovery")
    assert "album" in _tags(library_files, api.get_album_songs(album)[1])
    assert _tags(library_files, api.get_album_songs(album)[1])["album"] == "Discovery"
