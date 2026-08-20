"""Application settings and deterministic project paths.

The UI, CLI, and pilot workflows all use this module for shared defaults.
Environment variables are intentionally small and explicit so local runs stay
reproducible without requiring a configuration framework.
"""

from dataclasses import dataclass
import os
from pathlib import Path

from src.utils.models import DEFAULT_MODEL


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else default


@dataclass(frozen=True)
class AppSettings:
    """Resolved settings shared by application entrypoints."""

    model: str = DEFAULT_MODEL
    storage_path: Path = PROJECT_ROOT / "episodes"
    log_path: Path = PROJECT_ROOT / "log"


def load_settings() -> AppSettings:
    """Load settings from environment variables with repository-local defaults."""
    return AppSettings(
        model=os.environ.get("GRAVEDANCER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        storage_path=_path_from_env("GRAVEDANCER_STORAGE_PATH", PROJECT_ROOT / "episodes"),
        log_path=_path_from_env("GRAVEDANCER_LOG_PATH", PROJECT_ROOT / "log"),
    )


SETTINGS = load_settings()
