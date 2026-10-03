import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from mutagen import File as MutagenFile
from mutagen import MutagenError, Tags
from PIL import Image
from secret_type.typing.types import StringLike

from zic.ingestor.discogs_secret import DiscogsSecret, InvalidDiscogsSecrets
from zic.ingestor.progress import IngestProgress, JsonIngestProgress
from zic.logging import get_logger
from zic.utils.text import fold_diacritics

SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"

AUDIO_EXTENSIONS = {".mp3", ".m4a"}

# Strips stray leading/trailing punctuation and whitespace noise sometimes
# left by ripping tools, e.g. ". High tone        " -> "High tone".
NOISE_RE = re.compile(r"^[\s.\-_/,;:]+|[\s.\-_/,;:]+$")

UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"

# Tag values that mean "no real artist/album", seen in the wild from various
# ripping/tagging tools. Case- and accent-insensitive match, folded to the
# canonical Unknown fallback so they don't create near-duplicate placeholder
# rows in the DB.
ARTIST_PLACEHOLDER_TOKENS = {
    "unknown",
    "unknown artist",
    "various",
    "various artists",
    "inconnu",
    "artiste inconnu",
    "n/a",
    "na",
    "none",
    "no artist",
}
ALBUM_PLACEHOLDER_TOKENS = {
    "unknown",
    "unknown album",
    "inconnu",
    "album inconnu",
    "n/a",
    "na",
    "none",
    "no album",
}

YEAR_RE = re.compile(r"(\d{4})")
# Pure year or decade tokens ("2015", "90s", "2010s") sometimes leak into the
# genre field from scrobble-based taggers -- not actual musical genres.
YEAR_OR_DECADE_RE = re.compile(r"^(?:\d{4}|\d{2}s|\d{4}s)$")

# Separators between several genres in a single tag ("Rock; Pop",
# "Funk / Soul", "Rap & Hip-Hop", "Soul and R&B"...).
GENRE_SPLIT_RE = re.compile(r"\s*(?:[;,/&+|]|\band\b)\s*")
# Genre names that contain a separator but must stay whole. Matched
# case-insensitively, after "_" has been turned into spaces.
GENRE_PROTECTED = [
    "r&b",
    "r & b",
    "r'n'b",
    "rnb",
    "r and b",
    "rhythm & blues",
    "rhythm and blues",
    "rock & roll",
    "rock and roll",
    "rock 'n' roll",
    "rock'n'roll",
    "drum & bass",
    "drum and bass",
    "drum'n'bass",
    "d&b",
    "stage & screen",  # Discogs category (soundtracks, musicals...)
    "brass & military",  # Discogs category
]
GENRE_PROTECTED_RE = re.compile(
    r"(?<!\w)(?:"
    + "|".join(re.escape(g) for g in sorted(GENRE_PROTECTED, key=len, reverse=True))
    + r")(?!\w)"
)
# Tokens that don't split into genres on their own: "hip_hop_rap" (a
# flattened "Hip-Hop/Rap") would otherwise stay a single unknown genre.
GENRE_ALIASES = {
    "hip hop rap": {"hip hop", "rap"},
}
# Personal/list-style tags that occasionally end up in the genre field
# (e.g. via tools that copy a user's Last.fm tag cloud into ID3/MP4 tags),
# not actual musical genres. Necessarily incomplete: catches known recurring
# junk, not every possible arbitrary tag (see ingest.py's docstring).
GENRE_DENYLIST = {
    "wishlist",
    "vinyl",
    "favourite albums",
    "favorite albums",
    "albums",
    "albums i have listened",
    "compilation",
    "long",
    "joy",
    "fun",
    "wikipedia",
    "masterpiece",
    "remix",
    "chill",
}
GENRE_DENYLIST_PATTERNS = [
    re.compile(r"^best of \d{4}$", re.IGNORECASE),
    re.compile(r"^\d+ albums.*before you die$", re.IGNORECASE),
]

DISCOGS_MIN_REQUEST_INTERVAL = 1.1
DISCOGS_RATE_LIMIT_WAIT_SECONDS = 60.0
DISCOGS_MAX_ATTEMPTS = 2
_last_discogs_request_at = 0.0

COVER_MAX_SIZE = 200  # px, longest side
COVER_MAX_BYTES = 100 * 1024  # must stay under the DB's CHECK constraint

LEADING_ARTICLE_RE = re.compile(r"^(the|a|an|le|la|les|un|une|des)\s+", re.IGNORECASE)

# Heuristic separators used to split a composite artist_credit into several
# artists ("A feat. B", "A & B", "A, B"...). Best-effort: on atypical
# composite tags (long classical-music credits, etc.) the split can be
# imperfect. The raw artist_credit is always kept (after noise-stripping via
# clean_name) in the DB regardless, so nothing meaningful is ever lost.
ARTIST_SPLIT_RE = re.compile(r"\s*(?:,|;|/|&|\bfeat\.?\b|\bft\.?\b)\s*", re.IGNORECASE)

FILES_PER_COMMIT = 10

LOGGER = get_logger("Ingest")


# ---------------------------------------------------------------------------
# DB initialization
# ---------------------------------------------------------------------------


def init_db(conn: sqlite3.Connection) -> None:
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='songs'"
    ).fetchone()
    if existing:
        return
    if not SCHEMA_PATH.exists():
        LOGGER.error(f"schema.sql not found next to the script ({SCHEMA_PATH})")
        sys.exit(1)
    conn.executescript(SCHEMA_PATH.read_text())
    LOGGER.info("Database initialized (new file).")


# ---------------------------------------------------------------------------
# Normalization / parsing
# ---------------------------------------------------------------------------


def clean_name(name: str | None) -> str | None:
    """Strips stray leading/trailing punctuation/whitespace noise and
    collapses internal whitespace. Returns None if nothing meaningful is left."""
    if not name:
        return None
    cleaned = NOISE_RE.sub("", name)
    cleaned = " ".join(cleaned.split())
    return cleaned or None


def first_tag(tags: Tags, *keys: str) -> Any:
    for key in keys:
        values = tags.get(key)
        if values:
            value = values[0] if isinstance(values, list) else values
            value = str(value).strip()
            if value:
                return value
    return None


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


def normalize_name(name: str) -> str:
    """Comparison key used for artists.normalized_name: case- and
    accent-insensitive, whitespace-collapsed."""
    name = fold_diacritics(name)
    return " ".join(name.split()).strip().lower()


def extract_year(raw_date: str | None) -> int | None:
    if not raw_date:
        return None
    match = YEAR_RE.search(str(raw_date))
    return int(match.group(1)) if match else None


def split_genres(raw: str | None) -> set[str]:
    """Splits a raw genre tag into lowercased genre names, keeping names
    that contain a separator whole ("R&B", "Drum & Bass"...)."""
    if not raw:
        return set()
    text = raw.lower().replace("_", " ")

    # Swap protected names for placeholders so the split leaves them alone.
    protected: list[str] = []

    def protect(match: re.Match) -> str:
        protected.append(match.group(0))
        return f"\x00{len(protected) - 1}\x00"

    text = GENRE_PROTECTED_RE.sub(protect, text)

    genres: set[str] = set()
    for part in GENRE_SPLIT_RE.split(text):
        part = re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], part)
        part = clean_name(part)
        if part:
            genres.update(GENRE_ALIASES.get(part, {part}))
    return genres


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
    key = re.sub(r"[-_]+", " ", key)
    return " ".join(key.split())


def make_sort_title(title: str) -> str:
    return LEADING_ARTICLE_RE.sub("", title).strip().lower()


def split_artists(artist_credit: str) -> list[str]:
    parts = [clean_name(p) for p in ARTIST_SPLIT_RE.split(artist_credit)]
    parts = [p for p in parts if p]
    return parts or [artist_credit.strip()]


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def read_metadata(path: Path) -> dict[str, Any]:
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
    except MutagenError:
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
            result["genre"] = first_tag(
                tags, "genre"
            )  # split later, may contain ';'-joined values
            result["raw_date"] = first_tag(tags, "date", "originaldate", "year")
            result["track_number"], result["track_total"] = parse_number_pair(
                first_tag(tags, "tracknumber")
            )
            result["disc_number"], result["disc_total"] = parse_number_pair(
                first_tag(tags, "discnumber")
            )

    return result


def empty_album_discogs_data() -> dict[str, Any]:
    return {
        "cover_url": None,
        "genres": set(),
        "year": None,
    }


def wait_for_discogs_slot() -> None:
    global _last_discogs_request_at

    elapsed = time.monotonic() - _last_discogs_request_at
    if elapsed < DISCOGS_MIN_REQUEST_INTERVAL:
        time.sleep(DISCOGS_MIN_REQUEST_INTERVAL - elapsed)
    _last_discogs_request_at = time.monotonic()


def discogs_retry_wait(response: requests.Response) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), DISCOGS_MIN_REQUEST_INTERVAL)
        except ValueError:
            pass
    return DISCOGS_RATE_LIMIT_WAIT_SECONDS


def get_album_discogs_data(
    album_name: str, artist_name: str, key: StringLike, token: StringLike
) -> dict[str, Any]:
    if album_name == UNKNOWN_ALBUM or artist_name == UNKNOWN_ARTIST:
        return empty_album_discogs_data()

    with (
        key.dangerous_reveal() as discogs_key,
        token.dangerous_reveal() as discogs_token,
    ):
        authorization = f"Discogs key={discogs_key}, secret={discogs_token}"

    for attempt in range(DISCOGS_MAX_ATTEMPTS):
        wait_for_discogs_slot()
        response = requests.get(
            "https://api.discogs.com/database/search",
            params={
                "query": album_name,
                "type": "release",
                "artist": artist_name,
            },
            headers={
                "Authorization": authorization,
                "Content-Type": "application/json",
                "User-Agent": "zic-ingestor",
            },
        )
        if response.status_code != 429 or attempt == DISCOGS_MAX_ATTEMPTS - 1:
            break
        wait_seconds = discogs_retry_wait(response)
        LOGGER.warning(
            "Discogs rate limit reached; waiting %.1f seconds before retrying.",
            wait_seconds,
        )
        time.sleep(wait_seconds)

    if not response.ok:
        if response.status_code == 401:
            raise InvalidDiscogsSecrets()
        else:
            response.raise_for_status()
    response_data = response.json()
    result = empty_album_discogs_data()

    for r in response_data["results"]:
        if "cover_image" in r and not result["cover_url"]:
            if r["cover_image"]:
                result["cover_url"] = r["cover_image"]
            elif r.get("master_url"):
                master_response = requests.get(
                    r["master_url"],
                    headers={
                        "Authorization": authorization,
                        "Content-Type": "application/json",
                        "User-Agent": "zic-ingestor",
                    },
                )
                response.raise_for_status()
                master_data = master_response.json()
                if master_data.get("images"):
                    for image_data in master_data["images"]:
                        if image_data.get("type") == "primary" and "uri" in image_data:
                            result["cover_url"] = image_data["uri"]
                            break

        if "year" in r and not result["year"]:
            result["year"] = r["year"]
        if "genre" in r:
            # Discogs categories can be compound ("Funk / Soul",
            # "Folk, World, & Country"): split them like file tags.
            for genre in r["genre"]:
                result["genres"].update(split_genres(genre))
        # if "style" in r:
        #     result["genres"].update(g.strip().lower() for g in r["style"])

    return result


def compute_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def set_metadata(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO metadata (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()


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
    LOGGER.info(f"Artist created : {name}")
    return cur.lastrowid


def get_or_create_album(
    conn: sqlite3.Connection,
    name: str,
    artist_id: int,
    raw_date: str | None,
    is_compilation: bool,
) -> int:
    norm = normalize_name(name)
    row = conn.execute(
        "SELECT id FROM albums WHERE normalized_name = ? AND artist_id = ?",
        (norm, artist_id),
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO albums (name, year, raw_date, artist_id, is_compilation, normalized_name) VALUES (?, ?, ?, ?, ?, ?)",
        (name, extract_year(raw_date), raw_date, artist_id, int(is_compilation), norm),
    )
    LOGGER.info(f"Album created : {name}")
    return cur.lastrowid


def get_or_create_genre(
    conn: sqlite3.Connection, name: str, genres_name_id_map: dict[str, int]
) -> int:
    # Case-, accent-, AND separator-insensitive lookup: "Rock"/"rock" and
    # "trip-hop"/"trip hop" all resolve to the same row instead of creating
    # near-duplicates. Genre counts are small (a few hundred at most) so an
    # in-Python scan is cheap and simpler than a SQL collation.
    key = genre_match_key(name)

    if key in genres_name_id_map:
        return genres_name_id_map[key]

    cur = conn.execute("INSERT INTO genres (name) VALUES (?)", (name.strip(),))
    new_id = cur.lastrowid
    genres_name_id_map[key] = new_id
    LOGGER.info(f"Genre created : {name}")
    return cur.lastrowid


def link_album_genre(conn: sqlite3.Connection, album_id: int, genre_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO album_genres (album_id, genre_id) VALUES (?, ?)",
        (album_id, genre_id),
    )


def set_song_artists(
    conn: sqlite3.Connection, song_id: int, artist_credit: str
) -> None:
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
# Cover thumbnail extraction
# ---------------------------------------------------------------------------


def get_embedded_picture_bytes(path: Path) -> bytes | None:
    """Reads the embedded artwork straight from the file's raw tags (APIC for
    mp3, covr for m4a). Must be opened WITHOUT easy=True: the easy tag layer
    only exposes the mapped text fields, not picture frames."""
    ext = path.suffix.lower()
    try:
        audio = MutagenFile(path)
    except Exception:  # noqa BLE001
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


def get_picture_url_content(url: str, key: StringLike, token: StringLike) -> bytes:
    with (
        key.dangerous_reveal() as discogs_key,
        token.dangerous_reveal() as discogs_token,
    ):
        authorization = f"Discogs key={discogs_key}, secret={discogs_token}"

    response = requests.get(
        url, headers={"Authorization": authorization, "User-Agent": "zic-ingestor"}
    )
    response.raise_for_status()
    return response.content


def extract_cover_thumbnail(
    path: Path | str, key: StringLike, token: StringLike
) -> tuple[bytes, str, int, int, str] | None:
    """Extracts, downsizes and compresses the embedded artwork so it fits
    the DB's 100KB CHECK constraint. Returns
    (jpeg_bytes, mime_type, width, height, dominant_color_hex) or None if
    there's no embedded artwork, it can't be decoded, or Pillow isn't
    installed.
    """
    if os.path.exists(path):
        raw = get_embedded_picture_bytes(path)
    elif path.startswith("http"):
        raw = get_picture_url_content(path, key, token)
    else:
        return None
    if not raw:
        return None
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:  # noqa BLE001
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


def ensure_cover_thumbnail(
    conn: sqlite3.Connection,
    album_id: int,
    path: Path,
    cover_url: str | None,
    key: StringLike,
    token: StringLike,
):
    """Extracts and stores a thumbnail for the album, at most once per run
    and only if the album doesn't already have one."""

    if conn.execute(
        "SELECT 1 FROM covers_thumbnails WHERE album_id = ?", (album_id,)
    ).fetchone():
        return

    result = extract_cover_thumbnail(path, key, token)
    if result is None:
        if cover_url:
            result = extract_cover_thumbnail(cover_url, key, token)
        else:
            return
    thumb_bytes, mime, w, h, color = result
    conn.execute(
        "INSERT INTO covers_thumbnails (album_id, thumbnail, mime_type, width, height, dominant_color) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (album_id, thumb_bytes, mime, w, h, color),
    )


# ---------------------------------------------------------------------------
# Ingesting a single file
# ---------------------------------------------------------------------------


def ingest_file(
    conn: sqlite3.Connection,
    path: Path,
    root: Path,
    rescan: bool,
    discogs_secret: DiscogsSecret,
    cover_attempted: set[int],
    discogs_albums_data: dict[int, dict[str, Any]],
    genres_name_id_map: dict[str, int],
    genres_reset: set[int],
) -> str:
    rel_path = str(path.relative_to(root))
    file_mtime = path.stat().st_mtime
    file_mtime_str = f"{file_mtime:.6f}"

    existing = conn.execute(
        "SELECT id, file_modified_at FROM songs WHERE path = ?", (rel_path,)
    ).fetchone()

    if existing and not rescan:
        _, existing_mtime = existing
        if existing_mtime == file_mtime_str:
            return "unchanged"

    meta = read_metadata(path)
    if meta["duration"] == 0.0 and meta["file_size"] == 0:
        LOGGER.warning(
            f"Can't read : {path.relative_to(root)}, maybe it is corrupted or empty"
        )
        return "skipped"

    artist_credit = resolve_artist_field(meta["artist_credit"])
    album_name = resolve_album_field(meta["album_name"])
    albumartist_name = resolve_artist_field(
        meta["albumartist"] or meta["artist_credit"]
    )

    album_artist_id = get_or_create_artist(conn, albumartist_name)

    if album_artist_id not in discogs_albums_data:
        try:
            album_discogs_data = get_album_discogs_data(
                album_name, albumartist_name, discogs_secret.key, discogs_secret.token
            )
        except requests.ConnectionError:
            LOGGER.warning("Can't connect to Discogs API.")
            album_discogs_data = empty_album_discogs_data()
        discogs_albums_data[album_artist_id] = album_discogs_data
    else:
        album_discogs_data = discogs_albums_data[album_artist_id]

    is_compilation = bool(
        meta["albumartist"]
        and meta["artist_credit"]
        and albumartist_name != artist_credit
    )
    year = meta["raw_date"] or (album_discogs_data["year"])
    album_id = get_or_create_album(
        conn, album_name, album_artist_id, year, is_compilation
    )

    if rescan and album_id not in genres_reset:
        # Drop stale genre links from a previous scan so re-tagging (or
        # a change in the ingestor's parsing rules) doesn't leave orphaned
        # associations behind. Safe: every song of this album still to be
        # processed in this run will re-add its own genres below.
        conn.execute("DELETE FROM album_genres WHERE album_id = ?", (album_id,))
        genres_reset.add(album_id)

    # album_genres is the single source of truth for genres: every genre
    # found for this file (Discogs + tag) is linked to its album. Copy the
    # Discogs set so the file's own tags don't leak into the shared cache.
    genres = set(album_discogs_data["genres"])
    genres.update(split_genres(meta["genre"]))
    rejected_genre_tags = []
    for genre_name in genres:
        if (
            is_year_or_decade(genre_name)
            or is_denylisted_genre(genre_name)
            or is_known_artist_name(conn, genre_name)
        ):
            rejected_genre_tags.append(genre_name)
            continue
        gid = get_or_create_genre(conn, genre_name, genres_name_id_map)
        link_album_genre(conn, album_id, gid)

    extra_tags_json = (
        json.dumps({"rejected_genre_tags": rejected_genre_tags})
        if rejected_genre_tags
        else None
    )

    if album_id not in cover_attempted:
        # Cover thumbnail: extracted once per album from whichever file we
        # happen to be processing when we first see that album.
        ensure_cover_thumbnail(
            conn,
            album_id,
            path,
            album_discogs_data["cover_url"],
            discogs_secret.key,
            discogs_secret.token,
        )
        cover_attempted.add(album_id)

    content_hash = compute_hash(path)

    sort_title = make_sort_title(meta["title"])

    song_id = existing[0] if existing else None
    status = "updated"
    if song_id is None:
        same_content = conn.execute(
            "SELECT id, path FROM songs WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        if same_content and (root / same_content[1]).exists():
            LOGGER.warning(
                f"{rel_path} has the same content as {same_content[1]}, skipped"
            )
            return "skipped"
        if same_content:
            # Its file is gone: the same file was moved or renamed. Keep the
            # song (plays, likes...) and point it to the new location.
            song_id, status = same_content[0], "moved"
            LOGGER.info(f"Song moved : '{same_content[1]}' -> '{rel_path}'")

    if song_id is not None:
        conn.execute(
            """
            UPDATE songs SET
                path = ?, title = ?, artist_credit = ?, album_id = ?,
                track_number = ?, track_total = ?, disc_number = ?, disc_total = ?,
                duration = ?, format = ?, file_size = ?,
                bitrate = ?, sample_rate = ?, content_hash = ?,
                sort_title = ?, extra_tags = ?, file_modified_at = ?,
                imported_at = datetime('now')
            WHERE id = ?
            """,
            (
                rel_path,
                meta["title"],
                artist_credit,
                album_id,
                meta["track_number"],
                meta["track_total"],
                meta["disc_number"],
                meta["disc_total"],
                meta["duration"],
                meta["format"],
                meta["file_size"],
                meta["bitrate"],
                meta["sample_rate"],
                content_hash,
                sort_title,
                extra_tags_json,
                file_mtime_str,
                song_id,
            ),
        )
        set_song_artists(conn, song_id, artist_credit)
        return status
    else:
        cur = conn.execute(
            """
            INSERT INTO songs (
                path, title, artist_credit, album_id,
                track_number, track_total, disc_number, disc_total,
                duration, format, file_size,
                bitrate, sample_rate, content_hash, sort_title, extra_tags,
                file_modified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rel_path,
                meta["title"],
                artist_credit,
                album_id,
                meta["track_number"],
                meta["track_total"],
                meta["disc_number"],
                meta["disc_total"],
                meta["duration"],
                meta["format"],
                meta["file_size"],
                meta["bitrate"],
                meta["sample_rate"],
                content_hash,
                sort_title,
                extra_tags_json,
                file_mtime_str,
            ),
        )
        song_id = cur.lastrowid
        set_song_artists(conn, song_id, artist_credit)
        return "created"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def remove_missing_songs(
    conn: sqlite3.Connection, root: Path, scanned_paths: set[str]
) -> int:
    """Removes the songs whose file is gone (deleted, or moved and changed
    on the way: unchanged moved files were already relocated by their
    content hash). Their plays go with them."""
    missing = [
        (song_id, rel_path)
        for song_id, rel_path in conn.execute("SELECT id, path FROM songs")
        if rel_path not in scanned_paths and not (root / rel_path).exists()
    ]
    for song_id, rel_path in missing:
        conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))
        LOGGER.info(f"Song removed (file not found) : '{rel_path}'")
    if missing:
        LOGGER.info(f"Missing songs removed : {len(missing)}")
    return len(missing)


def remove_orphans(conn: sqlite3.Connection) -> None:
    """Albums without songs left (moved, removed, or regrouped under their
    right artist), then the genres and artists nothing refers to anymore:
    they would still show up in the explorer and the filters."""
    for label, query in (
        ("albums", "DELETE FROM albums WHERE id NOT IN (SELECT album_id FROM songs)"),
        (
            "genres",
            "DELETE FROM genres WHERE id NOT IN (SELECT genre_id FROM album_genres)",
        ),
        (
            "artists",
            (
                "DELETE FROM artists WHERE id NOT IN (SELECT artist_id FROM albums) "
                "AND id NOT IN (SELECT artist_id FROM song_artists)"
            ),
        ),
    ):
        cur = conn.execute(query)
        if cur.rowcount:
            LOGGER.info(f"Unused {label} removed : {cur.rowcount}")


def find_audio_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
            yield path


def ingest(
    root: Path,
    db_path: Path,
    rescan: bool,
    discogs_key: str | None = None,
    discogs_token: str | None = None,
    json_progress: bool = False,
) -> None:
    discogs_secret = DiscogsSecret.from_env()
    if discogs_key is not None:
        discogs_secret.key = discogs_key
    if discogs_token is not None:
        discogs_secret.token = discogs_token

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        init_db(conn)

        cover_attempted: set[int] = set()
        genres_reset: set[int] = set()
        discogs_albums_data: dict[int, dict[str, Any]] = {}
        files_to_commit = 0

        genres_name_id_map = {
            genre_match_key(gname): id_
            for id_, gname in conn.execute("SELECT id, name FROM genres")
        }

        # Listed upfront to know the total; sorted so that each album's
        # files are processed (and logged) together.
        paths = sorted(find_audio_files(root))

        progress = (
            JsonIngestProgress(root, len(paths), LOGGER)
            if json_progress
            else IngestProgress(root, db_path, rescan, len(paths), LOGGER)
        )
        with progress:
            for path in paths:
                progress.start_file(path)
                files_to_commit += 1
                try:
                    status = ingest_file(
                        conn,
                        path,
                        root,
                        rescan,
                        discogs_secret,
                        cover_attempted,
                        discogs_albums_data,
                        genres_name_id_map,
                        genres_reset,
                    )
                    # Unchanged files are the bulk of an incremental scan, and
                    # skipped ones already logged why: the counters suffice.
                    log = LOGGER.info if status in ("created", "updated") else LOGGER.debug
                    log(f"Song {status} : '{path.relative_to(root)}'")
                except Exception as e:  # noqa BLE001
                    status = "error"
                    LOGGER.error(f"Failed to ingest '{path.relative_to(root)}': {e!r}")
                progress.finish_file(status)

                if files_to_commit == FILES_PER_COMMIT:
                    conn.commit()
                    files_to_commit = 0

            if paths:
                remove_missing_songs(conn, root, {str(p.relative_to(root)) for p in paths})
            else:
                # Most likely an unmounted drive or a wrong folder, rather
                # than a library emptied on purpose: keep everything.
                LOGGER.warning(
                    f"No audio file found in {root}: missing songs are kept."
                )
            remove_orphans(conn)

            set_metadata(conn, "last_ingest", datetime.now(UTC).isoformat())
