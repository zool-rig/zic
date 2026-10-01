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


class InvalidDatabaseError(Exception):
    def __init__(self, db_path: os.PathLike) -> None:
        super().__init__(
            f"Database {db_path} is corrupted or not a valid zic database."
        )
