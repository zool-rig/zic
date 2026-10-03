import html
import json
import re

from PySide6.QtCore import QElapsedTimer, QProcess, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QFontMetrics
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from zic.widgets.rules import HRule

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# "2026-10-03 12:00:00,000 - ZIC - Ingest - WARNING - message"
LOG_LINE_RE = re.compile(r" - (DEBUG|INFO|WARNING|ERROR|CRITICAL) - (.*)$")
LOG_COLORS = {"WARNING": "#F0C35A", "ERROR": "#FF6B6B", "CRITICAL": "#FF6B6B"}
# status -> (label, color), as in the ingest's terminal UI
STATUSES = {
    "created": ("created", "#5AD17A"),
    "updated": ("updated", "#35F0E0"),
    "moved": ("moved", "#7AA2F7"),
    "unchanged": ("unchanged", "#8B96A5"),
    "skipped": ("skipped", "#F0C35A"),
    "error": ("errors", "#FF6B6B"),
}
CANCEL_KILL_DELAY_MS = 3000
LOG_MAX_LINES = 5000


def format_clock(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


class TaskDialog(QDialog):
    """Runs a zic command in a separate process and shows its progress.

    Modal on purpose: the user can't edit the library while another
    process writes the database. Progress is determinate when the command
    reports JSON events (see zic.ingestor.progress.JsonIngestProgress),
    otherwise only its logs are shown."""

    task_finished = Signal(bool)  # whether the command succeeded

    def __init__(
        self, title: str, program: str, args: list[str], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.title: str = title
        self.program: str = program
        self.args: list[str] = args
        self.process: QProcess = QProcess(self)
        self.elapsed_timer: QElapsedTimer = QElapsedTimer()
        self.total: int | None = None
        self.processed: int = 0
        self.counts: dict[str, int] = {}
        self.cancelled: bool = False
        self.running: bool = False
        self._stdout_buffer: str = ""
        self._stderr_buffer: str = ""

        # Layouts
        self.main_v_layout = None
        self.bottom_h_layout = None

        # Widgets
        self.title_lbl = None
        self.progress_bar = None
        self.timing_lbl = None
        self.counters_lbl = None
        self.current_lbl = None
        self.log_edt = None
        self.button = None
        self.clock_timer = None

        self.init_ui()

    def init_ui(self) -> None:
        self.init_layouts()
        self.init_widgets()
        self.set_layout()
        self.set_connections()
        self.set_default()

    def init_layouts(self) -> None:
        self.main_v_layout = QVBoxLayout(self)
        self.bottom_h_layout = QHBoxLayout()

    def init_widgets(self) -> None:
        self.title_lbl = QLabel(self.title)
        self.progress_bar = QProgressBar()
        self.timing_lbl = QLabel()
        self.counters_lbl = QLabel()
        self.current_lbl = QLabel()
        self.log_edt = QPlainTextEdit()
        self.button = QPushButton("Cancel")
        self.clock_timer = QTimer(self)

    def set_layout(self) -> None:
        self.main_v_layout.addWidget(self.title_lbl)
        self.main_v_layout.addWidget(self.progress_bar)
        self.main_v_layout.addWidget(self.timing_lbl)
        self.main_v_layout.addWidget(self.counters_lbl)
        self.main_v_layout.addWidget(self.current_lbl)
        self.main_v_layout.addWidget(self.log_edt, 1)
        self.main_v_layout.addWidget(HRule())
        self.main_v_layout.addLayout(self.bottom_h_layout)
        self.bottom_h_layout.addStretch()
        self.bottom_h_layout.addWidget(self.button)

    def set_connections(self) -> None:
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.on_process_finished)
        self.process.errorOccurred.connect(self.on_process_error)
        self.clock_timer.timeout.connect(self.update_timing)
        self.button.clicked.connect(self.on_button_clicked)

    def set_default(self) -> None:
        self.setWindowTitle(self.title)
        self.setMinimumSize(640, 420)
        self.title_lbl.setObjectName("DialogTitleLabel")
        self.timing_lbl.setObjectName("DialogNoteLabel")
        self.current_lbl.setObjectName("DialogNoteLabel")
        self.counters_lbl.setTextFormat(Qt.RichText)
        self.counters_lbl.hide()
        self.progress_bar.setRange(0, 0)  # busy until the total is known
        self.progress_bar.setTextVisible(False)
        self.log_edt.setReadOnly(True)
        self.log_edt.setMaximumBlockCount(LOG_MAX_LINES)
        self.log_edt.setPlaceholderText("Logs will show up here.")
        self.clock_timer.setInterval(500)

    # --- process -----------------------------------------------------------

    def start(self) -> None:
        self.running = True
        self.elapsed_timer.start()
        self.clock_timer.start()
        self.update_timing()
        self.process.start(self.program, self.args)

    def exec(self) -> int:
        self.start()
        return super().exec()

    def read_stdout(self) -> None:
        self._stdout_buffer += bytes(self.process.readAllStandardOutput()).decode(
            errors="replace"
        )
        *lines, self._stdout_buffer = self._stdout_buffer.split("\n")
        for line in lines:
            self.handle_stdout_line(line)

    def read_stderr(self) -> None:
        self._stderr_buffer += bytes(self.process.readAllStandardError()).decode(
            errors="replace"
        )
        *lines, self._stderr_buffer = self._stderr_buffer.split("\n")
        for line in lines:
            self.append_raw_log(line)

    def handle_stdout_line(self, line: str) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self.append_raw_log(line)
            return
        if not isinstance(event, dict):
            self.append_raw_log(line)
            return

        match event.get("event"):
            case "start":
                self.total = event["total"]
                self.progress_bar.setRange(0, max(self.total, 1))
                self.progress_bar.setTextVisible(True)
                self.progress_bar.setFormat("%v / %m")
            case "file":
                self.set_current(event["current"])
            case "progress" | "end":
                self.processed = event["done"]
                self.counts = event["counts"]
                self.progress_bar.setValue(self.processed)
                self.update_counters()
                self.update_timing()
            case "log":
                self.append_log(event["level"], event["message"])

    def on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        # Lines without a trailing newline.
        if self._stdout_buffer.strip():
            self.handle_stdout_line(self._stdout_buffer)
        self.append_raw_log(self._stderr_buffer)
        self._stdout_buffer = self._stderr_buffer = ""

        success = exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit
        if self.cancelled:
            self.finish("Cancelled", success=False)
        elif success:
            errors = self.counts.get("error", 0)
            self.finish(
                f"Finished with {errors} error{'s' if errors != 1 else ''}"
                if errors
                else "Finished",
                success=True,
            )
        else:
            self.finish(f"Failed (exit code {exit_code})", success=False)

    def on_process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.append_log(
                "ERROR",
                f"Couldn't start “{self.program}”: {self.process.errorString()}",
            )
            self.finish("Failed to start", success=False)

    def finish(self, status: str, success: bool) -> None:
        if not self.running:
            return
        self.running = False
        self.clock_timer.stop()
        self.update_timing()
        self.title_lbl.setText(f"{self.title} — {status}")
        if self.total is None or not success:
            # Leave a busy bar idle.
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1 if success else 0)
        self.current_lbl.clear()
        self.button.setText("Close")
        self.task_finished.emit(success)

    # --- cancellation ------------------------------------------------------

    def on_button_clicked(self) -> None:
        if self.running:
            self.request_cancel()
        else:
            self.accept()

    def request_cancel(self) -> None:
        answer = QMessageBox.question(
            self,
            "Cancel",
            f"Stop “{self.title}”?\nWhat was already processed is kept.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes or not self.running:
            return
        self.cancelled = True
        self.button.setEnabled(False)
        self.title_lbl.setText(f"{self.title} — Cancelling…")
        self.process.terminate()
        # terminate() can be ignored (e.g. console processes on Windows).
        QTimer.singleShot(CANCEL_KILL_DELAY_MS, self.kill_if_running)

    def kill_if_running(self) -> None:
        if self.process.state() != QProcess.NotRunning:
            self.process.kill()
        self.button.setEnabled(True)

    def reject(self) -> None:
        # Escape key.
        if self.running:
            self.request_cancel()
        else:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.running:
            event.ignore()
            self.request_cancel()
        else:
            super().closeEvent(event)

    # --- display -----------------------------------------------------------

    def set_current(self, text: str) -> None:
        metrics = QFontMetrics(self.current_lbl.font())
        width = max(self.current_lbl.width(), 300)
        self.current_lbl.setText(metrics.elidedText(f"→ {text}", Qt.ElideMiddle, width))

    def update_counters(self) -> None:
        parts = [
            f'<span style="color:{color}"><b>{self.counts.get(status, 0)}</b> {label}</span>'
            for status, (label, color) in STATUSES.items()
        ]
        self.counters_lbl.setText("&nbsp;&nbsp;&nbsp;".join(parts))
        self.counters_lbl.show()

    def update_timing(self) -> None:
        elapsed = self.elapsed_timer.elapsed() / 1000 if self.elapsed_timer.isValid() else 0
        parts = []
        if self.total is not None:
            remaining = self.total - self.processed
            parts.append(f"{remaining} left")
        parts.append(f"{format_clock(elapsed)} elapsed")
        if self.running and self.total is not None and self.processed:
            eta = elapsed / self.processed * (self.total - self.processed)
            parts.append(f"ETA {format_clock(eta)}")
        self.timing_lbl.setText(" • ".join(parts))

    def append_raw_log(self, line: str) -> None:
        line = ANSI_RE.sub("", line).rstrip()
        if not line:
            return
        match = LOG_LINE_RE.search(line)
        if match:
            self.append_log(match.group(1), match.group(2))
        else:
            self.append_log("INFO", line)

    def append_log(self, level: str, message: str) -> None:
        color = LOG_COLORS.get(level)
        text = html.escape(message)
        if color:
            text = f'<span style="color:{color}">{level.title()}: {text}</span>'
        self.log_edt.appendHtml(text)
