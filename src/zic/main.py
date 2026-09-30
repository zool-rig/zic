import sys
from pathlib import Path

import click


def first_launch() -> None:
    from zic.dialogs.first_launch_dialog import FirstLaunchDialog

    dialog = FirstLaunchDialog()
    ok = dialog.exec()
    if ok == 0:
        sys.exit()


def launch_ui() -> None:
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from zic.app import GlobalKeyFilter, ZicUI
    from zic.config import app_config_exists, get_app_config
    from zic.resources import get_resource
    from zic.utils.instance_lock import acquire_instance_lock

    qapp = QApplication(sys.argv)
    qapp.setWindowIcon(QIcon(get_resource("icons/zic.ico")))

    if not app_config_exists():
        first_launch()
    # Kept in a local so the lock is held until the app exits.
    instance_lock = acquire_instance_lock(get_app_config().db_path)  # noqa: F841
    app = ZicUI()
    key_filter = GlobalKeyFilter(app)
    qapp.installEventFilter(key_filter)
    app.show()
    sys.exit(qapp.exec())


@click.group(invoke_without_command=True, epilog="Run the GUI : zic")
@click.pass_context
@click.option("-V", "version", is_flag=True, help="Show the current version of ZIC")
def cli(ctx: click.Context, version: bool) -> None:
    """A local-library desktop music player with album/genre browsing and genre-aware smart playlists."""
    if version:
        import importlib.metadata

        print(f"ZIC {importlib.metadata.version('zic')}")
        return

    if ctx.invoked_subcommand is None:
        launch_ui()


@cli.command(
    help="Ingests an audio library (mp3/m4a) into a SQLite database.",
    epilog="Exemple:\n\n  zic ingest ~/Music",
)
@click.argument(
    "folder",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Root folder of the library to scan",
)
@click.option(
    "--db",
    type=Path,
    default=None,
    help="Path to the SQLite database, default to '$FOLDER/.db'",
)
@click.option(
    "--rescan", is_flag=True, help="Force re-parsing of every file, even unchanged ones"
)
@click.option(
    "-k",
    "--discogs-key",
    help="A Discogs Auth key, https://www.discogs.com/developers/#page:authentication,header:authentication-discogs-auth-flow",
)
@click.option(
    "-t",
    "--discogs-token",
    help="A Discogs Auth token, https://www.discogs.com/developers/#page:authentication,header:authentication-discogs-auth-flow",
)
def ingest(
    folder: Path,
    db: Path | None,
    rescan: bool,
    discogs_key: str | None,
    discogs_token: str | None,
) -> None:
    from zic.ingestor.ingest import ingest as do_ingest

    do_ingest(
        folder,
        db or (folder / ".db"),
        rescan,
        discogs_key=discogs_key,
        discogs_token=discogs_token,
    )


@cli.group(
    "genres",
    invoke_without_command=False,
    help="Manage genre proximity positions used to build genre-aware playlists.",
)
def genres() -> None:
    pass


@genres.command(
    "compute",
    epilog="Example:\n\n  zic genres compute ~/Music/.db",
)
@click.argument(
    "db",
    type=click.Path(
        exists=True,
        dir_okay=False,
        writable=True,
        path_type=Path,
    ),
    help="Path to the SQLite database",
)
def compute_genres(db: Path) -> None:
    """Computes proximity positions for every genre in the library.

    Positions are derived from how genres co-occur across your albums
    (Positive PMI + classical MDS), so they reflect your own collection
    rather than a fixed external taxonomy. Run this after a fresh import
    or whenever you've ingested enough new albums that genre relationships
    may have shifted. Re-run any time; existing positions are overwritten.
    """
    from zic.ingestor.genres import compute_genres_positions

    compute_genres_positions(db)


@genres.command(
    "vis",
    epilog="Example:\n\n  zic genres vis ~/Music/.db",
)
@click.argument(
    "db",
    type=click.Path(
        exists=True,
        dir_okay=False,
        writable=True,
        path_type=Path,
    ),
    help="Path to the SQLite database",
)
def visualize_genres(db: Path) -> None:
    """Opens an interactive 2D plot of the computed genre positions.

    Requires positions to have been computed first (see `zic genres compute`).
    Opens in your default web browser via Plotly; genres with no computed
    position are omitted from the plot.
    """
    from zic.ingestor.genres import visualize_genres as do_visualize_genres

    do_visualize_genres(db)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
