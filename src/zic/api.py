import sqlite3
import logging
import time

from collections import defaultdict
from typing import Any
from enum import Enum

from zic.models.artist import Artist
from zic.models.genre import Genre
from zic.models.album import Album, AlbumCover
from zic.models.song import Song
from zic.models.playlist import Playlist
from zic.config import get_app_config
from zic.utils.query_builder import QueryBuilder
from zic.utils.db_utils import RowFactory
from zic.logging import get_logger


SONG_CHUNK_LIMIT = 50
LOGGER = get_logger("API")


class AlbumSongOrder(Enum):
        TRACK_NUM = 1
        RANDOM = 2
        SONG_ID = 3


class ZicApi:
    @staticmethod
    def connect_to_db() -> sqlite3.Connection:
        db_path = get_app_config().db_path
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        LOGGER.debug(f"Connected to database {db_path}")
        return conn

    def __init__(self) -> None:
        self.connection: sqlite3.Connection = self.connect_to_db()

        self._artists_cache: list[Artist] | None = None
        self._genres_cache: list[Genre] | None = None
        self._albums_cache: list[Album] | None = None

    def disconnect(self) -> None:
        self.connection.close()

    def invalidate_caches(self) -> None:
        self.invalidate_artists_cache()
        self.invalidate_genres_cache()
        self.invalidate_albums_cache()

    def _cache_artists(self) -> None:
        start_time = time.perf_counter()
        cur = self.connection.execute("SELECT id, name, normalized_name FROM artists;")
        self._artists_cache = [Artist(*row) for row in cur.fetchall()]
        LOGGER.debug(
            f"{len(self._artists_cache)} artists fetched in {time.perf_counter() - start_time:.3f}s"
        )

    def invalidate_artists_cache(self) -> None:
        self._artists_cache = None

    def artists(self) -> list[Artist]:
        if self._artists_cache is None:
            self._cache_artists()
        return self._artists_cache

    def _cache_genres(self) -> None:
        start_time = time.perf_counter()
        cur = self.connection.execute("SELECT id, name, position FROM genres;")
        self._genres_cache = [Genre(*row) for row in cur.fetchall()]
        LOGGER.debug(
            f"{len(self._genres_cache)} genres fetched in {time.perf_counter() - start_time:.3f}s"
        )

    def invalidate_genres_cache(self) -> None:
        self._genres_cache = None

    def genres(self) -> list[Genre]:
        if self._genres_cache is None:
            self._cache_genres()
        return self._genres_cache

    def _cache_albums(self) -> None:
        start_time = time.perf_counter()
        with RowFactory(self.connection, sqlite3.Row):
            cur = self.connection.cursor()

            cur.execute(
                "SELECT "
                "albums.id, "
                "albums.name, "
                "albums.year, "
                "albums.raw_date, "
                "albums.artist_id, "
                "artists.name AS artist_name, "
                "artists.normalized_name AS artist_normalized_name, "
                "albums.is_compilation "
                "FROM albums "
                "LEFT JOIN artists ON artists.id = albums.artist_id;"
            )
            album_rows = cur.fetchall()

            cur.execute(
                "SELECT DISTINCT "
                "album_genres.album_id, "
                "genres.id AS genre_id, "
                "genres.name AS genre_name, "
                "genres.position AS genre_position "
                "FROM album_genres "
                "JOIN genres ON genres.id = album_genres.genre_id;"
            )
            genre_rows = cur.fetchall()

            genres_by_album: dict[int, list[Genre]] = defaultdict(list)
            for row in genre_rows:
                genres_by_album[row["album_id"]].append(
                    Genre(row["genre_id"], row["genre_name"], row["genre_position"])
                )

            self._albums_cache = []

            for row in album_rows:
                album = Album(
                    id=row["id"],
                    name=row["name"],
                    year=row["year"],
                    raw_date=row["raw_date"],
                    _artist_id=row["artist_id"],
                    _artist_name=row["artist_name"],
                    _artist_normalized_name=row["artist_normalized_name"],
                    is_compilation=bool(row["is_compilation"]),
                    genres=genres_by_album.get(row["id"], []),
                )
                self._albums_cache.append(album)

        LOGGER.debug(
            f"{len(self._albums_cache)} albums fetched in {time.perf_counter() - start_time:.3f}s"
        )

    def invalidate_albums_cache(self) -> None:
        self._albums_cache = None

    def albums(self) -> list[Album]:
        if self._albums_cache is None:
            self._cache_albums()
        return self._albums_cache

    def get_song_query(self) -> QueryBuilder:
        return QueryBuilder(
            "SELECT "
            "songs.id AS id, "
            "songs.path AS path, "
            "songs.title AS title, "
            "songs.artist_credit AS artist_credit, "
            "songs.track_number AS track_number, "
            "songs.track_total AS track_total, "
            "songs.disc_number AS disc_number, "
            "songs.disc_total AS disc_total, "
            "songs.duration AS duration, "
            "songs.format AS format, "
            "songs.bitrate AS bitrate, "
            "songs.sample_rate AS sample_rate, "
            "songs.content_hash AS content_hash, "
            "songs.sort_title AS sort_title, "
            "songs.like_count AS like_count, "
            "songs.play_count AS play_count, "
            "songs.last_played_at AS last_played_at, "
            "songs.hidden AS hidden, "
            "songs.added_to_library_at AS added_to_library_at, "
            "songs.file_modified_at AS file_modified_at, "
            "songs.imported_at AS imported_at, "
            "albums.id AS album_id, "
            "albums.name AS album_name, "
            "albums.year AS album_year, "
            "albums.raw_date AS album_raw_date, "
            "albums.is_compilation AS album_is_compilation, "
            "artists.id AS album_artist_id, "
            "artists.name AS album_artist_name, "
            "artists.normalized_name AS album_artist_normalized_name, "
            "genres.id AS genre_id, "
            "genres.name AS genre_name, "
            "genres.position AS genre_position "
            "FROM songs "
            "LEFT JOIN albums ON albums.id = songs.album_id "
            "LEFT JOIN artists ON artists.id = albums.artist_id "
            "LEFT JOIN genres ON genres.id = songs.genre_tag_id "
            "WHERE hidden = FALSE"
        )

    def get_songs_from_rows(self, rows: list[Any]) -> list[Song]:
        songs: list[Song] = []

        for row in rows:
            genre = None
            if row["genre_id"] is not None:
                genre = Genre(row["genre_id"], row["genre_name"], row["genre_position"])

            album = Album(
                id=row["album_id"],
                name=row["album_name"],
                year=row["album_year"],
                raw_date=row["album_raw_date"],
                _artist_id=row["album_artist_id"],
                _artist_name=row["album_artist_name"],
                _artist_normalized_name=row["album_artist_normalized_name"],
                is_compilation=bool(row["album_is_compilation"]),
                genres=[genre] if genre is not None else [],
            )

            songs.append(
                Song(
                    id=row["id"],
                    path=row["path"],
                    title=row["title"],
                    artist_credit=row["artist_credit"],
                    album=album,
                    track_number=row["track_number"],
                    track_total=row["track_total"],
                    disc_number=row["disc_number"],
                    disc_total=row["disc_total"],
                    duration=row["duration"],
                    format=row["format"],
                    bitrate=row["bitrate"],
                    sample_rate=row["sample_rate"],
                    content_hash=row["content_hash"],
                    sort_title=row["sort_title"],
                    like_count=row["like_count"],
                    play_count=row["play_count"],
                    last_played_at=row["last_played_at"],
                    hidden=row["hidden"],
                    added_to_library_at=row["added_to_library_at"],
                    file_modified_at=row["file_modified_at"],
                    imported_at=row["imported_at"],
                    genre=genre,
                )
            )

        return songs

    def fetch_random_songs(self, exclude_ids: set[int] | None = None) -> list[Song]:
        start_time = time.perf_counter()
        query = self.get_song_query()

        if exclude_ids:
            query.push("AND songs.id NOT IN")
            query.push_binds(exclude_ids)

        query.push(f"ORDER BY RANDOM() LIMIT {SONG_CHUNK_LIMIT}")

        with RowFactory(self.connection, sqlite3.Row):
            cur = self.connection.execute(*query.build())
            rows = cur.fetchall()

        songs = self.get_songs_from_rows(rows)

        LOGGER.debug(
            f"{len(songs)} random songs fetched in {time.perf_counter() - start_time:.3f}s"
        )
        return songs

    def get_random_playlist(self) -> Playlist:
        return Playlist(self.fetch_random_songs)

    def get_album_cover_thumbnail(self, album: Album) -> AlbumCover | None:
        start_time = time.perf_counter()
        query = QueryBuilder(
            "SELECT thumbnail, dominant_color FROM covers_thumbnails WHERE album_id ="
        )
        query.push_bind(album.id)
        cur = self.connection.execute(*query.build())
        result = cur.fetchone()
        LOGGER.debug(
            f"Album cover thumbnail for (id: {album.id}) fetched in {time.perf_counter() - start_time:.3f}s"
        )
        return AlbumCover(result[0], result[1]) if result else None

    def get_albums_cover_thumbnails(self, albums: list[Album]) -> dict[int, AlbumCover]:
        start_time = time.perf_counter()
        query = QueryBuilder(
            "SELECT album_id, thumbnail, dominant_color FROM covers_thumbnails WHERE album_id IN"
        )
        query.push_binds([album.id for album in albums])
        cur = self.connection.execute(*query.build())
        result = {row[0]: AlbumCover(row[1], row[2]) for row in cur.fetchall()}
        LOGGER.debug(
            f"{len(result)} album cover thumbnails fetched in {time.perf_counter() - start_time:.3f}s"
        )
        return result

    def get_song_path(self, song: Song) -> str:
        return str(get_app_config().root_dir / song.path)

    def record_song_play(self, song: Song) -> int:
        song.play()
        cur = self.connection.execute(
            "INSERT INTO plays (song_id, played_at) VALUES (?, ?)",
            (song.id, song.last_played_at.isoformat()),
        )
        self.connection.commit()
        LOGGER.debug(f"Song (id: {song.id}) added to plays")
        return cur.lastrowid

    def mark_play_skipped(self, play_id: int) -> None:
        self.connection.execute(
            "UPDATE plays SET completed = 0 WHERE id = ?",
            (play_id,),
        )
        self.connection.commit()
        LOGGER.debug(f"Play (id: {play_id}) marked as skipped")

    def sync_song(self, song: Song) -> None:
        query = QueryBuilder("UPDATE songs SET ")
        query.push("like_count =")
        query.push_bind(song.like_count)
        query.push(", play_count =")
        query.push_bind(song.play_count)
        query.push(", last_played_at =")
        query.push_bind(
            song.last_played_at.isoformat() if song.last_played_at else None
        )
        query.push("WHERE songs.id =")
        query.push_bind(song.id)
        self.connection.execute(*query.build())
        self.connection.commit()
        LOGGER.debug(f"Song synchronized : {song}")

    def get_album_songs(
        self,
        album: Album,
        order_mode: AlbumSongOrder = AlbumSongOrder.TRACK_NUM,
        song: Song | None = None,
    ) -> list[Song]:
        start_time = time.perf_counter()
        query = self.get_song_query()
        query.push("AND songs.album_id =")
        query.push_bind(album.id)
        if order_mode == AlbumSongOrder.TRACK_NUM:
            query.push("ORDER BY songs.track_number")
        elif order_mode == AlbumSongOrder.RANDOM:
            query.push("ORDER BY RANDOM()")
        elif order_mode == AlbumSongOrder.SONG_ID:
            if song is None:
                raise ValueError(f"Song must be provided with order mode to {order_mode}, got None")
            query.push("ORDER BY CASE WHEN songs.track_number IS NULL THEN 1 ELSE 0 END,")
            query.push("((songs.track_number - ")
            query.push_bind(song.track_number)
            query.push(") + 10000) % 10000")

        with RowFactory(self.connection, sqlite3.Row):
            cur = self.connection.execute(*query.build())
            rows = cur.fetchall()

        songs = self.get_songs_from_rows(rows)

        LOGGER.debug(
            f"{len(songs)} songs from {album.name} fetched in {time.perf_counter() - start_time:.3f}s"
        )
        return songs

    def get_album_playlist(self, album: Album) -> None:
        return Playlist(
            lambda *_: self.get_album_songs(album),
            self.fetch_random_songs  # TODO : replace by a similarity algo
        )

    def get_shuffle_album_playlist(self, album: Album) -> None:
        return Playlist(
            lambda *_: self.get_album_songs(album, order_mode=AlbumSongOrder.RANDOM),
            self.fetch_random_songs  # TODO : replace by a similarity algo
        )
    
    def get_song_playlist(self, album: Album, song: Song) -> None:
        return Playlist(
            lambda *_: self.get_album_songs(album, order_mode=AlbumSongOrder.SONG_ID, song=song),
            self.fetch_random_songs  # TODO : replace by a similarity algo
        )

    def get_song_artists(self, song: Song) -> list[Artist]:
        start_time = time.perf_counter()
        cur = self.connection.execute(
            "SELECT artists.id, artists.name, artists.normalized_name "
            "FROM song_artists "
            "JOIN artists ON artists.id = song_artists.artist_id "
            "WHERE song_artists.song_id = ? "
            "ORDER BY song_artists.position, artists.id;",
            (song.id,),
        )
        artists = [Artist(*row) for row in cur.fetchall()]
        LOGGER.debug(
            f"{len(artists)} artists for song (id: {song.id}) fetched in "
            f"{time.perf_counter() - start_time:.3f}s"
        )
        return artists
