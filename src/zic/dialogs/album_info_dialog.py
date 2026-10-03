from pathlib import PurePath

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from zic.api import AlbumEdit, ZicApi
from zic.dialogs.metadata_dialog import (
    MetadataDialog,
    make_completer,
    make_optional_spinbox,
    optional_value,
)
from zic.models.album import Album, AlbumCover
from zic.models.song import Song
from zic.utils.formatting import format_songs_info
from zic.widgets.cover_thumbnail import DEFAULT_COVER, CoverThumbnail


def common_folder(songs: list[Song]) -> str:
    """Deepest folder holding every song, relative to the library root."""
    folders = [song.path.parent for song in songs]
    if not folders:
        return "—"
    common = folders[0]
    while not all(f == common or common in f.parents for f in folders):
        common = common.parent
    return str(common) if common != PurePath(".") else "Library root"


class HiddenSongRow(QWidget):
    """A hidden song, with a button to show it again."""

    def __init__(self, song: Song, on_show) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        show_btn = QPushButton("Show")
        show_btn.setToolTip("Show this song in the library again")
        show_btn.clicked.connect(lambda: on_show(song, self))
        layout.addWidget(QLabel(song.title))
        layout.addStretch()
        layout.addWidget(show_btn)


class AlbumInfoDialog(MetadataDialog):
    def __init__(
        self,
        api: ZicApi,
        album: Album,
        cover: AlbumCover | None,
        parent: QWidget | None = None,
    ) -> None:
        self.album: Album = album
        self.cover: AlbumCover | None = cover
        self.songs: list[Song] = api.get_album_songs(album)
        self.hidden_songs: list[Song] = api.get_hidden_album_songs(album)
        # The album id after saving: it changes when merged into another one.
        self.album_id: int = album.id

        # Widgets
        self.cover_thumbnail = None
        self.name_edt = None
        self.artist_edt = None
        self.year_spin = None
        self.genres_edt = None
        self.hidden_songs_container = None

        super().__init__(api, f"{album.name} — {album.artist.name}", parent)

    def init_widgets(self) -> None:
        super().init_widgets()
        self.cover_thumbnail = CoverThumbnail(width=96, height=96)
        self.name_edt = QLineEdit(self.album.name)
        self.artist_edt = QLineEdit(self.album.artist.name)
        self.year_spin = make_optional_spinbox(9999, self.album.year)
        self.genres_edt = QLineEdit(", ".join(g.name for g in self.album.genres))
        self.hidden_songs_container = QWidget()

    def set_layout(self) -> None:
        super().set_layout()
        # Cover next to the title.
        self.main_v_layout.removeWidget(self.title_lbl)
        header = QHBoxLayout()
        header.addWidget(self.cover_thumbnail)
        header.addWidget(self.title_lbl, 1)
        self.main_v_layout.insertLayout(0, header)

        self.metadata_form.addRow("Name :", self.name_edt)
        self.metadata_form.addRow("Album artist :", self.artist_edt)
        self.metadata_form.addRow("Year :", self.year_spin)
        self.metadata_form.addRow("Genres :", self.genres_edt)

        songs = self.songs + self.hidden_songs
        self.add_detail("Songs", format_songs_info(self.songs))
        self.add_detail("Folder", common_folder(songs))
        self.add_detail("Date tag", self.album.raw_date or "—")
        self.add_detail("Compilation", "Yes" if self.album.is_compilation else "No")
        self.add_detail("Plays", str(sum(s.play_count for s in songs)))
        self.add_detail("Likes", str(sum(s.like_count for s in songs)))

        if self.hidden_songs:
            layout = QVBoxLayout(self.hidden_songs_container)
            layout.setContentsMargins(0, 0, 0, 0)
            for song in self.hidden_songs:
                layout.addWidget(HiddenSongRow(song, self.show_song))
            self.add_detail("Hidden songs", self.hidden_songs_container)

    def set_default(self) -> None:
        super().set_default()
        self.cover_thumbnail.bytes = (
            self.cover.thumbnail if self.cover is not None else DEFAULT_COVER
        )
        make_completer([a.name for a in self.api.artists()], self.artist_edt)
        make_completer(
            [g.name for g in self.api.genres()], self.genres_edt, multi_value=True
        )
        self.genres_edt.setPlaceholderText("Comma-separated, e.g. trip hop, downtempo")

    def files_description(self) -> str:
        count = len(self.songs) + len(self.hidden_songs)
        return f"the {count} file{'s' if count != 1 else ''} of this album"

    def show_song(self, song: Song, row: QWidget) -> None:
        self.api.set_song_hidden(song, False)
        self.changed = True
        row.hide()
        if all(r.isHidden() for r in self.hidden_songs_container.findChildren(HiddenSongRow)):
            self.details_form.setRowVisible(self.hidden_songs_container, False)

    def save(self) -> bool:
        name, artist_name = self.name_edt.text(), self.artist_edt.text()
        if (name.strip(), artist_name.strip()) != (self.album.name, self.album.artist.name):
            target = self.api.find_album(name, artist_name, exclude=self.album)
            if target is not None and not self.confirm_merge(target):
                return False

        album_id = self.api.update_album(
            self.album,
            AlbumEdit(
                name=name,
                artist_name=artist_name,
                year=optional_value(self.year_spin),
                genres=self.genres_edt.text().split(","),
            ),
            write_file_tags=self.write_file_tags,
        )
        if album_id is not None:
            self.album_id = album_id
            self.changed = True
        return True

    def confirm_merge(self, target: Album) -> bool:
        answer = QMessageBox.question(
            self,
            "Merge albums",
            f"An album named “{target.name}” by {target.artist.name} already "
            f"exists.\nThe songs of this album will be merged into it.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return answer == QMessageBox.Ok
