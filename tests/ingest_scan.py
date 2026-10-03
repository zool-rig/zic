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
