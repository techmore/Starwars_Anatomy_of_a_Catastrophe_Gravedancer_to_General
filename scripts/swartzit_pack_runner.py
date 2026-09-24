"""Optional Swartzit adapter for the generalized content-package protocol.

The Swartzit worker launches this file as an external process. It emits
human-readable pipeline logs plus JSONL frames; the worker ignores the former
and uses the latter for progress, day checkpoints, and the final package.

The adapter is intentionally a small registry. A future story, newsletter,
course, or image pack can add another pack implementation without adding a
dependency to Swartzit's server or web install.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.swartzit_package import (  # noqa: E402
    STARWARS_PACK_ID,
    STARWARS_PACK_VERSION,
    episode_to_package,
)


_MAC_DEFAULT_MODEL = "mlx-community/gemma-4-e4b-it-OptiQ-4bit"
_MAC_DEFAULT_RECAP_MODEL = "mlx-community/gemma-4-e2b-it-OptiQ-4bit"
_LINUX_DEFAULT_MODEL = "ollama:gemma4:e4b"

# Keep the pack portable without changing the Mac-first interactive app. The
# host can still override every stage through RUNNER_PACK_OPTIONS_JSON, while
# a source install on Ubuntu naturally selects its local Ollama model.
def _env_model_default(*names: str, fallback: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return fallback


DEFAULT_MODEL = _env_model_default(
    "GRAVEDANCER_PACK_DEFAULT_MODEL",
    "GRAVEDANCER_MODEL",
    fallback=_LINUX_DEFAULT_MODEL if sys.platform.startswith("linux") else _MAC_DEFAULT_MODEL,
)
DEFAULT_RECAP_MODEL = _env_model_default(
    "GRAVEDANCER_PACK_DEFAULT_RECAP_MODEL",
    "GRAVEDANCER_MODEL_RECAP",
    fallback=_LINUX_DEFAULT_MODEL if sys.platform.startswith("linux") else _MAC_DEFAULT_RECAP_MODEL,
)


def emit(frame: dict[str, Any]) -> None:
    print(json.dumps(frame, ensure_ascii=False, separators=(",", ":")), flush=True)


def _options() -> dict[str, Any]:
    raw = os.environ.get("RUNNER_PACK_OPTIONS_JSON", "{}").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"RUNNER_PACK_OPTIONS_JSON is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("RUNNER_PACK_OPTIONS_JSON must be an object")
    return value


def _resume_checkpoint() -> dict[str, Any] | None:
    raw = os.environ.get("RUNNER_RESUME_CHECKPOINT_JSON", "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"RUNNER_RESUME_CHECKPOINT_JSON is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("RUNNER_RESUME_CHECKPOINT_JSON must be an object")
    return value


def _set_optional_draw_things_environment(options: dict[str, Any]) -> None:
    draw = options.get("draw_things") or {}
    if not isinstance(draw, dict) or not options.get("generate_images", False):
        return
    os.environ["GRAVEDANCER_DT_BACKEND"] = str(draw.get("backend") or "cli")
    for key, env_name in (
        ("binary", "GRAVEDANCER_DT_CLI_BIN"),
        ("model", "GRAVEDANCER_DT_CLI_MODEL"),
        ("models_dir", "DRAWTHINGS_MODELS_DIR"),
        ("style_profile", "GRAVEDANCER_STYLE_PROFILE"),
    ):
        value = str(draw.get(key) or "").strip()
        if value:
            os.environ[env_name] = value
    backend = os.environ["GRAVEDANCER_DT_BACKEND"].strip().lower()
    if backend in {"comfy", "comfyui", "comfy-ui"}:
        for key, env_name in (
            ("url", "GRAVEDANCER_COMFYUI_URL"),
            ("workflow", "GRAVEDANCER_COMFYUI_WORKFLOW_JSON"),
            ("model", "GRAVEDANCER_COMFYUI_MODEL"),
            ("timeout", "GRAVEDANCER_COMFYUI_TIMEOUT"),
        ):
            raw_value = draw.get(key)
            if key == "url" and not raw_value:
                raw_value = draw.get("base_url")
            value = str(raw_value or "").strip()
            if value:
                os.environ[env_name] = value
    loras = draw.get("loras")
    if isinstance(loras, list):
        os.environ["GRAVEDANCER_DT_CLI_LORAS_JSON"] = json.dumps(loras)


def run_starwars(options: dict[str, Any]) -> str | None:
    # Set storage before importing the pipeline: its settings object is
    # intentionally resolved once per process for reproducible local runs.
    storage_path = str(options.get("storage_path") or (ROOT / "episodes"))
    os.environ["GRAVEDANCER_STORAGE_PATH"] = str(Path(storage_path).expanduser())
    if options.get("fast", True):
        os.environ["GRAVEDANCER_FAST"] = "1"
    _set_optional_draw_things_environment(options)

    from run_creative_pipeline import main  # noqa: PLC0415

    draw = options.get("draw_things") if isinstance(options.get("draw_things"), dict) else {}
    pack_model = str(options.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    story_model = str(options.get("story_model") or pack_model).strip() or pack_model
    recap_model = str(options.get("recap_model") or DEFAULT_RECAP_MODEL).strip() or DEFAULT_RECAP_MODEL
    visual_model = str(options.get("visual_model") or recap_model).strip() or recap_model
    seed = int(options.get("seed", os.environ.get("RUNNER_SEED", "42")))
    days = options.get("days")
    if days is not None:
        days = int(days)
        if not 3 <= days <= 8:
            raise ValueError("Star Wars pack days must be between 3 and 8")

    resume = _resume_checkpoint()
    if resume:
        completed_days = int(resume.get("completed_days", 0) or 0)
        total_days = int(resume.get("total_days", days or 7) or 7)
        resume_percent = min(99, max(1, round(100 * completed_days / max(total_days, 1))))
        emit({
            "type": "progress",
            "phase": "resume",
            "message": f"Resuming from the completed Day {completed_days} checkpoint",
            "percent": resume_percent,
        })

    emit({"type": "progress", "phase": "pack", "message": f"Starting {STARWARS_PACK_ID}", "percent": 1})
    episode_id = main(
        seed_value=seed,
        model=pack_model,
        story_model=story_model,
        recap_model=recap_model,
        visual_model=visual_model,
        num_days=days,
        generate_images=bool(options.get("generate_images", False)),
        image_mode=str(options.get("image_mode") or "day"),
        max_images=int(options["max_images"]) if options.get("max_images") is not None else None,
        generate_refs=bool(options.get("generate_refs", False)),
        image_width=int(draw.get("width", 1024)),
        image_height=int(draw.get("height", 576)),
        image_steps=int(draw.get("steps", 5)),
        image_cfg=float(draw["cfg"]) if draw.get("cfg") is not None else 1.4,
    )
    if not episode_id:
        emit({"type": "cancelled", "message": "Generation stopped; the latest completed day remains checkpointed."})
        return None
    package = episode_to_package(Path(storage_path) / episode_id)
    emit({"type": "package", "package": package})
    return episode_id


def backfill(episode_path: str) -> int:
    package = episode_to_package(episode_path)
    if os.environ.get("SWARTZIT_RUNNER_PROTOCOL", "").strip().lower() == "jsonl":
        emit({"type": "package", "package": package})
        return 0
    print(json.dumps(package, ensure_ascii=False, indent=2))
    return 0


def main_cli() -> int:
    parser = argparse.ArgumentParser(description="Run an optional Swartzit content pack")
    parser.add_argument("--pack", default=STARWARS_PACK_ID)
    parser.add_argument("--backfill", help="Convert an existing episode directory to content-package.v1")
    args = parser.parse_args()
    if args.backfill:
        return backfill(args.backfill)
    if args.pack != STARWARS_PACK_ID:
        raise SystemExit(f"Unknown pack: {args.pack}")
    run_starwars(_options())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main_cli())
    except KeyboardInterrupt:
        emit({"type": "cancelled", "message": "Interrupted"})
        raise SystemExit(130)
    except Exception as exc:
        emit({"type": "error", "message": str(exc)})
        raise SystemExit(1)
