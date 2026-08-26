import sqlite3

from zic.models.artist import Artist
from zic.models.genre import Genre
from zic.models.album import Album
from zic.models.song import Song
from zic.config import APP_CONFIG


def connect_to_db() -> sqlite3.Connection:
    conn = sqlite3.connect(APP_CONFIG.db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


