import sqlite3

import pytest

from zic import config as zic_config
from zic.ingestor.ingest import SCHEMA_PATH


@pytest.fixture(autouse=True)
def reset_config_singletons():
    """Every test starts with fresh config singletons, so nothing leaks
    from a previously-run test."""
    zic_config.APP_CONFIG = None
    zic_config.USER_CONFIG = None
    yield
    zic_config.APP_CONFIG = None
    zic_config.USER_CONFIG = None


@pytest.fixture
def app_paths(tmp_path, monkeypatch):
    """Redirects app/user config files to a temp dir instead of the real
    OS config locations, so tests never touch the developer's machine."""
    app_config_path = tmp_path / "config" / "app_config.toml"
    user_config_path = tmp_path / "data" / "user_config.json"
    monkeypatch.setattr(zic_config, "APP_CONFIG_PATH", app_config_path)
    monkeypatch.setattr(zic_config, "USER_CONFIG_PATH", user_config_path)
    return app_config_path, user_config_path


@pytest.fixture
def db():
    """An in-memory SQLite connection with ZIC's schema applied, empty."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    yield conn
    conn.close()


def _seed_library(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO artists (id, name, normalized_name) VALUES (1, 'Air', 'air')")
    conn.execute(
        "INSERT INTO artists (id, name, normalized_name) VALUES (2, 'Daft Punk', 'daft punk')"
    )

    conn.execute("INSERT INTO genres (id, name, position) VALUES (1, 'electronic', '[0.0, 0.0]')")
    conn.execute(
        "INSERT INTO genres (id, name, position) VALUES (2, 'french touch', '[0.1, 0.05]')"
    )
    conn.execute("INSERT INTO genres (id, name, position) VALUES (3, 'rock', '[5.0, 5.0]')")

    conn.execute(
        "INSERT INTO albums (id, name, year, raw_date, artist_id, is_compilation, normalized_name) "
        "VALUES (1, 'Moon Safari', 1998, '1998', 1, 0, 'moon safari')"
    )
    conn.execute(
        "INSERT INTO albums (id, name, year, raw_date, artist_id, is_compilation, normalized_name) "
        "VALUES (2, 'Discovery', 2001, '2001', 2, 0, 'discovery')"
    )
    conn.execute(
        "INSERT INTO albums (id, name, year, raw_date, artist_id, is_compilation, normalized_name) "
        "VALUES (3, 'Talkie Walkie', 2004, '2004', 1, 0, 'talkie walkie')"
    )

    conn.execute("INSERT INTO album_genres (album_id, genre_id) VALUES (1, 1)")
    conn.execute("INSERT INTO album_genres (album_id, genre_id) VALUES (1, 2)")
    conn.execute("INSERT INTO album_genres (album_id, genre_id) VALUES (2, 2)")
    # Talkie Walkie (album 3) intentionally has no genre.

    songs = [
        # id, path,                          title,                artist_credit, album_id, track, genre
        (1, "air/moon_safari/01.mp3",        "La Femme d'Argent",  "Air",       1, 1, 1),
        (2, "air/moon_safari/02.mp3",        "Sexy Boy",           "Air",       1, 2, 1),
        (5, "air/moon_safari/03.mp3",        "Talisman",           "Air",       1, 3, 1),
        (3, "daft_punk/discovery/01.mp3",    "One More Time",      "Daft Punk", 2, 1, 2),
        (4, "daft_punk/discovery/02.mp3",    "Aerodynamic",        "Daft Punk", 2, 2, 2),
        (6, "air/talkie_walkie/01.mp3",      "Cherry Blossom Girl","Air",       3, 1, None),
    ]
    artist_by_album = {1: 1, 2: 2, 3: 1}
    for song_id, path, title, artist_credit, album_id, track_number, genre_id in songs:
        conn.execute(
            "INSERT INTO songs "
            "(id, path, title, artist_credit, album_id, track_number, genre_tag_id, "
            "duration, format, file_size) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 180.0, 'mp3', 1000)",
            (song_id, path, title, artist_credit, album_id, track_number, genre_id),
        )
        conn.execute(
            "INSERT INTO song_artists (song_id, artist_id, role, position) VALUES (?, ?, 'main', 0)",
            (song_id, artist_by_album[album_id]),
        )


@pytest.fixture
def library_db_path(tmp_path):
    db_path = tmp_path / "library.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    _seed_library(conn)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def api(library_db_path, tmp_path, monkeypatch):
    from zic.api import ZicApi
    from zic.config import AppConfig

    app_config = AppConfig(db_path=library_db_path, root_dir=tmp_path)
    monkeypatch.setattr("zic.api.get_app_config", lambda: app_config)

    instance = ZicApi()
    yield instance
    instance.disconnect()
