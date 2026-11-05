import os
import sqlite3
from collections.abc import Callable
from typing import Any

RowFactoryOptions = (
    type[sqlite3.Row] | Callable[[sqlite3.Cursor, tuple[Any, ...]], object] | None
)

EXPECTED_TABLES = {
    "songs",
    "albums",
    "artists",
    "genres",
    "covers_thumbnails",
    "album_genres",
    "plays",
    "song_artists",
    "metadata",
}

# Schema changes since the first release, in order: each entry upgrades a
# database from version N (its index) to N + 1. PRAGMA user_version holds a
# database's version. schema.sql always describes the latest version, so
# fresh databases start there and never run these.
MIGRATIONS: list[list[str]] = [
    # 1: transition cue points, NULL until the song is analyzed
    [
        "ALTER TABLE songs ADD COLUMN cue_in REAL",
        "ALTER TABLE songs ADD COLUMN cue_out REAL",
    ],
    # 2: user playlists, made from the folders of the library's _playlists/
    [
        """
        CREATE TABLE user_playlists (
            id    INTEGER PRIMARY KEY,
            name  TEXT NOT NULL UNIQUE
        )
        """,
        """
        CREATE TABLE user_playlist_songs (
            playlist_id  INTEGER NOT NULL,
            song_id      INTEGER NOT NULL,
            position     INTEGER NOT NULL,

            PRIMARY KEY (playlist_id, song_id),
            FOREIGN KEY (playlist_id) REFERENCES user_playlists(id) ON DELETE CASCADE,
            FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX idx_user_playlist_songs_song_id ON user_playlist_songs(song_id)",
    ],
    # 3: files seen in each playlist's folder, so that scans keep what's edited
    # in the app. Filled by the next scan, which finds their songs already there.
    [
        """
        CREATE TABLE user_playlist_files (
            playlist_id  INTEGER NOT NULL,
            path         TEXT NOT NULL,
            song_id      INTEGER,

            PRIMARY KEY (playlist_id, path),
            FOREIGN KEY (playlist_id) REFERENCES user_playlists(id) ON DELETE CASCADE,
            FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE SET NULL
        )
        """,
        "CREATE INDEX idx_user_playlist_files_song_id ON user_playlist_files(song_id)",
    ],
    # 4: playlists made in the app or renamed: their folder isn't their name
    # anymore. Until now, all of them were named after their folder.
    [
        "ALTER TABLE user_playlists ADD COLUMN folder TEXT",
        "UPDATE user_playlists SET folder = name",
        "CREATE UNIQUE INDEX idx_user_playlists_folder ON user_playlists(folder)",
        "CREATE TABLE user_playlist_ignored_folders (folder TEXT PRIMARY KEY)",
    ],
]
SCHEMA_VERSION = len(MIGRATIONS)


class RowFactory:
    def __init__(self, conn: sqlite3.Connection, factory: RowFactoryOptions) -> None:
        self.conn = conn
        self.target_factory: RowFactoryOptions = factory
        self.current_factory = conn.row_factory

    def __enter__(self):
        self.conn.row_factory = self.target_factory

    def __exit__(self, exc_type, exc, tb):
        self.conn.row_factory = self.current_factory


def is_valid_sqlite_file(db_path: os.PathLike) -> bool:
    if not os.path.exists(db_path):
        return False

    conn = sqlite3.connect(db_path)
    try:
        return check_database(conn)
    finally:
        conn.close()


def check_database(conn: sqlite3.Connection) -> bool:
    try:
        cur = conn.execute("PRAGMA integrity_check")
        result = cur.fetchone()
        if result is None or result[0] != "ok":
            return False

        cur = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        existing_tables = {row[0] for row in cur.fetchall()}

        # Either a fresh/empty file (will be initialized on first ingest)
        # or an existing ZIC database with its core tables present.
        return not existing_tables or EXPECTED_TABLES.issubset(existing_tables)
    except sqlite3.DatabaseError:
        return False


def get_schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    # PRAGMA doesn't take bound parameters.
    conn.execute(f"PRAGMA user_version = {int(version)}")


def migrate_database(conn: sqlite3.Connection) -> None:
    """Brings an existing database up to SCHEMA_VERSION. A fresh, empty file
    is left alone: initializing it from schema.sql is the ingest's job."""
    if get_schema_version(conn) >= SCHEMA_VERSION:
        return

    conn.commit()
    # Write lock, then check again: the app and an ingest may open the
    # database at the same time, only one of them must apply the migrations.
    conn.execute("BEGIN IMMEDIATE")
    try:
        has_songs = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'songs'"
        ).fetchone()
        version = get_schema_version(conn)
        if has_songs:
            for number, statements in enumerate(
                MIGRATIONS[version:], start=version + 1
            ):
                for statement in statements:
                    conn.execute(statement)
                set_schema_version(conn, number)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


class InvalidDatabaseError(Exception):
    def __init__(self, db_path: os.PathLike) -> None:
        super().__init__(
            f"Database {db_path} is corrupted or not a valid zic database."
        )
