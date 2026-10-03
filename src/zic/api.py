import heapq
import math
import random
import sqlite3
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from zic.config import get_app_config
from zic.ingestor.ingest import (
    clean_name,
    compute_hash,
    genre_match_key,
    get_or_create_artist,
    get_or_create_genre,
    link_album_genre,
    make_sort_title,
    normalize_name,
    resolve_artist_field,
    set_song_artists,
    split_genres,
)
from zic.logging import get_logger
from zic.models.album import Album, AlbumCover
from zic.models.artist import Artist
from zic.models.genre import Genre
from zic.models.playlist import Playlist
from zic.models.song import Song
from zic.utils.db_utils import InvalidDatabaseError, RowFactory, check_database
from zic.utils.query_builder import QueryBuilder
from zic.utils.tags import (
    TagWriteError,
    check_writable,
    format_number_pair,
    read_tags,
    write_tags,
)
from zic.utils.text import fuzzy_alternatives, match_rank, normalize_search_text

SONG_CHUNK_LIMIT = 50
SEARCH_RESULTS_LIMIT = 5
LOGGER = get_logger("API")


class AlbumSongOrder(Enum):
    TRACK_NUM = 1
    RANDOM = 2
    SONG_ID = 3


@dataclass(slots=True)
class SearchResults:
    artists: list[Artist] = field(default_factory=list)
    albums: list[Album] = field(default_factory=list)
    genres: list[Genre] = field(default_factory=list)
    songs: list[Song] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.artists or self.albums or self.genres or self.songs)


# A search entry: (name, context, "name context", item). The name is what's
# ranked best, the context (e.g. the artist) only helps matching, and the
# joined text allows a fast substring pre-filter.
type SearchEntry[T] = tuple[str, str, str, T]


def make_search_entry[T](name: str, context: str, item: T) -> SearchEntry[T]:
    name, context = normalize_search_text(name), normalize_search_text(context)
    return name, context, f"{name} {context}", item


@dataclass(slots=True)
class SearchIndex:
    """Normalized search keys, built once so a search never re-normalizes
    the whole library."""

    artists: list[SearchEntry[Artist]]
    albums: list[SearchEntry[Album]]
    genres: list[SearchEntry[Genre]]
    songs: list[SearchEntry[int]]  # song ids, songs are fetched on demand
    vocabulary: set[str]  # words of artist, album and genre names (typo fixes)
    known_text: str  # every indexed word, to tell typos from real words


@dataclass(slots=True)
class SongEdit:
    title: str
    artist_credit: str
    track_number: int | None
    disc_number: int | None


@dataclass(slots=True)
class AlbumEdit:
    name: str
    artist_name: str
    year: int | None
    genres: list[str]


class ZicApi:
    @staticmethod
    def connect_to_db() -> sqlite3.Connection:
        db_path = get_app_config().db_path
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        if not check_database(conn):
            conn.close()
            raise InvalidDatabaseError(db_path)
        LOGGER.debug(f"Connected to database {db_path}")
        return conn

    def __init__(self) -> None:
        self.connection: sqlite3.Connection = self.connect_to_db()

        self._artists_cache: list[Artist] | None = None
        self._genres_cache: list[Genre] | None = None
        self._albums_cache: list[Album] | None = None
        self._search_index_cache: SearchIndex | None = None

        self.mood: set[int] | None = None

        # Player writes made while another process (ingest) writes the DB:
        # replayed in order by resume_writes(). None when writes go through.
        self._deferred_writes: list[Callable[[], None]] | None = None
        # Temporary (negative) ids of deferred plays -> their real ids.
        self._deferred_play_ids: dict[int, int] = {}
        self._next_deferred_play_id: int = -1

    def disconnect(self) -> None:
        self.connection.close()

    def invalidate_caches(self) -> None:
        self.invalidate_artists_cache()
        self.invalidate_genres_cache()
        self.invalidate_albums_cache()
        self.invalidate_search_index()

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

    def _fetch_genres_by_album(
        self, album_ids: set[int] | None = None
    ) -> dict[int, list[Genre]]:
        """Genres of each album, from album_genres. Fetches every album when
        album_ids is None."""
        query = QueryBuilder(
            "SELECT DISTINCT "
            "album_genres.album_id AS album_id, "
            "genres.id AS genre_id, "
            "genres.name AS genre_name, "
            "genres.position AS genre_position "
            "FROM album_genres "
            "JOIN genres ON genres.id = album_genres.genre_id"
        )
        if album_ids is not None:
            if not album_ids:
                return {}
            query.push("WHERE album_genres.album_id IN")
            query.push_binds(album_ids)

        with RowFactory(self.connection, sqlite3.Row):
            cur = self.connection.execute(*query.build())
            rows = cur.fetchall()

        genres_by_album: dict[int, list[Genre]] = defaultdict(list)
        for row in rows:
            genres_by_album[row["album_id"]].append(
                Genre(row["genre_id"], row["genre_name"], row["genre_position"])
            )
        return dict(genres_by_album)

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

            genres_by_album = self._fetch_genres_by_album()

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

    def get_song_query(self, include_hidden: bool = False) -> QueryBuilder:
        query = QueryBuilder(
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
            "artists.normalized_name AS album_artist_normalized_name "
            "FROM songs "
            "LEFT JOIN albums ON albums.id = songs.album_id "
            "LEFT JOIN artists ON artists.id = albums.artist_id "
            "WHERE TRUE"
        )
        if not include_hidden:
            query.push("AND hidden = FALSE")
        return query

    def get_songs_from_rows(self, rows: list[Any]) -> list[Song]:
        genres_by_album = self._fetch_genres_by_album({row["album_id"] for row in rows})

        songs: list[Song] = []

        for row in rows:
            album = Album(
                id=row["album_id"],
                name=row["album_name"],
                year=row["album_year"],
                raw_date=row["album_raw_date"],
                _artist_id=row["album_artist_id"],
                _artist_name=row["album_artist_name"],
                _artist_normalized_name=row["album_artist_normalized_name"],
                is_compilation=bool(row["album_is_compilation"]),
                genres=genres_by_album.get(row["album_id"], []),
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
                )
            )

        return songs

    def fetch_random_songs(
        self, exclude_ids: set[int] | None = None, limit: int = SONG_CHUNK_LIMIT
    ) -> list[Song]:
        if self.mood:
            songs = self.fetch_mood_songs(exclude_ids, limit)
            if songs:
                return songs
            LOGGER.debug("No song matches the current mood, falling back to random")
        return self.fetch_any_random_songs(exclude_ids, limit)

    def fetch_mood_songs(
        self, exclude_ids: set[int] | None = None, limit: int = SONG_CHUNK_LIMIT
    ) -> list[Song]:
        start_time = time.perf_counter()
        if not self.mood:
            return []

        query = self.get_song_query()
        query.push(
            "AND songs.album_id IN (SELECT album_id FROM album_genres WHERE genre_id IN"
        )
        query.push_binds(self.mood)
        query.push(")")

        if exclude_ids:
            query.push("AND songs.id NOT IN")
            query.push_binds(exclude_ids)

        query.push(f"ORDER BY RANDOM() LIMIT {int(limit)}")

        with RowFactory(self.connection, sqlite3.Row):
            cur = self.connection.execute(*query.build())
            rows = cur.fetchall()

        songs = self.get_songs_from_rows(rows)
        LOGGER.debug(
            f"{len(songs)} mood songs fetched in {time.perf_counter() - start_time:.3f}s"
        )
        return songs

    def fetch_any_random_songs(
        self, exclude_ids: set[int] | None = None, limit: int = SONG_CHUNK_LIMIT
    ) -> list[Song]:
        start_time = time.perf_counter()

        row = self.connection.execute(
            "SELECT MIN(id), MAX(id) FROM songs WHERE hidden = FALSE"
        ).fetchone()
        min_id, max_id = row
        if min_id is None:  # no songs at all
            return []

        exclude_ids = exclude_ids or set()
        collected: dict[int, Song] = {}
        attempts = 0
        max_attempts = 5  # safety net against pathological gaps/exclusions

        while len(collected) < limit and attempts < max_attempts:
            attempts += 1
            needed = limit - len(collected)
            # Oversample a bit: some picks will miss (gaps, hidden, excluded,
            # already collected), so ask for more ids than we still need.
            sample_size = min(needed * 3, max_id - min_id + 1)
            candidate_ids = random.sample(range(min_id, max_id + 1), sample_size)
            candidate_ids = [
                i for i in candidate_ids if i not in exclude_ids and i not in collected
            ]
            if not candidate_ids:
                continue

            query = self.get_song_query()
            query.push("AND songs.id IN")
            query.push_binds(candidate_ids)

            with RowFactory(self.connection, sqlite3.Row):
                cur = self.connection.execute(*query.build())
                rows = cur.fetchall()

            for song in self.get_songs_from_rows(rows):
                collected[song.id] = song

        # SQLite returns "IN (...)" rows sorted by id: shuffle before
        # truncating, otherwise the oversampled chunk keeps (and plays first)
        # the lowest ids only.
        songs = list(collected.values())
        random.shuffle(songs)
        songs = songs[:limit]

        LOGGER.debug(
            f"{len(songs)} random songs fetched in {time.perf_counter() - start_time:.3f}s"
        )
        return songs

    def get_random_playlist(self) -> Playlist:
        # Starts fully random, then follows the mood. Songs are fetched one at
        # a time so that each pick reflects the mood at the moment it's needed.
        self.reset_mood()
        return Playlist(lambda exclude_ids: self.fetch_random_songs(exclude_ids, 1))

    def set_mood(self, song: Song) -> None:
        """Random songs will now match the extended genres of this song."""
        self.mood = self.get_extended_genre_ids(song.album.genres) or None
        LOGGER.debug(
            f"Mood set from song (id: {song.id}): "
            f"{[g.name for g in self.genres() if g.id in (self.mood or ())]}"
        )

    def reset_mood(self) -> None:
        self.mood = None
        LOGGER.debug("Mood reset")

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

    @property
    def writes_suspended(self) -> bool:
        return self._deferred_writes is not None

    def suspend_writes(self) -> None:
        """Queues the player's writes (plays, skips, likes) instead of
        running them, while another process holds the DB write lock: they
        would otherwise wait for it, then fail with "database is locked"."""
        if self._deferred_writes is None:
            self._deferred_writes = []
            LOGGER.debug("Writes suspended")

    def resume_writes(self) -> None:
        writes, self._deferred_writes = self._deferred_writes or [], None
        for write in writes:
            write()
        LOGGER.debug(f"Writes resumed, {len(writes)} deferred writes applied")

    def _write(self, write: Callable[[], None]) -> None:
        if self._deferred_writes is not None:
            self._deferred_writes.append(write)
        else:
            write()

    def _insert_play(self, song_id: int, played_at: str) -> int:
        cur = self.connection.execute(
            "INSERT INTO plays (song_id, played_at) VALUES (?, ?)",
            (song_id, played_at),
        )
        self.connection.commit()
        LOGGER.debug(f"Song (id: {song_id}) added to plays")
        return cur.lastrowid

    def record_song_play(self, song: Song) -> int:
        song.play()
        played_at = song.last_played_at.isoformat()
        if self._deferred_writes is None:
            return self._insert_play(song.id, played_at)

        # No real id before the insert: hand out a temporary one, mapped to
        # the real one when the write is replayed.
        temp_id = self._next_deferred_play_id
        self._next_deferred_play_id -= 1

        def write() -> None:
            self._deferred_play_ids[temp_id] = self._insert_play(song.id, played_at)

        self._deferred_writes.append(write)
        return temp_id

    def mark_play_skipped(self, play_id: int) -> None:
        def write() -> None:
            real_id = self._deferred_play_ids.get(play_id, play_id)
            self.connection.execute(
                "UPDATE plays SET completed = 0 WHERE id = ?",
                (real_id,),
            )
            self.connection.commit()
            LOGGER.debug(f"Play (id: {real_id}) marked as skipped")

        self._write(write)

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
        # Built now: a deferred write keeps the values of this moment.
        statement = query.build()

        def write() -> None:
            self.connection.execute(*statement)
            self.connection.commit()
            LOGGER.debug(f"Song synchronized : {song}")

        self._write(write)

    def get_album_songs(
        self,
        album: Album,
        order_mode: AlbumSongOrder = AlbumSongOrder.TRACK_NUM,
        song: Song | None = None,
    ) -> list[Song]:
        start_time = time.perf_counter()
        if order_mode == AlbumSongOrder.SONG_ID and song is None:
            raise ValueError(
                f"Song must be provided with order mode to {order_mode}, got None"
            )

        query = self.get_song_query()
        query.push("AND songs.album_id =")
        query.push_bind(album.id)
        if order_mode == AlbumSongOrder.RANDOM:
            query.push("ORDER BY RANDOM()")
        else:
            # Album order: disc, then track (untagged tracks last), with a
            # stable tie-break for missing or duplicated track numbers.
            query.push(
                "ORDER BY COALESCE(songs.disc_number, 1), "
                "songs.track_number IS NULL, songs.track_number, "
                "songs.sort_title, songs.id"
            )

        with RowFactory(self.connection, sqlite3.Row):
            cur = self.connection.execute(*query.build())
            rows = cur.fetchall()

        songs = self.get_songs_from_rows(rows)

        if order_mode == AlbumSongOrder.SONG_ID:
            # Start exactly at the requested song (matched by id, not by
            # track number) and wrap around to the beginning of the album.
            start = next((i for i, s in enumerate(songs) if s.id == song.id), 0)
            songs = songs[start:] + songs[:start]

        LOGGER.debug(
            f"{len(songs)} songs from {album.name} fetched in {time.perf_counter() - start_time:.3f}s"
        )
        return songs

    def get_rest_discography_from_album(
        self, album: Album, exclude_ids: set[int] | None = None
    ) -> list[Song]:
        start_time = time.perf_counter()
        query = self.get_song_query()
        query.push("AND songs.album_id !=")
        query.push_bind(album.id)
        query.push("AND album_artist_id =")
        query.push_bind(album.artist.id)

        if exclude_ids:
            query.push("AND songs.id NOT IN")
            query.push_binds(exclude_ids)

        with RowFactory(self.connection, sqlite3.Row):
            cur = self.connection.execute(*query.build())
            rows = cur.fetchall()

        songs = self.get_songs_from_rows(rows)
        LOGGER.debug(
            f"{len(songs)} songs from {album.artist.name} fetched in {time.perf_counter() - start_time:.3f}s"
        )
        return songs

    def get_near_songs_from_album(
        self, album: Album, exclude_ids: set[int] | None = None
    ) -> list[Song]:
        start_time = time.perf_counter()
        near_genres_ids = self.get_extended_genre_ids(album.genres)
        if not near_genres_ids:
            return []

        query = self.get_song_query()
        query.push(
            "AND songs.album_id IN (SELECT album_id FROM album_genres WHERE genre_id IN"
        )
        query.push_binds(near_genres_ids)
        query.push(")")

        if exclude_ids:
            query.push("AND songs.id NOT IN")
            query.push_binds(exclude_ids)

        query.push(f"ORDER BY RANDOM() LIMIT {SONG_CHUNK_LIMIT}")

        with RowFactory(self.connection, sqlite3.Row):
            cur = self.connection.execute(*query.build())
            rows = cur.fetchall()

        songs = self.get_songs_from_rows(rows)
        LOGGER.debug(
            f"{len(songs)} similar songs fetched in {time.perf_counter() - start_time:.3f}s"
        )
        return songs

    def get_album_playlist(self, album: Album) -> Playlist:
        return Playlist(
            lambda *_: self.get_album_songs(album),
            lambda exclude_ids: self.get_rest_discography_from_album(
                album, exclude_ids=exclude_ids
            ),
            lambda exclude_ids: self.get_near_songs_from_album(
                album, exclude_ids=exclude_ids
            ),
            self.fetch_random_songs,
        )

    def get_shuffle_album_playlist(self, album: Album) -> Playlist:
        return Playlist(
            lambda *_: self.get_album_songs(album, order_mode=AlbumSongOrder.RANDOM),
            lambda exclude_ids: self.get_rest_discography_from_album(
                album, exclude_ids=exclude_ids
            ),
            lambda exclude_ids: self.get_near_songs_from_album(
                album, exclude_ids=exclude_ids
            ),
            self.fetch_random_songs,
        )

    def get_song_playlist(self, album: Album, song: Song) -> Playlist:
        return Playlist(
            lambda *_: self.get_album_songs(
                album, order_mode=AlbumSongOrder.SONG_ID, song=song
            ),
            lambda exclude_ids: self.get_rest_discography_from_album(
                album, exclude_ids=exclude_ids
            ),
            lambda exclude_ids: self.get_near_songs_from_album(
                album, exclude_ids=exclude_ids
            ),
            self.fetch_random_songs,
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

    def get_metadata(self, key: str) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def last_ingest_date(self) -> datetime | None:
        last_ingest = self.get_metadata("last_ingest")
        if last_ingest:
            return datetime.fromisoformat(last_ingest)

    def _genre_distance(self, genre_a: Genre, genre_b: Genre) -> float:
        return math.sqrt(
            sum((x - y) ** 2 for x, y in zip(genre_a.position, genre_b.position))
        )

    def get_near_genres(self, genre: Genre, max_genres: int = 5) -> list[Genre]:
        ranked = sorted(
            [(g, self._genre_distance(genre, g)) for g in self.genres() if g != genre],
            key=lambda x: x[1],
        )
        return [genre for genre, _ in ranked[:max_genres]]

    def get_extended_genre_ids(self, genres: list[Genre]) -> set[int]:
        """Ids of the given genres and of their near genres."""
        extended = {g.id for g in genres}
        for genre in genres:
            extended.update(g.id for g in self.get_near_genres(genre))
        return extended

    def _build_search_index(self) -> None:
        start_time = time.perf_counter()
        artists = [make_search_entry(a.name, "", a) for a in self.artists()]
        albums = [make_search_entry(a.name, a.artist.name, a) for a in self.albums()]
        genres = [make_search_entry(g.name, "", g) for g in self.genres()]
        cur = self.connection.execute(
            "SELECT id, title, artist_credit FROM songs WHERE hidden = FALSE"
        )
        songs = [
            make_search_entry(title, credit, song_id)
            for song_id, title, credit in cur.fetchall()
        ]
        vocabulary = {
            word
            for entries in (artists, albums, genres)
            for _, _, text, _ in entries
            for word in text.split()
        }
        known_text = "\n".join(
            [*vocabulary, *(text for _, _, text, _ in songs)]
        )
        self._search_index_cache = SearchIndex(
            artists, albums, genres, songs, vocabulary, known_text
        )
        LOGGER.debug(
            f"Search index ({len(songs)} songs) built in "
            f"{time.perf_counter() - start_time:.3f}s"
        )

    def invalidate_search_index(self) -> None:
        self._search_index_cache = None

    def search_index(self) -> SearchIndex:
        if self._search_index_cache is None:
            self._build_search_index()
        return self._search_index_cache

    @staticmethod
    def _best_matches[T](
        entries: list[SearchEntry[T]],
        tokens: list[str],
        alternatives: dict[str, list[str]],
        limit: int,
    ) -> list[T]:
        # Ranking is costly: only rank entries containing the longest token
        # (or one of its typo fixes), which every match must contain anyway.
        longest = max(tokens, key=len)
        candidates: dict[int, SearchEntry[T]] = {}
        for needle in (longest, *alternatives.get(longest, ())):
            candidates.update((id(e), e) for e in entries if needle in e[2])

        ranked = (
            (rank, i, item)
            for i, (name, context, _, item) in enumerate(candidates.values())
            if (rank := match_rank(tokens, name, context, alternatives)) is not None
        )
        return [item for *_, item in heapq.nsmallest(limit, ranked)]

    def search(self, text: str, limit: int = SEARCH_RESULTS_LIMIT) -> SearchResults:
        """Best artists, albums, genres and songs matching `text`. Case-,
        accent-, punctuation- and word-order-insensitive, and tolerant to
        small typos in artist, album and genre names."""
        start_time = time.perf_counter()
        tokens = normalize_search_text(text).split()
        if not tokens:
            return SearchResults()

        index = self.search_index()
        alternatives = fuzzy_alternatives(tokens, index.vocabulary, index.known_text)

        def best[T](entries: list[SearchEntry[T]]) -> list[T]:
            return self._best_matches(entries, tokens, alternatives, limit)

        results = SearchResults(
            artists=best(index.artists),
            albums=best(index.albums),
            genres=best(index.genres),
            songs=self._get_songs_by_ids(best(index.songs)),
        )
        LOGGER.debug(
            f"Search {text!r} done in {time.perf_counter() - start_time:.3f}s"
        )
        return results

    def _get_songs_by_ids(self, song_ids: list[int]) -> list[Song]:
        """Songs in the order of song_ids."""
        if not song_ids:
            return []

        query = self.get_song_query()
        query.push("AND songs.id IN")
        query.push_binds(song_ids)

        with RowFactory(self.connection, sqlite3.Row):
            cur = self.connection.execute(*query.build())
            rows = cur.fetchall()

        songs_by_id = {song.id: song for song in self.get_songs_from_rows(rows)}
        return [songs_by_id[i] for i in song_ids if i in songs_by_id]

    # --- metadata edition ---------------------------------------------------
    #
    # Files stay the source of truth: edits are written to the tags first,
    # then to the DB the same way the ingestor would read them back, so a
    # rescan finds the same values. Only changed fields are written.

    def _sync_file_state(self, song_id: int, path: Path) -> None:
        """Records the rewritten file as already scanned, so the next
        incremental scan doesn't re-ingest it."""
        stat = path.stat()
        self.connection.execute(
            "UPDATE songs SET file_modified_at = ?, file_size = ?, content_hash = ? "
            "WHERE id = ?",
            (f"{stat.st_mtime:.6f}", stat.st_size, compute_hash(path), song_id),
        )

    def _delete_orphans(self) -> None:
        self.connection.execute(
            "DELETE FROM genres WHERE id NOT IN (SELECT genre_id FROM album_genres)"
        )
        self.connection.execute(
            "DELETE FROM artists "
            "WHERE id NOT IN (SELECT artist_id FROM albums) "
            "AND id NOT IN (SELECT artist_id FROM song_artists)"
        )

    def update_song(self, song: Song, edit: SongEdit) -> bool:
        """Returns whether anything changed."""
        title = clean_name(edit.title)
        if not title:
            raise ValueError("A song needs a title.")
        artist_tag = clean_name(edit.artist_credit)
        artist_credit = resolve_artist_field(artist_tag)
        path = Path(self.get_song_path(song))

        tags: dict[str, str | None] = {}
        if title != song.title:
            tags["title"] = title
        if artist_credit != song.artist_credit:
            tags["artist"] = artist_tag
            # Without an album artist tag, the ingestor falls back on the
            # song artist to find the album: pin it so the album stays put.
            if "albumartist" not in read_tags(path):
                tags["albumartist"] = song.album.artist.name
        if edit.track_number != song.track_number:
            tags["tracknumber"] = format_number_pair(
                edit.track_number, song.track_total
            )
        if edit.disc_number != song.disc_number:
            tags["discnumber"] = format_number_pair(edit.disc_number, song.disc_total)
        if not tags:
            return False

        check_writable([path])
        write_tags(path, tags)

        with self.connection:
            self.connection.execute(
                "UPDATE songs SET title = ?, sort_title = ?, artist_credit = ?, "
                "track_number = ?, disc_number = ? WHERE id = ?",
                (
                    title,
                    make_sort_title(title),
                    artist_credit,
                    edit.track_number,
                    edit.disc_number,
                    song.id,
                ),
            )
            if "artist" in tags:
                set_song_artists(self.connection, song.id, artist_credit)
                self._delete_orphans()
            self._sync_file_state(song.id, path)

        self.invalidate_caches()
        LOGGER.info(f"Song (id: {song.id}) updated: {sorted(tags)}")
        return True

    def set_song_hidden(self, song: Song, hidden: bool) -> None:
        """Hides the song from the library (app-only flag, no tag)."""
        self.connection.execute(
            "UPDATE songs SET hidden = ? WHERE id = ?", (int(hidden), song.id)
        )
        self.connection.commit()
        song.hidden = hidden
        self.invalidate_search_index()
        LOGGER.debug(f"Song (id: {song.id}) {'hidden' if hidden else 'shown'}")

    def get_hidden_album_songs(self, album: Album) -> list[Song]:
        query = self.get_song_query(include_hidden=True)
        query.push("AND songs.hidden = TRUE AND songs.album_id =")
        query.push_bind(album.id)
        query.push("ORDER BY songs.sort_title, songs.id")

        with RowFactory(self.connection, sqlite3.Row):
            cur = self.connection.execute(*query.build())
            rows = cur.fetchall()
        return self.get_songs_from_rows(rows)

    def find_album_by_name(self, name: str, exclude: Album | None = None) -> Album | None:
        """The album the ingestor would file songs tagged `name` under."""
        norm = normalize_name(clean_name(name) or "")
        return next(
            (
                a
                for a in self.albums()
                if normalize_name(a.name) == norm
                and (exclude is None or a.id != exclude.id)
            ),
            None,
        )

    def update_album(self, album: Album, edit: AlbumEdit) -> int | None:
        """Applies the edit to every song of the album, hidden ones included.
        Returns the album id afterwards (None if nothing changed): renaming an
        album to the name of another one merges it into that one, as a rescan
        would."""
        name = clean_name(edit.name)
        if not name:
            raise ValueError("An album needs a name.")
        artist_tag = clean_name(edit.artist_name)
        artist_name = resolve_artist_field(artist_tag)
        genres = split_genres("; ".join(edit.genres))
        genres_changed = {genre_match_key(g) for g in genres} != {
            genre_match_key(g.name) for g in album.genres
        }

        tags: dict[str, str | None] = {}
        if name != album.name:
            tags["album"] = name
        if artist_name != album.artist.name:
            tags["albumartist"] = artist_tag
        if edit.year != album.year:
            tags["date"] = str(edit.year) if edit.year else None
        if genres_changed:
            tags["genre"] = "; ".join(sorted(genres)) or None
        if not tags:
            return None

        files = [
            (song_id, get_app_config().root_dir / rel_path)
            for song_id, rel_path in self.connection.execute(
                "SELECT id, path FROM songs WHERE album_id = ?", (album.id,)
            )
        ]
        check_writable([path for _, path in files])
        merge_target = self.find_album_by_name(name, exclude=album) if "album" in tags else None

        written = 0
        try:
            for _, path in files:
                write_tags(path, tags)
                written += 1
        except TagWriteError as e:
            if not written:
                raise
            raise TagWriteError(
                f"{e}\n{written} of {len(files)} files were already updated: "
                "check for new songs to resync the library."
            ) from e

        with self.connection:
            album_id = album.id
            if merge_target is not None:
                album_id = merge_target.id
                genres |= {g.name for g in merge_target.genres}
                self.connection.execute(
                    "UPDATE songs SET album_id = ? WHERE album_id = ?",
                    (album_id, album.id),
                )
                self.connection.execute(
                    "INSERT OR IGNORE INTO covers_thumbnails "
                    "(album_id, thumbnail, mime_type, width, height, dominant_color) "
                    "SELECT ?, thumbnail, mime_type, width, height, dominant_color "
                    "FROM covers_thumbnails WHERE album_id = ?",
                    (album_id, album.id),
                )
                self.connection.execute("DELETE FROM albums WHERE id = ?", (album.id,))

            raw_date = tags.get("date", album.raw_date)
            self.connection.execute(
                "UPDATE albums SET name = ?, normalized_name = ?, artist_id = ?, "
                "year = ?, raw_date = ? WHERE id = ?",
                (
                    name,
                    normalize_name(name),
                    get_or_create_artist(self.connection, artist_name),
                    edit.year,
                    raw_date,
                    album_id,
                ),
            )

            if genres_changed or merge_target is not None:
                genres_name_id_map = {
                    genre_match_key(gname): id_
                    for id_, gname in self.connection.execute(
                        "SELECT id, name FROM genres"
                    )
                }
                self.connection.execute(
                    "DELETE FROM album_genres WHERE album_id = ?", (album_id,)
                )
                for genre in genres:
                    genre_id = get_or_create_genre(
                        self.connection, genre, genres_name_id_map
                    )
                    link_album_genre(self.connection, album_id, genre_id)

            self._delete_orphans()
            for song_id, path in files:
                self._sync_file_state(song_id, path)

        self.invalidate_caches()
        LOGGER.info(f"Album (id: {album.id}) updated: {sorted(tags)}")
        return album_id
