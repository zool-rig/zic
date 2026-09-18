-- Final schema - music library (SQLite)

PRAGMA foreign_keys = ON;

CREATE TABLE artists (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    normalized_name   TEXT NOT NULL UNIQUE   -- trim + lower, to deduplicate variants
);

CREATE TABLE albums (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    year             INTEGER,                -- extracted from raw_date (4-digit regex)
    raw_date         TEXT,                   -- raw value of the "date" tag, format not guaranteed
    artist_id        INTEGER NOT NULL,       -- based on albumartist (fallback: artist of track 1, else unknown)
    is_compilation   INTEGER NOT NULL DEFAULT 0,
    normalized_name  TEXT NOT NULL UNIQUE,   -- trim + lower, to deduplicate variants

    FOREIGN KEY (artist_id) REFERENCES artists(id),
    UNIQUE (name, artist_id)
);

-- Cover thumbnails, kept separate from "albums" to keep its SELECTs light.
-- Used only for list/grid display (BLOB <100KB: faster stored in the DB
-- according to SQLite's own benchmarks: https://sqlite.org/intern-v-extern-blob.html).
-- The high-resolution cover is NOT cached: when a track is played, the app
-- reads the embedded artwork straight from the file's metadata (APIC/covr).
CREATE TABLE covers_thumbnails (
    album_id        INTEGER PRIMARY KEY,
    thumbnail       BLOB NOT NULL,
    mime_type       TEXT NOT NULL,        -- 'image/jpeg' | 'image/png'
    width           INTEGER,              -- thumbnail dimensions (not the original)
    height          INTEGER,
    dominant_color  TEXT,                 -- e.g. "#3a2f5e", computed once at extraction time

    FOREIGN KEY (album_id) REFERENCES albums(id) ON DELETE CASCADE,
    CHECK (length(thumbnail) <= 102400)   -- 100 KB, DB-level safety net
);

CREATE TABLE genres (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    position   TEXT   -- proximity vector, JSON: "[0.12, -0.4, ...]" (computed offline via Last.fm)
);

CREATE TABLE album_genres (
    album_id   INTEGER NOT NULL,
    genre_id   INTEGER NOT NULL,

    PRIMARY KEY (album_id, genre_id),
    FOREIGN KEY (album_id) REFERENCES albums(id) ON DELETE CASCADE,
    FOREIGN KEY (genre_id) REFERENCES genres(id) ON DELETE CASCADE
);

CREATE TABLE songs (
    id              INTEGER PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE,   -- relative path of the file
    title           TEXT NOT NULL,

    artist_credit   TEXT NOT NULL,          -- raw "artist" tag, kept as-is, never lost
    album_id        INTEGER NOT NULL,

    track_number    INTEGER,
    track_total     INTEGER,
    disc_number     INTEGER,
    disc_total      INTEGER,

    genre_tag_id    INTEGER,                -- genre taken directly from the file's tag, nullable

    duration        REAL NOT NULL,

    -- technical
    format          TEXT NOT NULL,          -- 'mp3' | 'm4a'
    file_size       INTEGER NOT NULL,
    bitrate         INTEGER,
    sample_rate     INTEGER,
    content_hash    TEXT,                   -- content-based dedup, independent of the file name

    extra_tags      TEXT,                   -- JSON: bpm, comment, copyright, composer, sort fields, etc.

    -- application
    sort_title      TEXT,                   -- normalized title for sorting (ignores articles/punctuation)
    like_count      INTEGER NOT NULL DEFAULT 0,
    play_count      INTEGER NOT NULL DEFAULT 0,   -- denormalized cache, maintained by trigger from "plays"
    last_played_at  TEXT,                   -- same, NULL until first played
    hidden          INTEGER NOT NULL DEFAULT 0,   -- hidden from the library without being deleted

    -- dates
    added_to_library_at   TEXT NOT NULL DEFAULT (datetime('now')),  -- first time seen in the library
    file_modified_at      TEXT,             -- file mtime at last scan (detects on-disk changes)
    imported_at            TEXT NOT NULL DEFAULT (datetime('now')), -- last technical (re)scan

    FOREIGN KEY (album_id) REFERENCES albums(id),
    FOREIGN KEY (genre_tag_id) REFERENCES genres(id)
);

-- Listening history, one row per play (used as a base for recommendation algorithms)
CREATE TABLE plays (
    id          INTEGER PRIMARY KEY,
    song_id     INTEGER NOT NULL,
    played_at   TEXT NOT NULL DEFAULT (datetime('now')),
    completed   INTEGER NOT NULL DEFAULT 1,   -- 0 if skipped early

    FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
);

CREATE INDEX idx_plays_song_id ON plays(song_id);
CREATE INDEX idx_plays_played_at ON plays(played_at);

-- Automatically keeps songs.play_count / last_played_at in sync on every play
CREATE TRIGGER trg_plays_after_insert
AFTER INSERT ON plays
BEGIN
    UPDATE songs
    SET play_count = play_count + 1,
        last_played_at = NEW.played_at
    WHERE id = NEW.song_id;
END;

CREATE TABLE song_artists (
    song_id     INTEGER NOT NULL,
    artist_id   INTEGER NOT NULL,
    role        TEXT NOT NULL DEFAULT 'main',   -- 'main' | 'featured' | 'composer' | 'performer'
    position    INTEGER NOT NULL DEFAULT 0,     -- order of appearance, for display purposes

    PRIMARY KEY (song_id, artist_id, role),
    FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE,
    FOREIGN KEY (artist_id) REFERENCES artists(id)
);

-- Useful indexes for frequent lookups/joins
CREATE INDEX idx_songs_album_id ON songs(album_id);
CREATE INDEX idx_albums_artist_id ON albums(artist_id);
CREATE INDEX idx_song_artists_artist_id ON song_artists(artist_id);
CREATE INDEX idx_album_genres_genre_id ON album_genres(genre_id);
