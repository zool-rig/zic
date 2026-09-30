from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QMessageBox

from zic.logging import get_logger

LOGGER = get_logger("InstanceLock")


def lock_path_for(db_path: Path) -> Path:
    return db_path.with_name(f"{db_path.name}.lock")


def acquire_instance_lock(db_path: Path) -> QLockFile | None:
    """Ensures no other ZIC instance is using the same database.

    SQLite can't list the connections open on a file, so each running app
    holds a lock file next to the database instead. Qt removes stale locks
    left by a crashed instance (dead PID) on its own.

    Returns the held lock, which must be kept alive for the whole app
    lifetime, or None if the user chose to continue without it. Exits if
    the user chose to quit.
    """
    lock = QLockFile(str(lock_path_for(db_path)))
    lock.setStaleLockTime(0)  # only rely on the PID check, never on age

    while not lock.tryLock(0):
        if lock.error() != QLockFile.LockError.LockFailedError:
            # Permission or unknown error: can't tell, don't block the user.
            LOGGER.warning(f"Can't create lock file for {db_path}: {lock.error()}")
            return None

        info = lock.getLockInfo()
        owner = f" (PID {info[0]} on {info[1]})" if info else ""
        LOGGER.warning(f"Database {db_path} is already used by another instance{owner}")

        box = QMessageBox(
            QMessageBox.Icon.Warning,
            "ZIC is already running",
            "Another instance of ZIC is already using this database"
            f"{owner}.\n\n"
            "Running several instances on the same database can cause write "
            "conflicts (plays, likes, scans). Please close the other instances, "
            "then click Retry.",
        )
        retry_btn = box.addButton(QMessageBox.StandardButton.Retry)
        ignore_btn = box.addButton("Continue anyway", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.setDefaultButton(retry_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked is ignore_btn:
            return None
        if clicked is not retry_btn:
            raise SystemExit(0)

    return lock
