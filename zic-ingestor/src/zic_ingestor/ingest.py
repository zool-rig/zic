#!/usr/bin/env python3
"""
ingest.py

Initializes the SQLite database if needed, walks a folder looking for audio
files (.mp3, .m4a), extracts their metadata via mutagen, and populates/
updates the database. When an album has no genre tag, it optionally looks
one up on Last.fm (album.getTopTags) and links it with source='lastfm'.
Same idea for the release date via album.getInfo when the file has none.
Also extracts embedded cover art into a compressed thumbnail cached in DB.

Designed to be run repeatedly (crontab, watchdog triggered on new files):
idempotent, does not reprocess files that are already known and unchanged
since the last run (comparison on the file's modification time).

Dependencies:
    pip install mutagen pillow

Usage:
    python3 ingest.py /path/library
    python3 ingest.py /path/library --db my_music.db
    python3 ingest.py /path/library --rescan          # force re-parsing everything
    python3 ingest.py /path/library --dry-run         # simulate, write nothing

Last.fm lookup (optional, used for missing genres and missing release dates):
    python3 ingest.py /path/library --lastfm-api-key YOUR_KEY
    # or export LASTFM_API_KEY=YOUR_KEY and just run:
    python3 ingest.py /path/library
    python3 ingest.py /path/library --no-lastfm       # disable lookup entirely
Get a free API key at: https://www.last.fm/api/account/create
"""

import argparse
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from mutagen import File as MutagenFile

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

AUDIO_EXTENSIONS = {".mp3", ".m4a"}

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"

# Tag values that mean "no real artist/album", seen in the wild from various
# ripping/tagging tools. Case- and accent-insensitive match, folded to the
# canonical Unknown fallback so they don't create near-duplicate placeholder
# rows in the DB.
ARTIST_PLACEHOLDER_TOKENS = {
    "unknown", "unknown artist", "various", "various artists",
    "inconnu", "artiste inconnu", "n/a", "na", "none", "no artist",
}
ALBUM_PLACEHOLDER_TOKENS = {
    "unknown", "unknown album", "inconnu", "album inconnu",
    "n/a", "na", "none", "no album",
}

# Heuristic separators used to split a composite artist_credit into several
# artists ("A feat. B", "A & B", "A, B"...). Best-effort: on atypical
# composite tags (long classical-music credits, etc.) the split can be
# imperfect. The raw artist_credit is always kept (after noise-stripping via
# clean_name) in the DB regardless, so nothing meaningful is ever lost.
ARTIST_SPLIT_RE = re.compile(
    r"\s*(?:,|;|/|&|\bfeat\.?\b|\bft\.?\b)\s*", re.IGNORECASE
)

# Some taggers store multiple genres joined in a single tag value ("Rock;Pop")
# instead of using repeated tag frames.
GENRE_SPLIT_RE = re.compile(r"\s*;\s*")

# Pure year or decade tokens ("2015", "90s", "2010s") sometimes leak into the
# genre field from scrobble-based taggers -- not actual musical genres.
YEAR_OR_DECADE_RE = re.compile(r"^(?:\d{4}|\d{2}s|\d{4}s)$")

# Personal/list-style tags that occasionally end up in the genre field
# (e.g. via tools that copy a user's Last.fm tag cloud into ID3/MP4 tags),
# not actual musical genres. Necessarily incomplete: catches known recurring
# junk, not every possible arbitrary tag (see ingest.py's docstring).
GENRE_DENYLIST = {
    "wishlist", "vinyl", "favourite albums", "favorite albums", "albums",
    "albums i have listened", "compilation", "long", "joy", "fun",
    "wikipedia", "masterpiece", "remix", "chill",
}
GENRE_DENYLIST_PATTERNS = [
    re.compile(r"^best of \d{4}$", re.IGNORECASE),
    re.compile(r"^\d+ albums.*before you die$", re.IGNORECASE),
]

LEADING_ARTICLE_RE = re.compile(
    r"^(the|a|an|le|la|les|un|une|des)\s+", re.IGNORECASE
)

# Strips stray leading/trailing punctuation and whitespace noise sometimes
# left by ripping tools, e.g. ". High tone        " -> "High tone".
NOISE_RE = re.compile(r"^[\s.\-_/,;:]+|[\s.\-_/,;:]+$")

YEAR_RE = re.compile(r"(\d{4})")

# --- Genre noise filtering ---------------------------------------------------
# The "genre" tag field is sometimes polluted by folksonomy-style tags from
# tools that copy Last.fm-esque free-form tags into it: years, decades,
# artist names, and personal list/note tags that aren't genres at all.

YEAR_OR_DECADE_RE = re.compile(r"^(?:\d{4}|\d{2}s|\d{4}s)$")

# Recurring non-genre "meta" tags seen in the wild (personal list/collection
# tags, not musical genres). Not exhaustive -- arbitrary junk (a stray note,
# a misfiled radio station name...) can't be caught by a fixed list; rejected
# values are preserved in songs.extra_tags rather than silently dropped, so
# nothing is lost even when this list misses something.
GENRE_DENYLIST = {
    "wishlist", "vinyl", "favourite albums", "favorite albums", "albums",
    "albums i have listened", "compilation", "long", "joy", "fun",
    "wikipedia", "masterpiece", "remix", "chill", "all",
}
GENRE_DENYLIST_PATTERNS = [
    re.compile(r"^best of \d{4}$", re.IGNORECASE),
    re.compile(r"^\d+ albums.*before you die$", re.IGNORECASE),
]

# --- Last.fm ---------------------------------------------------------------

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_MIN_TAG_WEIGHT = 10   # ignore tags with a popularity weight below this
LASTFM_MAX_TAGS = 3          # keep at most this many tags per album
LASTFM_REQUEST_DELAY = 0.25  # seconds between calls, stays under Last.fm's ~5 req/s guideline

# --- Cover thumbnails --------------------------------------------------------

COVER_MAX_SIZE = 200          # px, longest side
COVER_MAX_BYTES = 100 * 1024  # must stay under the DB's CHECK constraint


# ---------------------------------------------------------------------------
# DB initialization
# ---------------------------------------------------------------------------

def init_db(conn: sqlite3.Connection):
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='songs'"
    ).fetchone()
    if existing:
        return
    if not SCHEMA_PATH.exists():
        print(f"Error: schema.sql not found next to the script ({SCHEMA_PATH})", file=sys.stderr)
        sys.exit(1)
    conn.executescript(SCHEMA_PATH.read_text())
    print("Database initialized (new file).")


# ---------------------------------------------------------------------------
# Normalization / parsing
# ---------------------------------------------------------------------------

def fold_diacritics(s: str) -> str:
    """"Taï Phong" -> "Tai Phong": strips accents for matching purposes."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_name(name: str) -> str:
    """Comparison key used for artists.normalized_name: case- and
    accent-insensitive, whitespace-collapsed."""
    name = fold_diacritics(name)
    return " ".join(name.split()).strip().lower()


def clean_name(name: str | None) -> str | None:
    """Strips stray leading/trailing punctuation/whitespace noise and
    collapses internal whitespace. Returns None if nothing meaningful is left."""
    if not name:
        return None
    cleaned = NOISE_RE.sub("", name)
    cleaned = " ".join(cleaned.split())
    return cleaned or None


def make_sort_title(title: str) -> str:
    return LEADING_ARTICLE_RE.sub("", title).strip().lower()


def resolve_artist_field(raw: str | None) -> str:
    """Maps a cleaned tag value to UNKNOWN_ARTIST if it's a known placeholder
    ("Unknown", "Various", "Inconnu"...), otherwise returns it as-is."""
    if not raw:
        return UNKNOWN_ARTIST
    key = fold_diacritics(raw).strip().lower()
    if key in ARTIST_PLACEHOLDER_TOKENS:
        return UNKNOWN_ARTIST
    return raw


def resolve_album_field(raw: str | None) -> str:
    if not raw:
        return UNKNOWN_ALBUM
    key = fold_diacritics(raw).strip().lower()
    if key in ALBUM_PLACEHOLDER_TOKENS:
        return UNKNOWN_ALBUM
    return raw


def split_artists(artist_credit: str) -> list[str]:
    parts = [clean_name(p) for p in ARTIST_SPLIT_RE.split(artist_credit)]
    parts = [p for p in parts if p]
    return parts or [artist_credit.strip()]


def split_genres(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = [clean_name(p) for p in GENRE_SPLIT_RE.split(raw)]
    return [p for p in parts if p]


def is_year_or_decade(token: str) -> bool:
    return bool(YEAR_OR_DECADE_RE.fullmatch(token.strip()))


def is_denylisted_genre(token: str) -> bool:
    key = fold_diacritics(token).strip().lower()
    if key in GENRE_DENYLIST:
        return True
    return any(p.match(token.strip()) for p in GENRE_DENYLIST_PATTERNS)


def is_known_artist_name(conn: sqlite3.Connection, token: str) -> bool:
    """True if `token` matches an artist already known in the DB -- a strong
    signal that this "genre" tag is actually a copy-pasted artist name, not a
    real genre. Order-dependent (an artist not yet seen this run won't match
    yet), which is an accepted best-effort limitation."""
    row = conn.execute(
        "SELECT 1 FROM artists WHERE normalized_name = ?", (normalize_name(token),)
    ).fetchone()
    return row is not None


def genre_match_key(name: str) -> str:
    """Loose comparison key for genre deduplication: folds accents, case,
    AND separators (-, _, /) to spaces, so "trip-hop", "trip hop" and
    "Trip_Hop" are all recognized as the same genre."""
    key = fold_diacritics(name).lower()
    key = re.sub(r"[-_/]+", " ", key)
    return " ".join(key.split())


def parse_number_pair(value: str | None) -> tuple[int | None, int | None]:
    """Parses "3/12" -> (3, 12). Also handles "3" -> (3, None)."""
    if not value:
        return None, None
    value = str(value).strip()
    if "/" in value:
        num, _, total = value.partition("/")
    else:
        num, total = value, None
    try:
        num_i = int(num.strip()) if num.strip() else None
    except ValueError:
        num_i = None
    try:
        total_i = int(total.strip()) if total and total.strip() else None
    except ValueError:
        total_i = None
    return num_i, total_i


def extract_year(raw_date: str | None) -> int | None:
    if not raw_date:
        return None
    match = YEAR_RE.search(str(raw_date))
    return int(match.group(1)) if match else None


def compute_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_tag(tags, *keys):
    for key in keys:
        values = tags.get(key)
        if values:
            value = values[0] if isinstance(values, list) else values
            value = str(value).strip()
            if value:
                return value
    return None


def read_metadata(path: Path) -> dict:
    """Returns a metadata dict, with fallbacks for fields that are required
    in the DB even if tags are missing/unreadable. Text fields are passed
    through clean_name() to strip stray punctuation noise."""
    ext = path.suffix.lower()
    result = {
        "title": clean_name(path.stem) or path.stem,
        "artist_credit": None,
        "album_name": None,
        "albumartist": None,
        "genre": None,
        "raw_date": None,
        "track_number": None,
        "track_total": None,
        "disc_number": None,
        "disc_total": None,
        "duration": 0.0,
        "bitrate": None,
        "sample_rate": None,
        "format": ext.lstrip("."),
        "file_size": path.stat().st_size,
    }

    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None

    if audio is not None:
        if audio.info is not None:
            result["duration"] = float(getattr(audio.info, "length", 0.0) or 0.0)
            result["bitrate"] = getattr(audio.info, "bitrate", None)
            result["sample_rate"] = getattr(audio.info, "sample_rate", None)

        if audio.tags:
            tags = audio.tags
            result["title"] = clean_name(first_tag(tags, "title")) or result["title"]
            result["artist_credit"] = clean_name(first_tag(tags, "artist"))
            result["album_name"] = clean_name(first_tag(tags, "album"))
            result["albumartist"] = clean_name(first_tag(tags, "albumartist"))
            result["genre"] = first_tag(tags, "genre")  # split later, may contain ';'-joined values
            result["raw_date"] = first_tag(tags, "date", "originaldate", "year")
            result["track_number"], result["track_total"] = parse_number_pair(
                first_tag(tags, "tracknumber")
            )
            result["disc_number"], result["disc_total"] = parse_number_pair(
                first_tag(tags, "discnumber")
            )

    return result


# ---------------------------------------------------------------------------
# Last.fm lookups
# ---------------------------------------------------------------------------

def _lastfm_request(params: dict) -> dict | None:
    url = f"{LASTFM_API_URL}?{urlencode(params)}"
    try:
        with urlopen(url, timeout=5) as resp:
            return json.load(resp)
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        print(f"[WARN] Last.fm request failed ({params.get('method')}): {e}", file=sys.stderr)
        return None


def fetch_lastfm_album_tags(artist: str, album: str, api_key: str) -> list[str]:
    """Queries Last.fm's album.getTopTags and returns up to LASTFM_MAX_TAGS
    tag names whose popularity weight is >= LASTFM_MIN_TAG_WEIGHT.
    Returns [] on any network/parsing error or if nothing qualifies, so a
    Last.fm outage or an unmatched album never blocks ingestion.
    """
    data = _lastfm_request({
        "method": "album.gettoptags", "artist": artist, "album": album,
        "api_key": api_key, "format": "json",
    })
    if not data:
        return []

    tags = data.get("toptags", {}).get("tag", [])
    if isinstance(tags, dict):
        # Last.fm returns a single dict instead of a list when there's only one tag
        tags = [tags]

    result = []
    for tag in tags:
        try:
            weight = int(tag.get("count", 0))
        except (TypeError, ValueError):
            weight = 0
        name = (tag.get("name") or "").strip()
        if name and weight >= LASTFM_MIN_TAG_WEIGHT:
            result.append(name)
        if len(result) >= LASTFM_MAX_TAGS:
            break
    return result


def fetch_lastfm_album_date(artist: str, album: str, api_key: str) -> str | None:
    """Queries Last.fm's album.getInfo and returns a best-effort release date
    string if one can be found. Last.fm's release-date data is sparse and
    inconsistent across albums, so this is only a fallback for files that
    have no date tag at all -- returns None (not an error) when nothing
    usable is found.
    """
    data = _lastfm_request({
        "method": "album.getinfo", "artist": artist, "album": album,
        "api_key": api_key, "format": "json",
    })
    if not data:
        return None

    album_info = data.get("album", {})
    candidates = [
        album_info.get("releasedate"),
        (album_info.get("wiki") or {}).get("published"),
    ]
    for c in candidates:
        if c and YEAR_RE.search(c):
            return c.strip()
    return None


# ---------------------------------------------------------------------------
# Cover thumbnail extraction
# ---------------------------------------------------------------------------

def get_embedded_picture_bytes(path: Path) -> bytes | None:
    """Reads the embedded artwork straight from the file's raw tags (APIC for
    mp3, covr for m4a). Must be opened WITHOUT easy=True: the easy tag layer
    only exposes the mapped text fields, not picture frames."""
    ext = path.suffix.lower()
    try:
        audio = MutagenFile(path)
    except Exception:
        return None
    if audio is None or audio.tags is None:
        return None

    if ext == ".mp3":
        apics = audio.tags.getall("APIC") if hasattr(audio.tags, "getall") else []
        return bytes(apics[0].data) if apics else None
    elif ext == ".m4a":
        covers = audio.tags.get("covr")
        return bytes(covers[0]) if covers else None
    return None


def extract_cover_thumbnail(path: Path):
    """Extracts, downsizes and compresses the embedded artwork so it fits
    the DB's 100KB CHECK constraint. Returns
    (jpeg_bytes, mime_type, width, height, dominant_color_hex) or None if
    there's no embedded artwork, it can't be decoded, or Pillow isn't
    installed.
    """
    if not HAS_PIL:
        return None
    raw = get_embedded_picture_bytes(path)
    if not raw:
        return None
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None

    img.thumbnail((COVER_MAX_SIZE, COVER_MAX_SIZE))
    dominant = img.resize((1, 1)).getpixel((0, 0))
    dominant_hex = "#{:02x}{:02x}{:02x}".format(*dominant)

    quality = 85
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    while buf.tell() > COVER_MAX_BYTES and quality > 20:
        quality -= 10
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)

    if buf.tell() > COVER_MAX_BYTES:
        return None  # give up rather than violate the DB-level CHECK constraint

    return buf.getvalue(), "image/jpeg", img.width, img.height, dominant_hex


def ensure_cover_thumbnail(conn: sqlite3.Connection, album_id: int, path: Path, attempted: set[int]):
    """Extracts and stores a thumbnail for the album, at most once per run
    and only if the album doesn't already have one."""
    if album_id in attempted:
        return
    attempted.add(album_id)

    if conn.execute("SELECT 1 FROM covers_thumbnails WHERE album_id = ?", (album_id,)).fetchone():
        return

    result = extract_cover_thumbnail(path)
    if result is None:
        return
    thumb_bytes, mime, w, h, color = result
    conn.execute(
        "INSERT INTO covers_thumbnails (album_id, thumbnail, mime_type, width, height, dominant_color) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (album_id, thumb_bytes, mime, w, h, color),
    )


# ---------------------------------------------------------------------------
# Get-or-create helpers
# ---------------------------------------------------------------------------

def get_or_create_artist(conn: sqlite3.Connection, name: str) -> int:
    norm = normalize_name(name)
    row = conn.execute(
        "SELECT id FROM artists WHERE normalized_name = ?", (norm,)
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO artists (name, normalized_name) VALUES (?, ?)", (name, norm)
    )
    return cur.lastrowid


def get_or_create_album(
    conn: sqlite3.Connection, name: str, artist_id: int, raw_date: str | None, is_compilation: bool
) -> int:
    row = conn.execute(
        "SELECT id FROM albums WHERE name = ? AND artist_id = ?", (name, artist_id)
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO albums (name, year, raw_date, artist_id, is_compilation) VALUES (?, ?, ?, ?, ?)",
        (name, extract_year(raw_date), raw_date, artist_id, int(is_compilation)),
    )
    return cur.lastrowid


def get_or_create_genre(conn: sqlite3.Connection, name: str) -> int:
    # Case-, accent-, AND separator-insensitive lookup: "Rock"/"rock" and
    # "trip-hop"/"trip hop" all resolve to the same row instead of creating
    # near-duplicates. Genre counts are small (a few hundred at most) so an
    # in-Python scan is cheap and simpler than a SQL collation.
    key = genre_match_key(name)
    for gid, gname in conn.execute("SELECT id, name FROM genres"):
        if genre_match_key(gname) == key:
            return gid
    cur = conn.execute("INSERT INTO genres (name) VALUES (?)", (name.strip(),))
    return cur.lastrowid


def link_album_genre(conn: sqlite3.Connection, album_id: int, genre_id: int, source: str):
    conn.execute(
        "INSERT OR IGNORE INTO album_genres (album_id, genre_id, source) VALUES (?, ?, ?)",
        (album_id, genre_id, source),
    )


def album_has_genre(conn: sqlite3.Connection, album_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM album_genres WHERE album_id = ? LIMIT 1", (album_id,)
    ).fetchone()
    return row is not None


def album_year_is_missing(conn: sqlite3.Connection, album_id: int) -> bool:
    row = conn.execute("SELECT year FROM albums WHERE id = ?", (album_id,)).fetchone()
    return row is not None and row[0] is None


def set_song_artists(conn: sqlite3.Connection, song_id: int, artist_credit: str):
    conn.execute("DELETE FROM song_artists WHERE song_id = ?", (song_id,))
    names = split_artists(artist_credit) if artist_credit else [UNKNOWN_ARTIST]
    for position, name in enumerate(names):
        artist_id = get_or_create_artist(conn, name)
        role = "main" if position == 0 else "featured"
        conn.execute(
            "INSERT OR IGNORE INTO song_artists (song_id, artist_id, role, position) VALUES (?, ?, ?, ?)",
            (song_id, artist_id, role, position),
        )


# ---------------------------------------------------------------------------
# Ingesting a single file
# ---------------------------------------------------------------------------

def ingest_file(
    conn: sqlite3.Connection,
    path: Path,
    root: Path,
    rescan: bool,
    lastfm_api_key: str | None,
    lastfm_genre_attempted: set[int],
    lastfm_date_attempted: set[int],
    cover_attempted: set[int],
) -> str:
    """Returns 'new', 'updated', or 'unchanged'."""
    rel_path = str(path.relative_to(root))
    file_mtime = path.stat().st_mtime
    file_mtime_str = f"{file_mtime:.6f}"

    existing = conn.execute(
        "SELECT id, file_modified_at FROM songs WHERE path = ?", (rel_path,)
    ).fetchone()

    if existing and not rescan:
        existing_id, existing_mtime = existing
        if existing_mtime == file_mtime_str:
            return "unchanged"

    meta = read_metadata(path)

    artist_credit = resolve_artist_field(meta["artist_credit"])
    album_name = resolve_album_field(meta["album_name"])
    albumartist_name = resolve_artist_field(meta["albumartist"] or meta["artist_credit"])

    album_artist_id = get_or_create_artist(conn, albumartist_name)
    is_compilation = bool(
        meta["albumartist"] and meta["artist_credit"] and albumartist_name != artist_credit
    )
    album_id = get_or_create_album(conn, album_name, album_artist_id, meta["raw_date"], is_compilation)

    # Genres from the file's own tag (possibly ';'-joined, e.g. "Rock;Pop").
    # Tokens that look like noise (years, decades, artist names copy-pasted
    # into the genre field, known "meta" list-tags) are filtered out of the
    # genres table but not discarded: they're kept in extra_tags so nothing
    # is silently lost.
    genre_tag_id = None
    rejected_genre_tags = []
    for genre_name in split_genres(meta["genre"]):
        if (
            is_year_or_decade(genre_name)
            or is_denylisted_genre(genre_name)
            or is_known_artist_name(conn, genre_name)
        ):
            rejected_genre_tags.append(genre_name)
            continue
        gid = get_or_create_genre(conn, genre_name)
        if genre_tag_id is None:
            genre_tag_id = gid
        link_album_genre(conn, album_id, gid, source="tag")

    extra_tags_json = json.dumps({"rejected_genre_tags": rejected_genre_tags}) if rejected_genre_tags else None

    is_real_album = albumartist_name != UNKNOWN_ARTIST and album_name != UNKNOWN_ALBUM

    # Last.fm genre fallback: only if the album still has no genre at all
    # (from any source), we haven't already tried it this run, and lookup
    # wasn't disabled. Persists across runs via album_genres, so a resolved
    # (or previously tag-tagged) album is never re-queried.
    if (
        lastfm_api_key
        and is_real_album
        and album_id not in lastfm_genre_attempted
        and not album_has_genre(conn, album_id)
    ):
        lastfm_genre_attempted.add(album_id)
        tags = fetch_lastfm_album_tags(albumartist_name, album_name, lastfm_api_key)
        time.sleep(LASTFM_REQUEST_DELAY)
        for tag_name in tags:
            gid = get_or_create_genre(conn, tag_name)
            link_album_genre(conn, album_id, gid, source="lastfm")

    # Last.fm release-date fallback: only if the file itself has no date tag
    # and the album's year is still unset. Persists via albums.year, so once
    # resolved it's never re-queried (unresolved albums are retried each run
    # -- acceptable trade-off, see ingest.py's docstring/README notes).
    if (
        lastfm_api_key
        and is_real_album
        and meta["raw_date"] is None
        and album_id not in lastfm_date_attempted
        and album_year_is_missing(conn, album_id)
    ):
        lastfm_date_attempted.add(album_id)
        found_date = fetch_lastfm_album_date(albumartist_name, album_name, lastfm_api_key)
        time.sleep(LASTFM_REQUEST_DELAY)
        if found_date:
            conn.execute(
                "UPDATE albums SET raw_date = ?, year = ? WHERE id = ?",
                (found_date, extract_year(found_date), album_id),
            )

    # Cover thumbnail: extracted once per album from whichever file we
    # happen to be processing when we first see that album.
    ensure_cover_thumbnail(conn, album_id, path, cover_attempted)

    content_hash = compute_hash(path)
    sort_title = make_sort_title(meta["title"])

    if existing:
        song_id = existing[0]
        conn.execute(
            """
            UPDATE songs SET
                title = ?, artist_credit = ?, album_id = ?,
                track_number = ?, track_total = ?, disc_number = ?, disc_total = ?,
                genre_tag_id = ?, duration = ?, format = ?, file_size = ?,
                bitrate = ?, sample_rate = ?, content_hash = ?,
                sort_title = ?, extra_tags = ?, file_modified_at = ?,
                imported_at = datetime('now')
            WHERE id = ?
            """,
            (
                meta["title"], artist_credit, album_id,
                meta["track_number"], meta["track_total"], meta["disc_number"], meta["disc_total"],
                genre_tag_id, meta["duration"], meta["format"], meta["file_size"],
                meta["bitrate"], meta["sample_rate"], content_hash,
                sort_title, extra_tags_json, file_mtime_str,
                song_id,
            ),
        )
        set_song_artists(conn, song_id, artist_credit)
        return "updated"
    else:
        cur = conn.execute(
            """
            INSERT INTO songs (
                path, title, artist_credit, album_id,
                track_number, track_total, disc_number, disc_total,
                genre_tag_id, duration, format, file_size,
                bitrate, sample_rate, content_hash, sort_title, extra_tags,
                file_modified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rel_path, meta["title"], artist_credit, album_id,
                meta["track_number"], meta["track_total"], meta["disc_number"], meta["disc_total"],
                genre_tag_id, meta["duration"], meta["format"], meta["file_size"],
                meta["bitrate"], meta["sample_rate"], content_hash, sort_title, extra_tags_json,
                file_mtime_str,
            ),
        )
        song_id = cur.lastrowid
        set_song_artists(conn, song_id, artist_credit)
        return "new"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def find_audio_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
            yield path


def process(root: Path, db_path: Path, rescan: bool, dry_run: bool, lastfm_api_key: str | None):
    if not HAS_PIL:
        print("[WARN] Pillow is not installed: cover thumbnails will not be extracted. "
              "Install with: pip install pillow", file=sys.stderr)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)

    counts = {"new": 0, "updated": 0, "unchanged": 0, "error": 0}
    lastfm_genre_attempted: set[int] = set()
    lastfm_date_attempted: set[int] = set()
    cover_attempted: set[int] = set()

    for path in find_audio_files(root):
        try:
            if dry_run:
                # in dry-run we don't write anything; just simulate the
                # new/unchanged detection in read-only mode
                rel_path = str(path.relative_to(root))
                row = conn.execute(
                    "SELECT file_modified_at FROM songs WHERE path = ?", (rel_path,)
                ).fetchone()
                mtime_str = f"{path.stat().st_mtime:.6f}"
                status = "unchanged" if row and row[0] == mtime_str and not rescan else "new/updated"
                print(f"[DRY-RUN] {status}: {path}")
                continue

            status = ingest_file(
                conn, path, root, rescan, lastfm_api_key,
                lastfm_genre_attempted, lastfm_date_attempted, cover_attempted,
            )
            counts[status] = counts.get(status, 0) + 1
            if status in ("new", "updated"):
                print(f"{status.upper()}: {path.relative_to(root)}")

        except Exception as e:
            counts["error"] += 1
            print(f"[ERROR] {path}: {e}", file=sys.stderr)

    if not dry_run:
        conn.commit()

    conn.close()

    print("\n--- Summary ---")
    for key in ("new", "updated", "unchanged", "error"):
        print(f"{key}: {counts.get(key, 0)}")


def main():
    parser = argparse.ArgumentParser(
        description="Ingests an audio library (mp3/m4a) into a SQLite database."
    )
    parser.add_argument("folder", type=Path, help="Root folder of the library to scan")
    parser.add_argument(
        "--db", type=Path, default=Path("music_library.db"), help="Path to the SQLite database"
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Force re-parsing of every file, even unchanged ones",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate ingestion without writing to the database",
    )
    parser.add_argument(
        "--lastfm-api-key",
        default=os.environ.get("LASTFM_API_KEY"),
        help="Last.fm API key, used to look up a genre and/or release date "
        "for albums missing them in their tags. Defaults to the "
        "LASTFM_API_KEY env var. Get a free key at "
        "https://www.last.fm/api/account/create",
    )
    parser.add_argument(
        "--no-lastfm",
        action="store_true",
        help="Disable Last.fm lookup entirely, even if an API key is set",
    )
    args = parser.parse_args()

    if not args.folder.is_dir():
        print(f"Error: folder '{args.folder}' does not exist.", file=sys.stderr)
        sys.exit(1)

    lastfm_api_key = None if args.no_lastfm else args.lastfm_api_key

    process(args.folder.resolve(), args.db, args.rescan, args.dry_run, lastfm_api_key)


if __name__ == "__main__":
    main()
