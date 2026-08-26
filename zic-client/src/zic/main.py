import sys

from PySide6.QtWidgets import QApplication

from zic.app import ZicUI


def main() -> None:
    qapp = QApplication(sys.argv)
    app = ZicUI()
    app.show()
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()
