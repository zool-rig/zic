import json
import sqlite3
import tempfile
import webbrowser
import os
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
import plotly.express as px

from zic.logging import get_logger

DEFAULT_DIMENSIONS = 8
LOGGER = get_logger("Genre Pos")


def build_similarity_matrix(
    conn: sqlite3.Connection, genres: list[tuple[int, str]]
) -> np.ndarray:
    """Builds similarity from co-occurrence within the user's own library,
    using Positive PMI (with discounting) instead of raw normalized counts,
    so that frequent/generic tags (e.g. "rock") don't dominate purely
    because of their volume.
    """
    n = len(genres)
    index_by_id = {genre_id: i for i, (genre_id, _) in enumerate(genres)}

    albums_genres: dict[int, set[int]] = defaultdict(set)
    for album_id, genre_id in conn.execute(
        "SELECT album_id, genre_id FROM album_genres"
    ):
        if genre_id in index_by_id:
            albums_genres[album_id].add(genre_id)

    total_albums = len(albums_genres)
    if total_albums == 0:
        return np.eye(n)

    co_occurrence = np.zeros((n, n))
    marginal = np.zeros(n)  # Number of albums containing each genre

    for genre_ids in albums_genres.values():
        for gid in genre_ids:
            marginal[index_by_id[gid]] += 1
        for gi, gj in combinations(genre_ids, 2):
            i, j = index_by_id[gi], index_by_id[gj]
            co_occurrence[i, j] += 1
            co_occurrence[j, i] += 1

    # P(i,j), P(i), P(j)
    p_ij = co_occurrence / total_albums
    p_i = marginal / total_albums
    outer = np.outer(p_i, p_i)

    # PMI (only where co_occurrence > 0, otherwise log(0))
    pmi = np.zeros((n, n))
    nonzero = co_occurrence > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi[nonzero] = np.log(p_ij[nonzero] / outer[nonzero])

    # Discounting: mitigates rare pairs to avoid soaring PMIs
    # on a simple chance of single co-occurrence (Pantel & Lin, 2002)
    min_marginal = np.minimum.outer(marginal, marginal)
    discount = (co_occurrence / (co_occurrence + 1)) * (
        min_marginal / (min_marginal + 1)
    )
    pmi *= discount

    # Positive PMI: we ignore the associations "less frequent than chance"
    ppmi = np.clip(pmi, 0, None)
    np.fill_diagonal(ppmi, 0)

    max_val = ppmi.max()
    similarity = ppmi / max_val if max_val > 0 else ppmi
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


def visualize_genres(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name, position FROM genres WHERE position IS NOT NULL"
        ).fetchall()

    data = [
        {"genre": name, "x": json.loads(pos)[0], "y": json.loads(pos)[1]}
        for name, pos in rows
    ]

    fig = px.scatter(
        data,
        x="x",
        y="y",
        text="genre",
        title="Musical genres proximity (2D projection of the MDS)",
    )
    fig.update_traces(textposition="top center", marker={"size": 8})

    fd, tmp_path_str = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    tmp_path = Path(tmp_path_str)

    fig.write_html(str(tmp_path))
    webbrowser.open(f"file://{tmp_path}")
