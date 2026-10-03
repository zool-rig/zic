from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QWidget

from zic.api import SongEdit, ZicApi
from zic.dialogs.metadata_dialog import (
    MetadataDialog,
    make_completer,
    make_optional_spinbox,
    optional_value,
)
from zic.models.song import Song
from zic.utils.formatting import format_datetime, format_duration, format_size


def format_audio_info(song: Song) -> str:
    """'MP3 · 320 kbps · 44.1 kHz'."""
    parts = [song.format.upper()]
    if song.bitrate:
        parts.append(f"{round(song.bitrate / 1000)} kbps")
    if song.sample_rate:
        parts.append(f"{song.sample_rate / 1000:g} kHz")
    return " · ".join(parts)


class SongInfoDialog(MetadataDialog):
    def __init__(self, api: ZicApi, song: Song, parent: QWidget | None = None) -> None:
        self.song: Song = song

        # Widgets
        self.title_edt = None
        self.artist_edt = None
        self.track_spin = None
        self.disc_spin = None
        self.hidden_chk = None

        super().__init__(api, song.title, parent)

    def init_widgets(self) -> None:
        super().init_widgets()
        self.title_edt = QLineEdit(self.song.title)
        self.artist_edt = QLineEdit(self.song.artist_credit)
        self.track_spin = make_optional_spinbox(999, self.song.track_number)
        self.disc_spin = make_optional_spinbox(99, self.song.disc_number)
        self.hidden_chk = QCheckBox("Hide this song from the library")

    def set_layout(self) -> None:
        super().set_layout()
        self.metadata_form.addRow("Title :", self.title_edt)
        self.metadata_form.addRow("Artist :", self.artist_edt)
        self.metadata_form.addRow(
            "Track :", self.with_total(self.track_spin, self.song.track_total)
        )
        self.metadata_form.addRow(
            "Disc :", self.with_total(self.disc_spin, self.song.disc_total)
        )
        self.metadata_form.addRow("", self.hidden_chk)

        song, album = self.song, self.song.album
        path = Path(self.api.get_song_path(song))
        size = format_size(path.stat().st_size) if path.is_file() else "File not found"
        self.add_detail("Album", f"{album.name} — {album.artist.name}")
        self.add_detail("File", str(song.path))
        self.add_detail("Audio", format_audio_info(song))
        self.add_detail("Duration", format_duration(song.duration))
        self.add_detail("Size", size)
        self.add_detail("Plays", str(song.play_count))
        self.add_detail("Likes", str(song.like_count))
        self.add_detail("Last played", format_datetime(song.last_played_at, "Never"))
        self.add_detail("Added", format_datetime(song.added_to_library_at))
        self.add_detail("Last scan", format_datetime(song.imported_at))

    def set_default(self) -> None:
        super().set_default()
        make_completer([a.name for a in self.api.artists()], self.artist_edt)
        self.hidden_chk.setChecked(self.song.hidden)
        self.hidden_chk.setToolTip(
            "Hidden songs are left out of albums, playlists and searches.\n"
            "They can be shown again from the album info."
        )

    def files_description(self) -> str:
        return "the audio file"

    @staticmethod
    def with_total(spinbox: QWidget, total: int | None) -> QWidget:
        """The spin box, followed by "/ total" when the total is known."""
        if not total:
            return spinbox
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(spinbox)
        layout.addWidget(QLabel(f"/ {total}"))
        layout.addStretch()
        return container

    def save(self) -> bool:
        self.changed = self.api.update_song(
            self.song,
            SongEdit(
                title=self.title_edt.text(),
                artist_credit=self.artist_edt.text(),
                track_number=optional_value(self.track_spin),
                disc_number=optional_value(self.disc_spin),
            ),
            write_file_tags=self.write_file_tags,
        )
        if self.hidden_chk.isChecked() != self.song.hidden:
            self.api.set_song_hidden(self.song, self.hidden_chk.isChecked())
            self.changed = True
        return True
