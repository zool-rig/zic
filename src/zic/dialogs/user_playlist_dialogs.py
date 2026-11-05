from collections.abc import Callable

from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from zic.api import ZicApi
from zic.models.user_playlist import UserPlaylist, UserPlaylistNameError


def ask_name(parent: QWidget | None, title: str, name: str) -> str | None:
    text, accepted = QInputDialog.getText(
        parent, title, "Name:", QLineEdit.EchoMode.Normal, name
    )
    return text if accepted else None


def show_name_error(parent: QWidget | None, message: str) -> None:
    QMessageBox.warning(parent, "Invalid name", message)


def confirm_deletion(parent: QWidget | None, playlist: UserPlaylist) -> bool:
    message = f"Delete the playlist '{playlist.name}'? Its songs stay in your library."
    if playlist.folder is not None:
        message += (
            f"\n\nIts folder '{playlist.folder}' and its files are kept, "
            "and won't make it come back at the next scan."
        )
    answer = QMessageBox.question(
        parent,
        "Delete playlist",
        message,
        QMessageBox.Ok | QMessageBox.Cancel,
        QMessageBox.Cancel,
    )
    return answer == QMessageBox.Ok


def _ask_valid_name(
    parent: QWidget | None,
    title: str,
    name: str,
    apply: Callable[[str], UserPlaylist],
) -> UserPlaylist | None:
    """Asks again until the name is accepted, or the user gives up."""
    while (name := ask_name(parent, title, name)) is not None:
        try:
            return apply(name)
        except UserPlaylistNameError as e:
            show_name_error(parent, str(e))
    return None


def create_playlist(api: ZicApi, parent: QWidget | None) -> UserPlaylist | None:
    return _ask_valid_name(parent, "New playlist", "", api.create_user_playlist)


def rename_playlist(
    api: ZicApi, playlist: UserPlaylist, parent: QWidget | None
) -> UserPlaylist | None:
    return _ask_valid_name(
        parent,
        "Rename playlist",
        playlist.name,
        lambda name: api.rename_user_playlist(playlist, name),
    )
