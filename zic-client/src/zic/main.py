import sys
import os
import logging

# Must be set before Qt loads, otherwise the ffmpeg multimedia backend dumps av_log output.
if "ZIC_DEVEL" not in os.environ:
    os.environ.setdefault(
        "QT_LOGGING_RULES", "qt.multimedia.ffmpeg.*=false;qt.multimedia.ffmpeg=false"
    )

from PySide6.QtWidgets import QApplication  # noqa: E402

from zic.app import ZicUI  # noqa: E402
from zic.config import app_config_exists


def first_launch() -> None:
    from zic.dialogs.first_launch_dialog import FirstLaunchDialog

    dialog = FirstLaunchDialog()
    ok = dialog.exec()
    if ok == 0:
        sys.exit()


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.DEBUG if "ZIC_DEVEL" in os.environ else logging.INFO,
    )
    qapp = QApplication(sys.argv)
    if not app_config_exists():
        first_launch()
    app = ZicUI()
    app.show()
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()
