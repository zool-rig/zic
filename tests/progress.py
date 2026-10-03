import io
import logging

import pytest
from rich.console import Console

from zic.ingestor.progress import IngestProgress


def _progress(tmp_path, total=3):
    console = Console(file=io.StringIO(), width=100, force_terminal=False)
    logger = logging.getLogger("test-ingest-progress")
    logger.setLevel(logging.INFO)
    return IngestProgress(tmp_path, tmp_path / "lib.db", False, total, logger, console)


def test_counts_and_summary(tmp_path):
    progress = _progress(tmp_path)
    with progress:
        for name, status in (("a.mp3", "created"), ("b.mp3", "unchanged"), ("c.mp3", "error")):
            progress.start_file(tmp_path / name)
            progress.finish_file(status)

    assert progress.counts == {"created": 1, "updated": 0, "unchanged": 1, "skipped": 0, "error": 1}
    assert progress.current == "c.mp3"
    output = progress.console.file.getvalue()
    assert "ZIC ingest" in output
    assert "Ingest finished with errors" in output
    assert "3/3" in output


def test_logs_go_through_the_console_then_handlers_are_restored(tmp_path):
    progress = _progress(tmp_path)
    original = logging.StreamHandler()
    progress.logger.handlers = [original]

    with progress:
        progress.logger.info("Album created : Moon Safari")

    assert progress.logger.handlers == [original]
    assert progress.logger.propagate
    assert "Album created : Moon Safari" in progress.console.file.getvalue()


def test_interrupted_run_says_so(tmp_path):
    progress = _progress(tmp_path)
    with pytest.raises(KeyboardInterrupt), progress:
        raise KeyboardInterrupt
    assert "Ingest interrupted" in progress.console.file.getvalue()
