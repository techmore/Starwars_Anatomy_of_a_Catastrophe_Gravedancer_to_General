"""Logging helpers for the local app."""

import logging
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "log"
LOG_PATH = REPO_ROOT / "log.txt"
_RUN_LOCK = RLock()
_CURRENT_RUN_LOG_PATH: Path | None = None


def _ensure_log_targets() -> None:
    global _CURRENT_RUN_LOG_PATH
    if _CURRENT_RUN_LOG_PATH is not None:
        return
    run_dir = LOG_DIR / f"RUN_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    _CURRENT_RUN_LOG_PATH = run_dir / "Logs_Associated_with_start_of_Run.txt"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.touch(exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    _CURRENT_RUN_LOG_PATH.touch(exist_ok=True)


def _new_run_log_path(run_label: str | None = None) -> Path:
    """Create a new timestamped run log path."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"-{_slugify(run_label)}" if run_label else ""
    run_dir = LOG_DIR / f"RUN_{stamp}{suffix}-{uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "Logs_Associated_with_start_of_Run.txt"


def _slugify(value: str | None) -> str:
    """Normalize a run label for filesystem use."""
    if not value:
        return ""
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:32]


def get_run_log_path() -> Path:
    """Return the currently active run log path."""
    _ensure_log_targets()
    with _RUN_LOCK:
        return _CURRENT_RUN_LOG_PATH


def get_run_log_name() -> str:
    """Return the active run log filename."""
    return get_run_log_path().name


def start_new_run_log(run_label: str | None = None) -> Path:
    """Switch logging to a fresh run file and return its path."""
    global _CURRENT_RUN_LOG_PATH
    with _RUN_LOCK:
        _CURRENT_RUN_LOG_PATH = _new_run_log_path(run_label)
        _CURRENT_RUN_LOG_PATH.touch(exist_ok=True)
        return _CURRENT_RUN_LOG_PATH


class _DynamicRunFileHandler(logging.Handler):
    """A file handler that follows the current workflow run path."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            path = get_run_log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(self.format(record) + "\n")
        except Exception:
            self.handleError(record)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured for the local app if needed."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    current_handler = logging.FileHandler(LOG_PATH)
    current_handler.setFormatter(formatter)
    run_handler = _DynamicRunFileHandler()
    run_handler.setFormatter(formatter)
    logger.addHandler(current_handler)
    logger.addHandler(run_handler)
    logger.propagate = False
    return logger


@contextmanager
def log_timing(logger: logging.Logger, label: str, **fields):
    """Log the start/end of a timed operation with optional metadata."""
    start = time.perf_counter()
    if fields:
        meta = " ".join(f"{key}={value}" for key, value in fields.items())
        logger.info("%s start %s", label, meta)
    else:
        logger.info("%s start", label)
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        if fields:
            meta = " ".join(f"{key}={value}" for key, value in fields.items())
            logger.info("%s end elapsed=%.3fs %s", label, elapsed, meta)
        else:
            logger.info("%s end elapsed=%.3fs", label, elapsed)


def read_log_tail(max_lines: int = 120) -> str:
    """Return the tail of the repo-local log file for in-app debugging."""
    if not LOG_PATH.exists():
        return ""
    try:
        lines = LOG_PATH.read_text().splitlines()
    except Exception:
        return ""
    if max_lines <= 0:
        return ""
    return "\n".join(lines[-max_lines:])


def write_debug_artifact(filename: str, content: str) -> Path:
    """Write a repo-local debug artifact next to log.txt and return its path."""
    path = get_run_log_path().parent / filename
    path.write_text(content)
    return path


def list_log_runs(limit: int = 20) -> list[Path]:
    """List timestamped run logs, newest first."""
    if not LOG_DIR.exists():
        return []
    runs = sorted(LOG_DIR.glob("*/Logs_Associated_with_start_of_Run.txt"), reverse=True)
    if limit <= 0:
        return []
    return runs[:limit]


def __getattr__(name: str):
    """Lazy module-level attribute for ``RUN_LOG_PATH``.

    Kept importable via ``from src.utils.logging_utils import RUN_LOG_PATH``
    without eagerly creating the log directory at import time.
    """
    if name == "RUN_LOG_PATH":
        return get_run_log_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
