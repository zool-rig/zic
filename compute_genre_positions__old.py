#!/usr/bin/env python3
"""
compute_genre_positions.py

Computes a low-dimensional proximity vector for every genre in the database
and stores it in genres.position (JSON array of floats).

Unlike ingest.py, this is a standalone batch job, not something run per
file: it needs the *complete* current genre vocabulary to build a
meaningful similarity matrix, so it's meant to be re-run occasionally
(e.g. after a big library import, or every few weeks) rather than on every
ingest.

Two similarity sources are available:

  --source library (default, recommended)
      Builds similarity from your own collection: two genres that are
      frequently linked to the same albums (album_genres) are considered
      close. No external dependency, works fully offline, and only ever
      reflects genres that actually matter to your library.

  --source lastfm
      Uses Last.fm's tag.getSimilar, which returns related tags based on
      real listening data across all of Last.fm.
      NOTE: as of April 2026, this endpoint is confirmed broken on Last.fm's
      side (returns an empty list for every tag, regardless of the API key)
      -- see https://support.last.fm/t/tag-getsimilar-does-not-work/118230
      This mode is kept in case Last.fm fixes it, but --source library is
      the reliable option today.

Either way, the resulting n x n similarity matrix is turned into a distance
matrix (1 - similarity) and embedded into a low-dimensional space via
classical MDS (Principal Coordinates Analysis), where Euclidean distance
between two genre vectors approximates their proximity.

Dependencies:
    pip install numpy

Usage:
    python3 compute_genre_positions.py --db music_library.db
    python3 compute_genre_positions.py --db music_library.db --dimensions 12
    python3 compute_genre_positions.py --db music_library.db --dry-run
    python3 compute_genre_positions.py --db music_library.db --source lastfm --lastfm-api-key YOUR_KEY
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import unicodedata
from collections import defaultdict
from itertools import combinations
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_REQUEST_DELAY = 0.25  # seconds between calls, stays under Last.fm's ~5 req/s guideline

DEFAULT_DIMENSIONS = 8
DEFAULT_SIMILAR_LIMIT = 30  # how many similar tags to request per genre (lastfm mode only)


class LastfmAPIError(Exception):
    """Raised when Last.fm returns a valid JSON response that is actually an
    error envelope (e.g. invalid API key, rate limit exceeded). This is
    distinct from a network failure: the HTTP call succeeded, json.load()
    succeeded, but the payload is {"error": <code>, "message": <str>}
    instead of the expected data shape. Left unchecked, this silently looks
    like "no data found" for every single tag."""
    pass


def build_similarity_matrix_from_library(conn: sqlite3.Connection, genres: list[tuple[int, str]]) -> np.ndarray:
    """Builds similarity from co-occurrence within the user's own library:
    two genres that are frequently linked to the same album (album_genres)
    are considered close. Fully local, no external dependency.
    """
    n = len(genres)
    index_by_id = {genre_id: i for i, (genre_id, _) in enumerate(genres)}

    albums_genres: dict[int, set[int]] = defaultdict(set)
    for album_id, genre_id in conn.execute("SELECT album_id, genre_id FROM album_genres"):
        if genre_id in index_by_id:
            albums_genres[album_id].add(genre_id)

    co_occurrence = np.zeros((n, n))
    for genre_ids in albums_genres.values():
        for gi, gj in combinations(genre_ids, 2):
            i, j = index_by_id[gi], index_by_id[gj]
            co_occurrence[i, j] += 1
            co_occurrence[j, i] += 1

    max_count = co_occurrence.max()
    similarity = co_occurrence / max_count if max_count > 0 else co_occurrence
    np.fill_diagonal(similarity, 1.0)

    for i, (_, name) in enumerate(genres):
        linked = int(np.count_nonzero(co_occurrence[i]))
        print(f"  {name}: co-occurs with {linked} other genre(s) across the library")

    return similarity


# ---------------------------------------------------------------------------
# Last.fm similarity (see module docstring: currently broken on Last.fm's
# side as of April 2026, kept in case they fix it)
# ---------------------------------------------------------------------------

def fold_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_key(name: str) -> str:
    return fold_diacritics(name).strip().lower()


def fetch_lastfm_similar_tags(tag: str, api_key: str, limit: int) -> list[tuple[str, float]]:
    """Queries Last.fm's tag.getSimilar. Returns a list of (tag_name, match)
    where match is a similarity score in [0, 1]. Returns [] on any
    network/parsing error, so an outage or an unknown tag never blocks the
    whole computation."""
    params = {
        "method": "tag.getsimilar",
        "tag": tag,
        "api_key": api_key,
        "format": "json",
        "limit": str(limit),
    }
    url = f"{LASTFM_API_URL}?{urlencode(params)}"
    try:
        with urlopen(url, timeout=5) as resp:
            data = json.load(resp)
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        print(f"[WARN] Last.fm tag.getSimilar failed for '{tag}': {e}", file=sys.stderr)
        return []

    if isinstance(data, dict) and "error" in data:
        # A valid JSON response that is actually an API-level error (bad key,
        # rate limit, unrecognized method...). Must NOT be treated as "zero
        # similar tags" -- that would silently corrupt every single lookup.
        raise LastfmAPIError(f"Last.fm error {data.get('error')}: {data.get('message', 'unknown error')}")

    tags = data.get("similartags", {}).get("tag", [])
    if isinstance(tags, dict):
        tags = [tags]  # Last.fm returns a single dict instead of a list when there's only one match

    result = []
    for t in tags:
        name = (t.get("name") or "").strip()
        try:
            match = float(t.get("match", 0))
        except (TypeError, ValueError):
            match = 0.0
        if name:
            result.append((name, match))
    return result


def build_similarity_matrix(
    genres: list[tuple[int, str]], api_key: str, limit: int
) -> np.ndarray:
    """genres: list of (id, name), in the order that defines matrix indices.
    Returns an n x n symmetric similarity matrix, 1.0 on the diagonal."""
    n = len(genres)
    index_by_key = {normalize_key(name): i for i, (_, name) in enumerate(genres)}
    S = np.eye(n)

    for i, (_, name) in enumerate(genres):
        similar = fetch_lastfm_similar_tags(name, api_key, limit)
        time.sleep(LASTFM_REQUEST_DELAY)

        for sim_name, match in similar:
            j = index_by_key.get(normalize_key(sim_name))
            if j is None or j == i:
                continue  # tag not in our vocabulary, or self-match: skip
            S[i, j] = max(S[i, j], match)
            S[j, i] = max(S[j, i], match)

        print(f"  {name}: {len(similar)} related tags from Last.fm, "
              f"{sum(1 for sim_name, _ in similar if normalize_key(sim_name) in index_by_key)} matched our vocabulary")

    return S


def classical_mds(distances: np.ndarray, dimensions: int) -> np.ndarray:
    """Classical multidimensional scaling (Principal Coordinates Analysis).
    Embeds n points, given only their pairwise distances, into a
    `dimensions`-dimensional Euclidean space that best preserves those
    distances. Pure numpy, no scikit-learn dependency.
    """
    n = distances.shape[0]
    dimensions = min(dimensions, max(n - 1, 1))

    d2 = distances ** 2
    j = np.eye(n) - np.ones((n, n)) / n
    b = -0.5 * j @ d2 @ j  # double-centered inner-product matrix

    eigvals, eigvecs = np.linalg.eigh(b)  # b is symmetric
    order = np.argsort(eigvals)[::-1][:dimensions]
    top_vals = np.clip(eigvals[order], 0, None)  # negative eigenvalues -> 0 (noise in the input distances)

    return eigvecs[:, order] @ np.diag(np.sqrt(top_vals))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process(db_path, source: str, api_key: str | None, dimensions: int, similar_limit: int, dry_run: bool):
    conn = sqlite3.connect(db_path)
    genres = conn.execute("SELECT id, name FROM genres ORDER BY id").fetchall()

    if not genres:
        print("No genres in the database, nothing to do.")
        conn.close()
        return

    if len(genres) < 2:
        print("Only one genre in the database: positions would be meaningless (nothing to be "
              "close to or far from). Skipping.")
        conn.close()
        return

    if source == "lastfm":
        print(
            "[WARN] --source lastfm relies on tag.getSimilar, which is confirmed broken on "
            "Last.fm's side as of April 2026 (empty results for every tag). --source library "
            "is the reliable default; proceeding anyway since it was explicitly requested.\n",
            file=sys.stderr,
        )
        # Fail fast and clearly rather than burning through every genre with a
        # broken API key and silently getting zero results for all of them.
        print("Checking Last.fm API access...")
        try:
            fetch_lastfm_similar_tags(genres[0][1], api_key, 1)
        except LastfmAPIError as e:
            print(f"\n[ERROR] {e}", file=sys.stderr)
            print(
                "\nThe Last.fm API call itself failed (this is not a network issue).\n"
                "Most likely causes:\n"
                "  - the API key is invalid, was mistyped, or hasn't been activated\n"
                "  - the key's request quota has been exceeded\n"
                "Get/check a key at: https://www.last.fm/api/account/create",
                file=sys.stderr,
            )
            conn.close()
            sys.exit(1)
        print("OK.\n")

        print(f"Computing positions for {len(genres)} genres...\n")
        similarity = build_similarity_matrix(genres, api_key, similar_limit)
    else:
        print(f"Computing positions for {len(genres)} genres from library co-occurrence...\n")
        similarity = build_similarity_matrix_from_library(conn, genres)

    distance = 1.0 - similarity
    np.fill_diagonal(distance, 0.0)

    coords = classical_mds(distance, dimensions)

    print(f"\nEmbedded into {coords.shape[1]} dimensions.")

    if dry_run:
        print("\n[DRY-RUN] Positions computed but not written to the database:")
        for (genre_id, name), vec in zip(genres, coords):
            rounded = [round(float(x), 4) for x in vec]
            print(f"  {name}: {rounded}")
        conn.close()
        return

    for (genre_id, name), vec in zip(genres, coords):
        position_json = json.dumps([round(float(x), 6) for x in vec])
        conn.execute("UPDATE genres SET position = ? WHERE id = ?", (position_json, genre_id))

    conn.commit()
    conn.close()
    print(f"\nDone: {len(genres)} genre positions updated.")


def main():
    parser = argparse.ArgumentParser(
        description="Computes proximity vectors for all genres in the DB."
    )
    parser.add_argument("--db", required=True, help="Path to the SQLite database")
    parser.add_argument(
        "--source", choices=["library", "lastfm"], default="library",
        help="Similarity source. 'library' (default) uses co-occurrence in your own "
        "collection, fully offline. 'lastfm' uses tag.getSimilar, currently broken on "
        "Last.fm's side as of April 2026 -- see the module docstring.",
    )
    parser.add_argument(
        "--lastfm-api-key",
        default=os.environ.get("LASTFM_API_KEY"),
        help="Last.fm API key, required only for --source lastfm. Defaults to the "
        "LASTFM_API_KEY env var. Get a free key at https://www.last.fm/api/account/create",
    )
    parser.add_argument(
        "--dimensions", type=int, default=DEFAULT_DIMENSIONS,
        help=f"Size of the output vector (default: {DEFAULT_DIMENSIONS})",
    )
    parser.add_argument(
        "--similar-limit", type=int, default=DEFAULT_SIMILAR_LIMIT,
        help=f"Number of similar tags to request per genre from Last.fm, --source lastfm only "
        f"(default: {DEFAULT_SIMILAR_LIMIT})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute and print the positions without writing them to the database",
    )
    args = parser.parse_args()

    if args.source == "lastfm" and not args.lastfm_api_key:
        print("Error: --source lastfm requires an API key (--lastfm-api-key or LASTFM_API_KEY env var).",
              file=sys.stderr)
        sys.exit(1)

    process(args.db, args.source, args.lastfm_api_key, args.dimensions, args.similar_limit, args.dry_run)


if __name__ == "__main__":
    main()