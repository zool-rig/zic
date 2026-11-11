"""End-to-end ingest runs on small synthetic libraries (no network)."""

import shutil
import sqlite3

import pytest

from zic.ingestor import ingest as ingest_module
from zic.ingestor.ingest import empty_album_discogs_data
from zic.utils.tags import write_tags

# Silent MPEG frames; `salt` frames more make each file's content unique.
FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


@pytest.fixture(autouse=True)
def no_discogs(monkeypatch):
    monkeypatch.setattr(
        ingest_module, "get_album_discogs_data", lambda *a: empty_album_discogs_data()
    )


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    return root


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "lib.db"


def make_song(root, rel_path, artist, album, title, salt):
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(FRAME * (40 + salt))
    write_tags(
        path, {"artist": artist, "albumartist": artist, "album": album, "title": title}
    )
    return path


def run_ingest(root, db_path, rescan=False):
    ingest_module.ingest(root, db_path, rescan, json_progress=True)


def query(db_path, sql, *params):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql, params).fetchall()


# --- same-named albums -----------------------------------------------------


def test_same_named_albums_of_different_artists_stay_apart(lib, db_path):
    make_song(lib, "a/gh/01.mp3", "Artist A", "Greatest Hits", "Song A", 1)
    make_song(lib, "b/gh/01.mp3", "Artist B", "Greatest Hits", "Song B", 2)
    run_ingest(lib, db_path)

    albums = query(
        db_path,
        "SELECT albums.name, artists.name, "
        "(SELECT count(*) FROM songs WHERE album_id = albums.id) "
        "FROM albums JOIN artists ON artists.id = albums.artist_id ORDER BY artists.name",
    )
    assert albums == [
        ("Greatest Hits", "Artist A", 1),
        ("Greatest Hits", "Artist B", 1),
    ]


def test_album_name_variants_of_one_artist_are_still_merged(lib, db_path):
    make_song(lib, "a/1.mp3", "Artist A", "Greatest Hits", "One", 1)
    make_song(lib, "a/2.mp3", "Artist A", "greatest  HITS", "Two", 2)
    run_ingest(lib, db_path)
    assert query(db_path, "SELECT count(*) FROM albums") == [(1,)]


# --- moved / removed files --------------------------------------------------


def test_moved_file_keeps_its_song_and_history(lib, db_path):
    make_song(lib, "a/old/01.mp3", "Artist A", "Album", "Song", 1)
    run_ingest(lib, db_path)
    (song_id,) = query(db_path, "SELECT id FROM songs")[0]
    query(db_path, "INSERT INTO plays (song_id) VALUES (?)", song_id)

    (lib / "a/new").mkdir()
    shutil.move(lib / "a/old/01.mp3", lib / "a/new/01.mp3")
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT id, path FROM songs") == [(song_id, "a/new/01.mp3")]
    assert query(db_path, "SELECT count(*) FROM plays WHERE song_id = ?", song_id) == [
        (1,)
    ]


def test_moved_and_retagged_file_replaces_the_old_song(lib, db_path):
    # New content: not recognized as a move, so a new song; the old one goes.
    path = make_song(lib, "x/01.mp3", "Artist A", "Album", "Song", 1)
    run_ingest(lib, db_path)
    path.unlink()
    make_song(lib, "y/01.mp3", "Artist B", "Album", "Song", 5)
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT path FROM songs") == [("y/01.mp3",)]
    assert query(
        db_path,
        "SELECT artists.name FROM albums JOIN artists ON artists.id = albums.artist_id",
    ) == [("Artist B",)]
    # No empty album nor unused artist left behind.
    assert query(db_path, "SELECT name FROM artists") == [("Artist B",)]


def test_removed_files_are_removed_with_their_empty_album(lib, db_path):
    make_song(lib, "a/01.mp3", "Artist A", "Kept", "Song 1", 1)
    gone = make_song(lib, "b/01.mp3", "Artist B", "Gone", "Song 2", 2)
    run_ingest(lib, db_path)

    gone.unlink()
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT path FROM songs") == [("a/01.mp3",)]
    assert query(db_path, "SELECT name FROM albums") == [("Kept",)]
    assert query(db_path, "SELECT name FROM artists") == [("Artist A",)]


def test_duplicate_content_is_still_skipped(lib, db_path):
    make_song(lib, "a/01.mp3", "Artist A", "Album", "Song", 1)
    shutil.copy(lib / "a/01.mp3", lib / "a/copy.mp3")
    run_ingest(lib, db_path)
    assert query(db_path, "SELECT path FROM songs") == [("a/01.mp3",)]


def test_empty_scan_keeps_the_library(lib, db_path):
    # E.g. the library's drive isn't mounted: don't wipe everything.
    path = make_song(lib, "a/01.mp3", "Artist A", "Album", "Song", 1)
    run_ingest(lib, db_path)
    path.unlink()
    run_ingest(lib, db_path)
    assert query(db_path, "SELECT path FROM songs") == [("a/01.mp3",)]


# --- user playlists --------------------------------------------------------


def playlist_songs(db_path, name):
    """The titles of a playlist, in its order."""
    return [
        title
        for (title,) in query(
            db_path,
            "SELECT songs.title FROM user_playlist_songs "
            "JOIN user_playlists ON user_playlists.id = playlist_id "
            "JOIN songs ON songs.id = song_id "
            "WHERE user_playlists.name = ? ORDER BY position",
            name,
        )
    ]


def test_playlist_folder_creates_a_playlist_in_natural_order(lib, db_path):
    make_song(lib, "_playlists/Road/10.mp3", "A", "Album", "Ten", 1)
    make_song(lib, "_playlists/Road/2.mp3", "A", "Album", "Two", 2)
    make_song(lib, "_playlists/Road/sub/30.mp3", "A", "Album", "Sub", 3)
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT name FROM user_playlists") == [("Road",)]
    assert playlist_songs(db_path, "Road") == ["Two", "Ten", "Sub"]


def test_file_directly_in_playlists_folder_is_an_ordinary_song(lib, db_path):
    make_song(lib, "_playlists/loose.mp3", "A", "Album", "Loose", 1)
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT title FROM songs") == [("Loose",)]
    assert query(db_path, "SELECT count(*) FROM user_playlists") == [(0,)]


def test_rescan_applies_what_changed_in_the_folder(lib, db_path):
    first = make_song(lib, "_playlists/Road/1.mp3", "A", "Album", "First", 1)
    make_song(lib, "_playlists/Road/2.mp3", "A", "Album", "Second", 2)
    make_song(lib, "_playlists/Road/3.mp3", "A", "Album", "Third", 3)
    run_ingest(lib, db_path)

    # One removed, one renamed, one added before the others.
    first.unlink()
    shutil.move(lib / "_playlists/Road/2.mp3", lib / "_playlists/Road/9.mp3")
    make_song(lib, "_playlists/Road/0.mp3", "A", "Album", "New", 4)
    run_ingest(lib, db_path)

    assert playlist_songs(db_path, "Road") == ["Second", "Third", "New"]


def edit_playlist(db_path, sql, *params):
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(sql, params)


def song_id_of(db_path, title):
    return query(db_path, "SELECT id FROM songs WHERE title = ?", title)[0][0]


def test_rescan_keeps_what_was_edited_in_the_app(lib, db_path):
    make_song(lib, "other/1.mp3", "A", "Album", "Elsewhere", 1)
    make_song(lib, "_playlists/Road/1.mp3", "A", "Album", "One", 2)
    make_song(lib, "_playlists/Road/2.mp3", "A", "Album", "Two", 3)
    make_song(lib, "_playlists/Road/3.mp3", "A", "Album", "Three", 4)
    run_ingest(lib, db_path)
    playlist_id = query(db_path, "SELECT id FROM user_playlists")[0][0]

    # Reversed, "Two" removed, and a song from elsewhere added first.
    for title, position in (("One", 2), ("Three", 1)):
        edit_playlist(
            db_path,
            "UPDATE user_playlist_songs SET position = ? WHERE song_id = ?",
            position,
            song_id_of(db_path, title),
        )
    edit_playlist(
        db_path,
        "DELETE FROM user_playlist_songs WHERE song_id = ?",
        song_id_of(db_path, "Two"),
    )
    edit_playlist(
        db_path,
        "INSERT INTO user_playlist_songs (playlist_id, song_id, position) "
        "VALUES (?, ?, 0)",
        playlist_id,
        song_id_of(db_path, "Elsewhere"),
    )

    run_ingest(lib, db_path)
    run_ingest(lib, db_path, rescan=True)

    assert playlist_songs(db_path, "Road") == ["Elsewhere", "Three", "One"]

    # A new file joins the end, and a deleted one still removes its song.
    make_song(lib, "_playlists/Road/4.mp3", "A", "Album", "Four", 5)
    (lib / "_playlists/Road/3.mp3").unlink()
    run_ingest(lib, db_path)

    assert playlist_songs(db_path, "Road") == ["Elsewhere", "One", "Four"]


def test_song_removed_in_the_app_comes_back_with_a_new_file(lib, db_path):
    make_song(lib, "_playlists/Road/1.mp3", "A", "Album", "One", 1)
    make_song(lib, "_playlists/Road/2.mp3", "A", "Album", "Two", 2)
    run_ingest(lib, db_path)
    edit_playlist(
        db_path,
        "DELETE FROM user_playlist_songs WHERE song_id = ?",
        song_id_of(db_path, "Two"),
    )

    # Same content, new name: the file is new to this folder.
    shutil.move(lib / "_playlists/Road/2.mp3", lib / "_playlists/Road/3.mp3")
    run_ingest(lib, db_path)
    assert playlist_songs(db_path, "Road") == ["One", "Two"]


def test_file_holding_another_song_keeps_its_place(lib, db_path):
    make_song(lib, "lib/1.mp3", "A", "Album", "Original", 1)
    (lib / "_playlists/Road").mkdir(parents=True)
    shutil.copy(lib / "lib/1.mp3", lib / "_playlists/Road/1.mp3")
    make_song(lib, "_playlists/Road/2.mp3", "A", "Album", "Two", 2)
    run_ingest(lib, db_path)

    # The copy no longer matches the original, so it's a song of its own.
    write_tags(lib / "_playlists/Road/1.mp3", {"title": "Retagged"})
    run_ingest(lib, db_path)

    assert playlist_songs(db_path, "Road") == ["Retagged", "Two"]


def test_removed_playlist_folder_removes_the_playlist(lib, db_path):
    make_song(lib, "kept/1.mp3", "A", "Album", "Kept", 1)
    make_song(lib, "_playlists/Road/1.mp3", "A", "Album", "Song", 2)
    run_ingest(lib, db_path)

    shutil.rmtree(lib / "_playlists/Road")
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT count(*) FROM user_playlists") == [(0,)]
    assert query(db_path, "SELECT count(*) FROM user_playlist_songs") == [(0,)]


def test_copy_of_a_library_song_joins_the_playlist_without_a_new_song(lib, db_path):
    # In a lowercase folder, it would sort after _playlists without ordering.
    make_song(lib, "lib/1.mp3", "A", "Album", "Song", 1)
    (lib / "_playlists/Road").mkdir(parents=True)
    shutil.copy(lib / "lib/1.mp3", lib / "_playlists/Road/1.mp3")
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT path FROM songs") == [("lib/1.mp3",)]
    assert playlist_songs(db_path, "Road") == ["Song"]


def test_copy_doesnt_read_the_file_again_at_each_scan(lib, db_path, monkeypatch):
    make_song(lib, "lib/1.mp3", "A", "Album", "Song", 1)
    (lib / "_playlists/Road").mkdir(parents=True)
    shutil.copy(lib / "lib/1.mp3", lib / "_playlists/Road/1.mp3")
    run_ingest(lib, db_path)

    read = []
    real_read_metadata = ingest_module.read_metadata
    monkeypatch.setattr(
        ingest_module,
        "read_metadata",
        lambda path: (read.append(path), real_read_metadata(path))[1],
    )
    run_ingest(lib, db_path)

    assert read == []
    assert playlist_songs(db_path, "Road") == ["Song"]


def test_deleted_original_makes_the_playlist_copy_take_over(lib, db_path):
    original = make_song(lib, "lib/1.mp3", "A", "Album", "Song", 1)
    (lib / "_playlists/Road").mkdir(parents=True)
    shutil.copy(original, lib / "_playlists/Road/1.mp3")
    run_ingest(lib, db_path)
    (song_id,) = query(db_path, "SELECT id FROM songs")[0]

    original.unlink()
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT id, path FROM songs") == [
        (song_id, "_playlists/Road/1.mp3")
    ]
    assert playlist_songs(db_path, "Road") == ["Song"]


def test_same_song_in_two_playlists_and_twice_in_one(lib, db_path):
    make_song(lib, "_playlists/One/1.mp3", "A", "Album", "Song", 1)
    (lib / "_playlists/Two").mkdir()
    shutil.copy(lib / "_playlists/One/1.mp3", lib / "_playlists/One/2.mp3")
    shutil.copy(lib / "_playlists/One/1.mp3", lib / "_playlists/Two/1.mp3")
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT count(*) FROM songs") == [(1,)]
    assert playlist_songs(db_path, "One") == ["Song"]
    assert playlist_songs(db_path, "Two") == ["Song"]


def test_song_only_in_a_playlist_gets_its_album(lib, db_path):
    make_song(lib, "_playlists/Road/1.mp3", "A", "Only Here", "Song", 1)
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT name FROM albums") == [("Only Here",)]


def test_failed_file_leaves_its_playlist_untouched(lib, db_path, monkeypatch):
    make_song(lib, "_playlists/Road/1.mp3", "A", "Album", "One", 1)
    make_song(lib, "_playlists/Road/2.mp3", "A", "Album", "Two", 2)
    make_song(lib, "_playlists/Other/1.mp3", "A", "Album", "Other", 3)
    run_ingest(lib, db_path)

    make_song(lib, "_playlists/Road/3.mp3", "A", "Album", "Three", 4)
    make_song(lib, "_playlists/Other/2.mp3", "A", "Album", "Other 2", 5)
    real_ingest_file = ingest_module.ingest_file

    def failing_ingest_file(conn, path, *args):
        if path.name == "3.mp3":
            raise OSError("Input/output error")
        return real_ingest_file(conn, path, *args)

    monkeypatch.setattr(ingest_module, "ingest_file", failing_ingest_file)
    run_ingest(lib, db_path)

    assert playlist_songs(db_path, "Road") == ["One", "Two"]
    assert playlist_songs(db_path, "Other") == ["Other", "Other 2"]

    monkeypatch.setattr(ingest_module, "ingest_file", real_ingest_file)
    run_ingest(lib, db_path)
    assert playlist_songs(db_path, "Road") == ["One", "Two", "Three"]


def test_empty_scan_keeps_the_playlists(lib, db_path):
    path = make_song(lib, "_playlists/Road/1.mp3", "A", "Album", "Song", 1)
    run_ingest(lib, db_path)
    path.unlink()
    run_ingest(lib, db_path)

    assert playlist_songs(db_path, "Road") == ["Song"]


def test_playlist_made_in_the_app_survives_scans(lib, db_path):
    make_song(lib, "a/1.mp3", "A", "Album", "Song", 1)
    run_ingest(lib, db_path)
    edit_playlist(db_path, "INSERT INTO user_playlists (name) VALUES ('Mine')")
    edit_playlist(
        db_path,
        "INSERT INTO user_playlist_songs (playlist_id, song_id, position) "
        "SELECT user_playlists.id, ?, 0 FROM user_playlists",
        song_id_of(db_path, "Song"),
    )

    run_ingest(lib, db_path)

    assert playlist_songs(db_path, "Mine") == ["Song"]


def test_renamed_playlist_stays_linked_to_its_folder(lib, db_path):
    make_song(lib, "_playlists/Road/1.mp3", "A", "Album", "One", 1)
    run_ingest(lib, db_path)
    edit_playlist(db_path, "UPDATE user_playlists SET name = 'Trip'")

    make_song(lib, "_playlists/Road/2.mp3", "A", "Album", "Two", 2)
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT name, folder FROM user_playlists") == [
        ("Trip", "Road")
    ]
    assert playlist_songs(db_path, "Trip") == ["One", "Two"]


def test_folder_named_like_another_playlist_gets_its_own(lib, db_path):
    make_song(lib, "a/1.mp3", "A", "Album", "Song", 1)
    run_ingest(lib, db_path)
    edit_playlist(db_path, "INSERT INTO user_playlists (name) VALUES ('road')")

    make_song(lib, "_playlists/Road/1.mp3", "A", "Album", "One", 2)
    run_ingest(lib, db_path)

    assert playlist_songs(db_path, "Road (2)") == ["One"]
    assert playlist_songs(db_path, "road") == []


def test_deleted_playlist_stays_deleted_until_its_folder_is_gone(lib, db_path):
    make_song(lib, "_playlists/Road/1.mp3", "A", "Album", "One", 1)
    make_song(lib, "kept/1.mp3", "A", "Album", "Kept", 2)
    run_ingest(lib, db_path)

    edit_playlist(
        db_path, "INSERT INTO user_playlist_ignored_folders (folder) VALUES ('Road')"
    )
    edit_playlist(db_path, "DELETE FROM user_playlists")
    run_ingest(lib, db_path)

    assert query(db_path, "SELECT count(*) FROM user_playlists") == [(0,)]
    # Its song stays in the library.
    assert song_id_of(db_path, "One")

    # Gone, then back: that's a new folder.
    shutil.move(lib / "_playlists/Road", lib / "_playlists_backup")
    run_ingest(lib, db_path)
    assert query(db_path, "SELECT count(*) FROM user_playlist_ignored_folders") == [
        (0,)
    ]
    shutil.move(lib / "_playlists_backup", lib / "_playlists/Road")
    run_ingest(lib, db_path)
    assert playlist_songs(db_path, "Road") == ["One"]


# --- transition cue points -------------------------------------------------


def test_ingest_analyzes_new_songs(lib, db_path):
    make_song(lib, "a/01.mp3", "Artist", "Album", "Song", 1)
    run_ingest(lib, db_path)

    ((cue_in, cue_out),) = query(db_path, "SELECT cue_in, cue_out FROM songs")
    assert cue_in is not None
    assert cue_out is not None


def test_ingest_keeps_cues_of_moved_songs_only(lib, db_path, monkeypatch):
    make_song(lib, "a/01.mp3", "Artist", "Album", "Song", 1)
    make_song(lib, "a/02.mp3", "Artist", "Album", "Other", 2)
    run_ingest(lib, db_path)

    analyzed = []
    monkeypatch.setattr(
        ingest_module,
        "analyze_file",
        lambda path: analyzed.append(path.name) or (1.0, 2.0),
    )
    shutil.move(lib / "a/01.mp3", lib / "a/01-moved.mp3")
    make_song(lib, "a/02.mp3", "Artist", "Album", "Other", 3)  # new content
    run_ingest(lib, db_path)

    assert analyzed == ["02.mp3"]
    assert query(
        db_path, "SELECT cue_in, cue_out FROM songs WHERE title = 'Other'"
    ) == [(1.0, 2.0)]
