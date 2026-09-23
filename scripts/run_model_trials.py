#!/usr/bin/env python3
"""Run a bounded, sequential bake-off of local MLX story models.

The runner deliberately starts a fresh pipeline process for each model. That
keeps the comparison fair and guarantees that one model's resident weights do
not share the MLX client's process with the next model. Each trial gets its
own storage root, stream log, and JSON receipt.

Examples:
    # Download both snapshots to a roomy volume, then stop.
    python scripts/run_model_trials.py \
        --download-only \
        --model-root /Volumes/14tb/gravedancer-models

    # Download if needed, then run both models in the listed order.
    python scripts/run_model_trials.py \
        --download \
        --model-root /Volumes/14tb/gravedancer-models \
        --daily-target-tokens 8000 \
        --seed 2

    # Only perform the short, timed generation probe.
    python scripts/run_model_trials.py \
        --smoke-only \
        --model-root /Volumes/14tb/gravedancer-models
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_REPOS = (
    "mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit",
    "mlx-community/Qwen3.8-27B-OptiQ-4bit",
)
DEFAULT_SEED = 2
DEFAULT_DAILY_TARGET_TOKENS = 8_000


def slugify(value: str) -> str:
    """Return a stable, filesystem-safe name for a model or run."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip(".-")
    return slug or "model"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def model_target_dir(model_root: Path, repo_id: str) -> Path:
    """Return the deterministic download directory for a Hub repo."""
    return model_root / slugify(repo_id)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _file_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _snapshot_download(repo_id: str, target: Path) -> Path:
    """Download or resume a Hub snapshot into *target*.

    Importing ``huggingface_hub`` only when the user explicitly requests a
    download keeps normal trial execution offline and lightweight.
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "huggingface_hub is required for --download; install requirements "
            "or run this from the project venv"
        ) from exc

    target.mkdir(parents=True, exist_ok=True)
    downloaded = snapshot_download(repo_id=repo_id, local_dir=str(target))
    return Path(downloaded)


def prepare_model(repo_id: str, model_root: Path) -> Path:
    """Download/resume one model and return its local directory."""
    supplied_path = Path(repo_id).expanduser()
    if supplied_path.is_dir():
        return supplied_path.resolve()
    target = model_target_dir(model_root, repo_id)
    print(f"[download] {repo_id} -> {target}", flush=True)
    resolved = _snapshot_download(repo_id, target)
    print(f"[download] ready: {resolved} ({_file_bytes(resolved) / (1024 ** 3):.2f} GiB)", flush=True)
    return resolved


def _episode_summary(storage_root: Path) -> dict[str, Any]:
    """Collect simple output evidence without interpreting prose quality."""
    episodes_root = storage_root / "episodes"
    metadata_files = sorted(episodes_root.glob("*/metadata.json")) if episodes_root.is_dir() else []
    episodes: list[dict[str, Any]] = []
    for metadata_path in metadata_files:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        story_path = metadata_path.with_name("story.md")
        try:
            story_chars = story_path.stat().st_size if story_path.exists() else 0
        except OSError:
            story_chars = 0
        episodes.append({
            "id": metadata_path.parent.name,
            "title": metadata.get("title", ""),
            "pipeline_complete": bool(metadata.get("pipeline_complete")),
            "word_count": metadata.get("word_count"),
            "story_chars": story_chars,
            "story_path": str(story_path),
        })
    return {
        "episode_count": len(episodes),
        "completed_count": sum(1 for episode in episodes if episode["pipeline_complete"]),
        "episodes": episodes,
        "checkpoint_count": len(list((episodes_root / ".checkpoints").glob("*.json")))
        if (episodes_root / ".checkpoints").is_dir()
        else 0,
    }


def _pipeline_env(
    *,
    trial_storage: Path,
    model_path: Path,
    daily_target_tokens: int,
) -> dict[str, str]:
    """Build a reproducible, offline environment for one pipeline process."""
    # logging_utils opens its aggregate log during module import, before the
    # pipeline creates EpisodeStorage. Make the parent available first.
    trial_storage.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for key in (
        "GRAVEDANCER_MODEL_OUTLINE",
        "GRAVEDANCER_MODEL_STORY",
        "GRAVEDANCER_MODEL_RECAP",
        "GRAVEDANCER_MODEL_VISUAL",
    ):
        env.pop(key, None)
    env.update({
        "GRAVEDANCER_MODEL": str(model_path),
        "GRAVEDANCER_STORAGE_PATH": str(trial_storage / "episodes"),
        "GRAVEDANCER_LOG_PATH": str(trial_storage / "log"),
        "GRAVEDANCER_DAILY_TARGET_TOKENS": str(daily_target_tokens),
        "GRAVEDANCER_FAST": "1",
        # The snapshot is already prepared. A trial must not silently fetch a
        # different revision halfway through the comparison.
        "GRAVEDANCER_ALLOW_MODEL_DOWNLOADS": "0",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONUNBUFFERED": "1",
    })
    return env


def pipeline_command(model_path: Path, seed: int) -> list[str]:
    """Return the exact command used for one full story trial."""
    return [
        sys.executable,
        str(PROJECT_ROOT / "run_creative_pipeline.py"),
        "--seed",
        str(seed),
        "--model",
        str(model_path),
    ]


def smoke_command(model_path: Path, max_tokens: int, report_path: Path) -> list[str]:
    """Return the short fixed-prompt command used for throughput metrics."""
    return [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "benchmark_model.py"),
        "--model",
        str(model_path),
        "--max-tokens",
        str(max_tokens),
        "--output",
        str(report_path),
    ]


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    """Stop a child pipeline and its descendants after an interactive stop."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        try:
            process.terminate()
        except OSError:
            return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            process.kill()
        process.wait(timeout=10)


def run_smoke_trial(
    *,
    repo_id: str,
    model_path: Path,
    trial_root: Path,
    max_tokens: int,
) -> dict[str, Any]:
    """Run the fixed short benchmark before the expensive story trial."""
    label = slugify(repo_id)
    smoke_dir = trial_root / label
    smoke_dir.mkdir(parents=True, exist_ok=True)
    log_path = smoke_dir / "smoke.log"
    report_path = smoke_dir / "smoke.json"
    command = smoke_command(model_path, max_tokens, report_path)
    env = _pipeline_env(
        trial_storage=smoke_dir / "smoke-storage",
        model_path=model_path,
        daily_target_tokens=8_000,
    )
    started_at = utc_now()
    started = time.perf_counter()
    returncode: int | None = None
    status = "failed"

    print(f"\n[smoke {label}] starting {max_tokens}-token timing probe", flush=True)
    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    try:
        assert process.stdout is not None
        with log_path.open("w", encoding="utf-8") as log_handle:
            for line in process.stdout:
                log_handle.write(line)
                log_handle.flush()
                print(f"[{label}/smoke] {line}", end="", flush=True)
        returncode = process.wait()
        status = "passed" if returncode == 0 else "failed"
    except KeyboardInterrupt:
        print(f"\n[smoke {label}] stopping child process", flush=True)
        _terminate_process_group(process)
        returncode = process.returncode
        status = "interrupted"

    metrics: dict[str, Any] = {}
    if report_path.exists():
        try:
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                metrics = loaded
        except (OSError, json.JSONDecodeError):
            pass
    receipt = {
        "repo_id": repo_id,
        "model_path": str(model_path),
        "max_tokens": max_tokens,
        "command": command,
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "returncode": returncode,
        "status": status,
        "log_path": str(log_path),
        "metrics": metrics,
    }
    _write_json(smoke_dir / "smoke-receipt.json", receipt)
    print(
        f"[smoke {label}] {status} in {receipt['duration_seconds']:.1f}s "
        f"(receipt={smoke_dir / 'smoke-receipt.json'})",
        flush=True,
    )
    return receipt


def run_trial(
    *,
    repo_id: str,
    model_path: Path,
    trial_root: Path,
    seed: int,
    daily_target_tokens: int,
) -> dict[str, Any]:
    """Run one model to completion and write its receipt."""
    label = slugify(repo_id)
    trial_dir = trial_root / label
    trial_dir.mkdir(parents=True, exist_ok=True)
    log_path = trial_dir / "pipeline.log"
    receipt_path = trial_dir / "trial.json"
    storage_root = trial_dir / "storage"
    command = pipeline_command(model_path, seed)
    env = _pipeline_env(
        trial_storage=storage_root,
        model_path=model_path,
        daily_target_tokens=daily_target_tokens,
    )
    started_at = utc_now()
    started = time.perf_counter()
    status = "failed"
    returncode: int | None = None

    print(f"\n[trial {label}] starting sequential pipeline", flush=True)
    print(f"[trial {label}] model={model_path}", flush=True)
    print(f"[trial {label}] log={log_path}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    try:
        assert process.stdout is not None
        with log_path.open("w", encoding="utf-8") as log_handle:
            for line in process.stdout:
                log_handle.write(line)
                log_handle.flush()
                print(f"[{label}] {line}", end="", flush=True)
        returncode = process.wait()
        status = "passed" if returncode == 0 else "failed"
    except KeyboardInterrupt:
        print(f"\n[trial {label}] stopping child process", flush=True)
        _terminate_process_group(process)
        returncode = process.returncode
        status = "interrupted"

    finished_at = utc_now()
    receipt = {
        "repo_id": repo_id,
        "model_path": str(model_path),
        "seed": seed,
        "daily_target_tokens": daily_target_tokens,
        "command": command,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "returncode": returncode,
        "status": status,
        "log_path": str(log_path),
        "storage_root": str(storage_root),
        "disk_free_bytes_after": shutil.disk_usage(PROJECT_ROOT).free,
        "output": _episode_summary(storage_root),
    }
    _write_json(receipt_path, receipt)
    print(
        f"[trial {label}] {status} in {receipt['duration_seconds']:.1f}s "
        f"(receipt={receipt_path})",
        flush=True,
    )
    return receipt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        help="Model Hub repo or local path; repeat for a custom sequential order.",
    )
    parser.add_argument(
        "--model-root",
        type=Path,
        default=Path(os.environ.get("GRAVEDANCER_TRIAL_MODEL_ROOT", PROJECT_ROOT / ".trial-models")),
        help="Directory holding downloaded snapshots (used by --download).",
    )
    parser.add_argument(
        "--trial-root",
        type=Path,
        default=PROJECT_ROOT / "trial-runs",
        help="Directory for logs, storage, and receipts.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--daily-target-tokens",
        type=int,
        default=DEFAULT_DAILY_TARGET_TOKENS,
        help="Bounded story target per day; values below 8000 are rejected by the pipeline schema.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download/resume all model snapshots before running trials.",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Prepare snapshots and write a manifest without running story trials.",
    )
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="Run the short timed generation probe but skip full story generation.",
    )
    parser.add_argument(
        "--smoke-max-tokens",
        type=int,
        default=512,
        help="Output ceiling for the fixed smoke probe (32-4096).",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop after the first failed model trial instead of recording the remaining models as pending.",
    )
    args = parser.parse_args()
    if args.daily_target_tokens < 8_000:
        parser.error("--daily-target-tokens must be at least 8000")
    if args.download_only:
        args.download = True
    if not 32 <= args.smoke_max_tokens <= 4096:
        parser.error("--smoke-max-tokens must be between 32 and 4096")
    if not args.models:
        args.models = list(DEFAULT_MODEL_REPOS)
    return args


def main() -> int:
    args = _parse_args()
    model_root = args.model_root.expanduser().resolve()
    trial_root = args.trial_root.expanduser().resolve()
    trial_root.mkdir(parents=True, exist_ok=True)

    resolved_models: dict[str, str] = {}
    preparation_errors: dict[str, str] = {}
    for repo_id in args.models:
        try:
            if args.download:
                resolved = prepare_model(repo_id, model_root)
            else:
                supplied_path = Path(repo_id).expanduser()
                cached_path = model_target_dir(model_root, repo_id)
                if supplied_path.is_dir():
                    resolved = supplied_path.resolve()
                elif cached_path.is_dir():
                    resolved = cached_path.resolve()
                else:
                    resolved = Path(repo_id)
            resolved_models[repo_id] = str(resolved)
        except Exception as exc:  # keep the finite batch moving to the next model
            preparation_errors[repo_id] = str(exc)
            print(f"[download] FAILED {repo_id}: {exc}", file=sys.stderr, flush=True)

    manifest: dict[str, Any] = {
        "created_at": utc_now(),
        "project_root": str(PROJECT_ROOT),
        "model_root": str(model_root),
        "trial_root": str(trial_root),
        "seed": args.seed,
        "daily_target_tokens": args.daily_target_tokens,
        "smoke_max_tokens": args.smoke_max_tokens,
        "smoke_only": args.smoke_only,
        "models": list(args.models),
        "resolved_models": resolved_models,
        "preparation_errors": preparation_errors,
        "trials": [],
    }
    manifest_path = trial_root / "manifest.json"
    _write_json(manifest_path, manifest)

    if args.download_only:
        print(f"\n[download] manifest={manifest_path}", flush=True)
        return 0 if not preparation_errors else 1

    exit_code = 0
    for repo_id in args.models:
        model_path_text = resolved_models.get(repo_id)
        if not model_path_text:
            result = {
                "repo_id": repo_id,
                "status": "blocked",
                "reason": preparation_errors.get(repo_id, "model preparation failed"),
            }
            manifest["trials"].append(result)
            _write_json(manifest_path, manifest)
            exit_code = 1
            if args.stop_on_error:
                break
            continue

        model_path = Path(model_path_text)
        smoke = run_smoke_trial(
            repo_id=repo_id,
            model_path=model_path,
            trial_root=trial_root,
            max_tokens=args.smoke_max_tokens,
        )
        result = {"repo_id": repo_id, "smoke": smoke}
        if args.smoke_only:
            result["status"] = smoke["status"]
        else:
            full = run_trial(
                repo_id=repo_id,
                model_path=model_path,
                trial_root=trial_root,
                seed=args.seed,
                daily_target_tokens=args.daily_target_tokens,
            )
            result["full"] = full
            result["status"] = full["status"]
        manifest["trials"].append(result)
        _write_json(manifest_path, manifest)
        if result["status"] != "passed":
            exit_code = 1
            if args.stop_on_error:
                break

    print(f"\n[trial batch] manifest={manifest_path}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
