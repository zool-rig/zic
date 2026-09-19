import sys
import click

from pathlib import Path


def first_launch() -> None:
    from zic.dialogs.first_launch_dialog import FirstLaunchDialog

    dialog = FirstLaunchDialog()
    ok = dialog.exec()
    if ok == 0:
        sys.exit()


def launch_ui() -> None:
    from PySide6.QtWidgets import QApplication
    from zic.app import ZicUI, GlobalKeyFilter
    from zic.config import app_config_exists

    qapp = QApplication(sys.argv)
    if not app_config_exists():
        first_launch()
    app = ZicUI()
    key_filter = GlobalKeyFilter(app)
    qapp.installEventFilter(key_filter)
    app.show()
    sys.exit(qapp.exec())


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("-V", "version", is_flag=True)
def cli(ctx: click.Context, version: bool) -> None:
    if version:
        import importlib.metadata

        print(f"ZIC {importlib.metadata.version('zic')}")
        return

    if ctx.invoked_subcommand is None:
        launch_ui()


@cli.command(help="Ingests an audio library (mp3/m4a) into a SQLite database.")
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
    "-k", "--discogs-key", help="A Discogs Auth key, https://www.discogs.com/developers/#page:authentication,header:authentication-discogs-auth-flow"
)
@click.option(
    "-t", "--discogs-token", help="A Discogs Auth token, https://www.discogs.com/developers/#page:authentication,header:authentication-discogs-auth-flow"
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


@cli.command("compute-genres")
@click.argument(
    "db",
    type=click.Path(
        exists=True,
        dir_okay=False,
        writable=True,
        path_type=Path,
    ),
    help="Path to the SQLite database"
)
def compute_genres(db: Path) -> None:
    from zic.ingestor.genres import compute_genres_positions

    compute_genres_positions(db)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
