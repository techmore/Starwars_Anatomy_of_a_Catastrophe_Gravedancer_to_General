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


# Per-stage model routing: outline on the strongest plot model, prose on the
# best writer, recap/visual work on a cheap fast model. Precedence per stage:
# explicit CLI flag > GRAVEDANCER_MODEL_<STAGE> env > the run's main model.
STAGE_MODEL_ENV_VARS = {
    "outline": "GRAVEDANCER_MODEL_OUTLINE",
    "story": "GRAVEDANCER_MODEL_STORY",
    "recap": "GRAVEDANCER_MODEL_RECAP",
    "visual": "GRAVEDANCER_MODEL_VISUAL",
}


def stage_model(stage: str, main_model: str, override: str = "") -> str:
    """Resolve the model for a pipeline stage (CLI override > env > main)."""
    candidate = (override or "").strip()
    if candidate:
        return candidate
    env_name = STAGE_MODEL_ENV_VARS.get(stage, "")
    candidate = os.environ.get(env_name, "").strip() if env_name else ""
    return candidate or main_model


SETTINGS = load_settings()
