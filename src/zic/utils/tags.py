import os
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen import MutagenError

# Keys of mutagen's "easy" interface, the same the ingestor reads: they map
# to the right frame/atom for both MP3 (ID3) and M4A (MP4).
EDITABLE_TAGS = {
    "title",
    "artist",
    "album",
    "albumartist",
    "date",
    "genre",
    "tracknumber",
    "discnumber",
}


class TagWriteError(Exception):
    pass


def format_number_pair(number: int | None, total: int | None) -> str | None:
    """(3, 12) -> "3/12", (3, None) -> "3", (None, ...) -> None."""
    if number is None:
        return None
    return f"{number}/{total}" if total else str(number)


def check_writable(paths: list[Path]) -> None:
    """Raises before anything is written if a file can't be modified, so a
    multi-file edit doesn't stop halfway."""
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise TagWriteError(f"File not found: {missing[0]}")
    read_only = [p for p in paths if not os.access(p, os.W_OK)]
    if read_only:
        raise TagWriteError(f"File is read-only: {read_only[0]}")


def read_tags(path: Path) -> dict[str, str]:
    """First value of each editable tag present in the file."""
    try:
        audio = MutagenFile(path, easy=True)
    except MutagenError as e:
        raise TagWriteError(f"Can't read tags of {path}: {e}") from e
    if audio is None or not audio.tags:
        return {}
    return {
        key: str(values[0])
        for key in EDITABLE_TAGS
        if (values := audio.tags.get(key))
    }


def write_tags(path: Path, tags: dict[str, str | None]) -> None:
    """Sets the given tags (a None or empty value removes the tag). Other
    tags are left untouched."""
    unknown = set(tags) - EDITABLE_TAGS
    if unknown:
        raise ValueError(f"Not editable tags: {sorted(unknown)}")

    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            raise TagWriteError(f"Unsupported audio file: {path}")
        if audio.tags is None:
            audio.add_tags()
        for key, value in tags.items():
            if value:
                audio.tags[key] = [value]
            elif key in audio.tags:
                del audio.tags[key]
        audio.save()
    except MutagenError as e:
        raise TagWriteError(f"Can't write tags of {path}: {e}") from e
    except OSError as e:
        raise TagWriteError(f"Can't write {path}: {e.strerror}") from e
