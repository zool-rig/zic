import json
import sqlite3
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np

from zic.logging import get_logger

DEFAULT_DIMENSIONS = 8
LOGGER = get_logger("Genre Pos")


def build_similarity_matrix(
    conn: sqlite3.Connection, genres: list[tuple[int, str]]
) -> np.ndarray:
    """Builds similarity from co-occurrence within the user's own library:
    two genres that are frequently linked to the same album (album_genres)
    are considered close. Fully local, no external dependency.
    """
    n = len(genres)
    index_by_id = {genre_id: i for i, (genre_id, _) in enumerate(genres)}
    genre_name_by_id = {genre_id: name for genre_id, name in genres}

    albums_genres: dict[int, set[int]] = defaultdict(set)
    for album_id, genre_id in conn.execute(
        "SELECT album_id, genre_id FROM album_genres"
    ):
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
        LOGGER.info(
            f"{name}: co-occurs with {linked} other genre(s) across the library"
        )

    return similarity


def classical_mds(distances: np.ndarray, dimensions: int) -> np.ndarray:
    """Classical multidimensional scaling (Principal Coordinates Analysis).
    Embeds n points, given only their pairwise distances, into a
    `dimensions`-dimensional Euclidean space that best preserves those
    distances. Pure numpy, no scikit-learn dependency.
    """
    n = distances.shape[0]
    dimensions = min(dimensions, max(n - 1, 1))

    d2 = distances**2
    j = np.eye(n) - np.ones((n, n)) / n
    b = -0.5 * j @ d2 @ j  # double-centered inner-product matrix

    eigvals, eigvecs = np.linalg.eigh(b)  # b is symmetric
    order = np.argsort(eigvals)[::-1][:dimensions]
    top_vals = np.clip(
        eigvals[order], 0, None
    )  # negative eigenvalues -> 0 (noise in the input distances)

    return eigvecs[:, order] @ np.diag(np.sqrt(top_vals))


def compute_genres_positions(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        genres = conn.execute("SELECT id, name FROM genres ORDER BY id").fetchall()

        if not genres:
            LOGGER.info("No genres in the database, nothing to do.")
            conn.close()
            return

        if len(genres) < 2:
            LOGGER.info(
                "Only one genre in the database: positions would be meaningless (nothing to be "
                "close to or far from). Skipping."
            )
            conn.close()
            return

        LOGGER.info(
            f"Computing positions for {len(genres)} genres from library co-occurrence...\n"
        )
        similarity = build_similarity_matrix(conn, genres)

        distance = 1.0 - similarity
        np.fill_diagonal(distance, 0.0)

        coords = classical_mds(distance, DEFAULT_DIMENSIONS)

        for (genre_id, name), vec in zip(genres, coords):
            position_json = json.dumps([round(float(x), 6) for x in vec])
            conn.execute(
                "UPDATE genres SET position = ? WHERE id = ?", (position_json, genre_id)
            )

        conn.commit()
