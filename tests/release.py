import pytest

from zic.utils.release import find_release_date


@pytest.mark.parametrize(
    "fields, expected",
    [
        # As written by setuptools: every keyword in one comma-separated field.
        (["music,release-date:2026-09-20,player"], "2026-09-20"),
        (["release-date:2026-09-20"], "2026-09-20"),
        (["music, release-date:2026-09-20 , player"], "2026-09-20"),
        # One field per keyword, as other build backends may write them.
        (["music", "release-date:2026-09-20"], "2026-09-20"),
        (["music,player"], None),
        (["release-date:"], None),
        ([], None),
    ],
)
def test_find_release_date(fields, expected):
    assert find_release_date(fields) == expected
