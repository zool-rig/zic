import logging
import time
from pathlib import Path
from types import TracebackType
from typing import Self

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

# status -> (label, style), in display order
STATUSES: dict[str, tuple[str, str]] = {
    "created": ("created", "green"),
    "updated": ("updated", "cyan"),
    "unchanged": ("unchanged", "bright_black"),
    "skipped": ("skipped", "yellow"),
    "error": ("errors", "red"),
}


class RemainingColumn(ProgressColumn):
    """'1 234 left'."""

    def render(self, task: Task) -> Text:
        if task.total is None:
            return Text("")
        return Text(f"{int(task.total - task.completed)} left", style="magenta")


class IngestProgress:
    """Terminal UI of an ingest run: a header, then a live progress bar,
    status counters and the file being processed, with the ingest logs
    scrolling above them, and a summary at the end.

    On a non-interactive output (pipe, the app's QProcess), the live part
    isn't redrawn: only the logs and the summary are printed."""

    def __init__(
        self,
        root: Path,
        db_path: Path,
        rescan: bool,
        total: int,
        logger: logging.Logger,
        console: Console | None = None,
    ) -> None:
        self.root: Path = root
        self.db_path: Path = db_path
        self.rescan: bool = rescan
        self.total: int = total
        self.logger: logging.Logger = logger
        self.console: Console = console or Console()
        self.counts: dict[str, int] = dict.fromkeys(STATUSES, 0)
        self.current: str = ""
        self.started_at: float = 0.0

        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]Ingesting"),
            BarColumn(),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TextColumn("•"),
            RemainingColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("elapsed • ETA"),
            TimeRemainingColumn(),
            console=self.console,
        )
        self.task_id = self.progress.add_task("ingest", total=total)
        self.live = Live(
            self, console=self.console, refresh_per_second=10, transient=True
        )
        self._saved_handlers: list[logging.Handler] = []
        self._saved_propagate: bool = True

    def __enter__(self) -> Self:
        self.started_at = time.monotonic()
        self.console.print(self.header())
        # Route the ingest logs through the live console: they print above
        # the progress display instead of breaking it.
        self._saved_handlers = self.logger.handlers[:]
        self._saved_propagate = self.logger.propagate
        handler = RichHandler(
            console=self.console,
            show_path=False,
            markup=False,
            rich_tracebacks=True,
            log_time_format="[%X]",
        )
        handler.setLevel(self.logger.level)
        self.logger.handlers = [handler]
        self.logger.propagate = False
        self.live.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.live.stop()
        self.logger.handlers = self._saved_handlers
        self.logger.propagate = self._saved_propagate
        self.console.print(self.summary(interrupted=exc_type is not None))

    def start_file(self, path: Path) -> None:
        self.current = str(path.relative_to(self.root))

    def finish_file(self, status: str) -> None:
        self.counts[status] += 1
        self.progress.advance(self.task_id)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def header(self) -> Panel:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold")
        grid.add_column()
        grid.add_row("Library", str(self.root))
        grid.add_row("Database", str(self.db_path))
        grid.add_row(
            "Mode",
            "full rescan" if self.rescan else "new and modified files only",
        )
        grid.add_row("Files", str(self.total))
        return Panel(grid, title="[bold cyan]ZIC ingest", border_style="cyan", expand=False)

    def counters(self) -> Text:
        text = Text()
        for status, (label, style) in STATUSES.items():
            if text:
                text.append("   ")
            text.append(f"{self.counts[status]}", style=f"bold {style}")
            text.append(f" {label}", style=style)
        return text

    def __rich__(self) -> RenderableType:
        """Redrawn by the Live display on every refresh."""
        current = Text(f"→ {self.current}", style="dim", no_wrap=True, overflow="ellipsis")
        return Panel(
            Group(self.progress, self.counters(), current),
            border_style="bright_black",
        )

    def summary(self, interrupted: bool = False) -> Panel:
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="right")
        table.add_column()
        for status, (label, style) in STATUSES.items():
            table.add_row(f"[bold {style}]{self.counts[status]}", f"[{style}]{label}")

        processed = sum(self.counts.values())
        elapsed = self.elapsed
        minutes, seconds = divmod(int(elapsed), 60)
        rate = processed / elapsed if elapsed > 0 else 0.0
        table.add_row("", "")
        table.add_row(f"[bold]{processed}/{self.total}", "files processed")
        table.add_row(f"[bold]{minutes:02d}:{seconds:02d}", f"elapsed ({rate:.1f} files/s)")

        if interrupted:
            title, style = "[bold yellow]Ingest interrupted", "yellow"
        elif self.counts["error"]:
            title, style = "[bold red]Ingest finished with errors", "red"
        else:
            title, style = "[bold green]Ingest finished", "green"
        return Panel(table, title=title, border_style=style, expand=False)
