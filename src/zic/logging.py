import logging
import os

if "ZIC_DEVEL" not in os.environ:
    os.environ.setdefault(
        "QT_LOGGING_RULES", "qt.multimedia.ffmpeg.*=false;qt.multimedia.ffmpeg=false"
    )


class ColoredFormatter(logging.Formatter):
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    blue = "\x1b[0;34m"
    reset = "\x1b[0m"
    format = "%(asctime)s - ZIC - %(name)s - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: blue + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    level = logging.DEBUG if "ZIC_DEVEL" in os.environ else logging.INFO
    logger.setLevel(level)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(ColoredFormatter())
    logger.addHandler(stream_handler)
    return logger
