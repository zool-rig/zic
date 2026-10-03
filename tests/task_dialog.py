from zic.dialogs.task_dialog import format_clock


def test_format_clock():
    assert format_clock(5.9) == "00:05"
    assert format_clock(125) == "02:05"
    assert format_clock(3725) == "1:02:05"
