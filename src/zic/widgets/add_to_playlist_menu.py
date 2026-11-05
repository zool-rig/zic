from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QMenu, QWidget

from zic.api import ZicApi
from zic.dialogs.user_playlist_dialogs import create_playlist
from zic.models.song import Song
from zic.models.user_playlist import UserPlaylist


def build_add_to_playlist_menu(
    api: ZicApi, song: Song, parent: QWidget | None = None
) -> QMenu:
    """A song is only once in a playlist: those which have it are disabled."""
    menu = QMenu(parent)
    playlist_ids = api.get_user_playlist_ids_of_song(song)
    playlists = api.get_user_playlists()
    for playlist in playlists:
        action = menu.addAction(playlist.name)
        action.setData(playlist)
        action.setEnabled(playlist.id not in playlist_ids)
    if playlists:
        menu.addSeparator()
    # No playlist as its data: that's how it's told apart from the others.
    menu.addAction("New playlist...")
    return menu


def choose_action(menu: QMenu) -> QAction | None:
    return menu.exec(QCursor.pos())


def show_add_to_playlist_menu(
    api: ZicApi, song: Song, parent: QWidget | None
) -> UserPlaylist | None:
    """Returns the playlist the song was added to, if one was chosen."""
    menu = build_add_to_playlist_menu(api, song, parent)
    action = choose_action(menu)
    chosen = action is not None
    playlist = action.data() if chosen else None
    # Its parent would otherwise keep it, one more at each opening.
    menu.deleteLater()
    if chosen and playlist is None:
        playlist = create_playlist(api, parent)
    if playlist is not None:
        api.add_song_to_user_playlist(playlist, song)
    return playlist
