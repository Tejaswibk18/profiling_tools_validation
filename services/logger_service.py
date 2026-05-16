import logging
from pathlib import Path


LOG_DIR = Path("reports/logs")

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True
)


logging.basicConfig(
    filename=LOG_DIR / "error.log",
    level=logging.ERROR,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    )
)


def log_error(message):

    logging.error(message)