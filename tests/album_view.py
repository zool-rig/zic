from types import SimpleNamespace

import pytest

from zic.widgets.album_view import format_songs_info


def _songs(*durations):
    return [SimpleNamespace(duration=d) for d in durations]


@pytest.mark.parametrize(
    "durations, expected",
    [
        ((), "0 songs · 0 min"),
        ((200,), "1 song · 3 min"),
        ((240,) * 12, "12 songs · 48 min"),
        ((180,) * 25, "25 songs · 1 h 15 min"),
        ((1800, 1860), "2 songs · 1 h 01 min"),
    ],
)
def test_format_songs_info(durations, expected):
    assert format_songs_info(_songs(*durations)) == expected
