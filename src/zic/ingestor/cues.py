"""Transition cue points: where a song's sound really starts and where it is
over, so crossfades skip leading silences and fade over the outro instead
of the file's last seconds."""

import sqlite3
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from pathlib import Path

import av
import numpy as np

from zic.ingestor.progress import IngestProgress, JsonIngestProgress
from zic.logging import get_logger
from zic.utils.db_utils import migrate_database

ANALYSIS_RATE = 11025  # Hz: plenty to measure loudness, and 4x less to decode
WINDOW = 0.05  # s, loudness resolution
# Thresholds below the song's loud level (90th percentile of its windows),
# so quiet recordings get their cues as well as loud ones.
CUE_IN_THRESHOLD = -40.0  # dB: anything above is the song starting
CUE_OUT_THRESHOLD = -20.0  # dB: below it until the end, the song is over
SILENCE_LEVEL = -60.0  # dBFS: a loud level under it is a silent track
FLOOR_LEVEL = -120.0  # dBFS, digital silence

FILES_PER_COMMIT = 10

LOGGER = get_logger("Analysis")


def read_levels(path: Path) -> np.ndarray:
    """The song's loudness for each WINDOW, in dBFS."""
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        # Large output frames: per-frame Python calls cost more than decoding.
        resampler = av.AudioResampler(
            format="flt",
            layout="mono",
            rate=ANALYSIS_RATE,
            frame_size=ANALYSIS_RATE * 5,
        )
        chunks = []
        for packet in container.demux(stream):
            try:
                frames = packet.decode()
            except av.InvalidDataError:
                # A damaged frame here and there (common in MP3s): players
                # skip it, and so can the analysis.
                continue
            for frame in frames:
                chunks.extend(f.to_ndarray().ravel() for f in resampler.resample(frame))
        chunks.extend(f.to_ndarray().ravel() for f in resampler.resample(None))

    size = int(ANALYSIS_RATE * WINDOW)
    samples = np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)
    count = len(samples) // size
    windows = samples[: count * size].reshape(count, size)
    rms = np.sqrt(np.mean(np.square(windows, dtype=np.float64), axis=1))
    return 20 * np.log10(np.maximum(rms, 10 ** (FLOOR_LEVEL / 20)))


def find_cues(levels: np.ndarray) -> tuple[float, float]:
    """(cue_in, cue_out) in seconds, from the song's loudness levels. A
    silent song gets its whole length: there's nothing to cut."""
    duration = round(len(levels) * WINDOW, 3)
    if len(levels) == 0:
        return 0.0, 0.0

    loud = np.percentile(levels, 90)
    if loud < SILENCE_LEVEL:
        return 0.0, duration

    starts = np.flatnonzero(levels >= loud + CUE_IN_THRESHOLD)
    ends = np.flatnonzero(levels >= loud + CUE_OUT_THRESHOLD)
    return round(starts[0] * WINDOW, 3), round((ends[-1] + 1) * WINDOW, 3)


def analyze_file(path: Path) -> tuple[float, float]:
    return find_cues(read_levels(path))


def store_cues(
    conn: sqlite3.Connection, song_id: int, cues: tuple[float, float]
) -> None:
    conn.execute(
        "UPDATE songs SET cue_in = ?, cue_out = ? WHERE id = ?", (*cues, song_id)
    )


def analyze(
    root: Path, db_path: Path, everything: bool = False, json_progress: bool = False
) -> None:
    """Computes the cue points of the songs not analyzed yet (every song with
    everything=True), on all CPU cores. The ingest analyzes the songs it adds:
    this is for libraries ingested before cue points existed."""
    with sqlite3.connect(db_path) as conn:
        migrate_database(conn)
        has_songs = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'songs'"
        ).fetchone()
        rows = (
            conn.execute(
                "SELECT id, path FROM songs"
                + ("" if everything else " WHERE cue_in IS NULL")
                + " ORDER BY path"
            ).fetchall()
            if has_songs
            else []
        )

        progress = (
            JsonIngestProgress(root, len(rows), LOGGER)
            if json_progress
            else IngestProgress(
                root, db_path, everything, len(rows), LOGGER, task="analysis"
            )
        )
        files_to_commit = 0
        executor = ProcessPoolExecutor()
        try:
            with progress:
                futures: dict[Future, tuple[int, Path]] = {}
                for song_id, rel_path in rows:
                    path = root / rel_path
                    if path.exists():
                        futures[executor.submit(analyze_file, path)] = (song_id, path)
                    else:
                        progress.start_file(path)
                        LOGGER.warning(f"File not found : '{rel_path}', skipped")
                        progress.finish_file("skipped")

                for future in as_completed(futures):
                    song_id, path = futures[future]
                    progress.start_file(path)
                    try:
                        store_cues(conn, song_id, future.result())
                        status = "updated"
                        LOGGER.debug(f"Song analyzed : '{path.relative_to(root)}'")
                    except Exception as e:  # noqa BLE001
                        status = "error"
                        LOGGER.error(
                            f"Failed to analyze '{path.relative_to(root)}': {e!r}"
                        )
                    progress.finish_file(status)

                    files_to_commit += 1
                    if files_to_commit == FILES_PER_COMMIT:
                        conn.commit()
                        files_to_commit = 0
        finally:
            # Interrupted: drop the queued songs instead of analyzing them all.
            executor.shutdown(cancel_futures=True)
