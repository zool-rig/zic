import json
import sqlite3
import wave

import numpy as np
import pytest

from zic.ingestor.cues import WINDOW, analyze, analyze_file, find_cues

RATE = 44100


def write_wav(path, *parts):
    """A mono WAV made of (seconds, amplitude) parts of a 440 Hz sine."""
    samples = np.concatenate(
        [
            amplitude * np.sin(2 * np.pi * 440 * np.arange(int(seconds * RATE)) / RATE)
            for seconds, amplitude in parts
        ]
    )
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes((samples * 32767).astype("<i2").tobytes())
    return path


def test_cues_skip_the_silences_around_the_song():
    levels = np.array([-120.0] * 20 + [-10.0] * 100 + [-120.0] * 30)

    assert find_cues(levels) == (20 * WINDOW, 120 * WINDOW)


def test_cue_out_lands_inside_the_fade_out():
    fade = np.linspace(-10, -70, 61)  # -1 dB per window
    levels = np.concatenate([[-10.0] * 200, fade])

    cue_in, cue_out = find_cues(levels)

    assert cue_in == 0.0
    # Last window at least 20 dB under the loud level
    assert cue_out == pytest.approx((200 + 21) * WINDOW)


def test_silent_song_keeps_its_whole_length():
    assert find_cues(np.array([-120.0] * 40)) == (0.0, 40 * WINDOW)
    assert find_cues(np.array([])) == (0.0, 0.0)


def test_analyze_file_decodes_the_audio(tmp_path):
    path = write_wav(tmp_path / "song.wav", (1, 0), (3, 0.5), (1.5, 0))

    cue_in, cue_out = analyze_file(path)

    assert cue_in == pytest.approx(1.0, abs=0.1)
    assert cue_out == pytest.approx(4.0, abs=0.1)


def test_analyze_fills_the_songs_not_analyzed_yet(tmp_path, capsys, db_with_song):
    db_path, root = db_with_song
    write_wav(root / "song.wav", (0.5, 0), (3, 0.5))

    analyze(root, db_path, json_progress=True)

    with sqlite3.connect(db_path) as conn:
        cue_in, cue_out = conn.execute("SELECT cue_in, cue_out FROM songs").fetchone()
    assert cue_in == pytest.approx(0.5, abs=0.1)
    assert cue_out == pytest.approx(3.5, abs=0.1)
    end = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert end["counts"]["updated"] == 1


def test_analyze_skips_missing_files(tmp_path, capsys, db_with_song):
    db_path, root = db_with_song

    analyze(root, db_path, json_progress=True)

    end = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert end["counts"]["skipped"] == 1


@pytest.fixture
def db_with_song(tmp_path, library_db_path):
    """The seeded library, down to one song, 'song.wav', not analyzed yet."""
    root = tmp_path / "lib"
    root.mkdir()
    with sqlite3.connect(library_db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        (song_id,) = conn.execute("SELECT MIN(id) FROM songs").fetchone()
        conn.execute("DELETE FROM songs WHERE id != ?", (song_id,))
        conn.execute("UPDATE songs SET path = 'song.wav'")
    return library_db_path, root
