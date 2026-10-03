from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol


class HasDuration(Protocol):
    duration: float


def format_duration(seconds: float) -> str:
    """'03:25'."""
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def format_songs_info(songs: Sequence[HasDuration]) -> str:
    """'12 songs · 47 min', or '25 songs · 1 h 12 min'."""
    count = f"{len(songs)} song{'s' if len(songs) != 1 else ''}"
    minutes = round(sum(song.duration for song in songs) / 60)
    hours, minutes = divmod(minutes, 60)
    duration = f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"
    return f"{count} · {duration}"


def format_size(size: int) -> str:
    """'8.4 MB'."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def format_datetime(value: datetime | None, default: str = "—") -> str:
    """Local time. Naive datetimes come from SQLite's datetime('now'): UTC."""
    if value is None:
        return default
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone().strftime("%d/%m/%Y %H:%M")
