import sys
import os
import logging
import click


if "ZIC_DEVEL" not in os.environ:
    os.environ.setdefault(
        "QT_LOGGING_RULES", "qt.multimedia.ffmpeg.*=false;qt.multimedia.ffmpeg=false"
    )


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
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.DEBUG if "ZIC_DEVEL" in os.environ else logging.INFO,
    )

    if version:
        import importlib.metadata
        print(f"ZIC {importlib.metadata.version('zic')}")
        return

    if ctx.invoked_subcommand is None:
        launch_ui()


@cli.command("ingest")
def ingest() -> None:
    print("Ingest")


@cli.command("compute-genres")
def compute_genres() -> None:
    print("Compute genres")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
