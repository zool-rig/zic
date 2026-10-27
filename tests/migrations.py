import re
import sqlite3
from pathlib import Path

import pytest

from zic.ingestor.ingest import SCHEMA_PATH
from zic.utils.db_utils import SCHEMA_VERSION, get_schema_version, migrate_database

# schema.sql as first released, before any migration
SCHEMA_V0_PATH = Path(__file__).parent / "data" / "schema_v0.sql"


def columns(conn: sqlite3.Connection) -> dict[str, set[tuple]]:
    """Every table's columns, ignoring their order: migrations append
    columns where schema.sql may declare them anywhere."""
    tables = [
        name
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    ]
    return {
        table: {
            (name, type_, notnull, default, pk)
            for _, name, type_, notnull, default, pk in conn.execute(
                f"PRAGMA table_info({table})"
            )
        }
        for table in tables
    }


@pytest.fixture
def db_v0():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_V0_PATH.read_text())
    yield conn
    conn.close()


def test_schema_file_is_at_the_latest_version():
    version = re.search(r"PRAGMA user_version = (\d+);", SCHEMA_PATH.read_text())
    assert version is not None
    assert int(version.group(1)) == SCHEMA_VERSION


def test_migrated_database_matches_a_fresh_one(db, db_v0):
    assert get_schema_version(db_v0) == 0

    migrate_database(db_v0)

    assert get_schema_version(db_v0) == SCHEMA_VERSION
    assert columns(db_v0) == columns(db)


def test_migration_keeps_existing_data(db_v0):
    db_v0.execute(
        "INSERT INTO artists (id, name, normalized_name) VALUES (1, 'Air', 'air')"
    )
    db_v0.execute(
        "INSERT INTO albums (id, name, artist_id, normalized_name) "
        "VALUES (1, 'Moon Safari', 1, 'moon safari')"
    )
    db_v0.execute(
        "INSERT INTO songs (id, path, title, artist_credit, album_id, duration, "
        "format, file_size) VALUES (1, 'a.mp3', 'Sexy Boy', 'Air', 1, 298.0, 'mp3', 1)"
    )
    db_v0.commit()

    migrate_database(db_v0)

    assert db_v0.execute("SELECT title, cue_in, cue_out FROM songs").fetchall() == [
        ("Sexy Boy", None, None)
    ]


def test_migrating_twice_changes_nothing(db_v0):
    migrate_database(db_v0)
    migrate_database(db_v0)

    assert get_schema_version(db_v0) == SCHEMA_VERSION


def test_empty_database_is_left_to_the_ingest():
    conn = sqlite3.connect(":memory:")

    migrate_database(conn)

    assert get_schema_version(conn) == 0
    assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []
