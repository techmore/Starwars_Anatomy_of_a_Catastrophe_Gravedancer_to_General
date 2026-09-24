"""Run a bounded local-model benchmark without creating an episode.

Example:
    python3 scripts/benchmark_model.py --model lmstudio:ornith-1.5-9b-mlx
"""

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.mlx_client import BONSAI_1BIT_MODEL, MLXClient
from src.utils.models import normalize_model_name
from src.utils.settings import SETTINGS

DEFAULT_PROMPT = (
    "Write a 250-word atmospheric opening scene for a science-fiction pursuit. "
    "Output prose only, with no headings, analysis, or explanation."
)


def run_benchmark(model: str, max_tokens: int, prompt: str) -> dict:
    """Measure load latency separately from generation latency when possible."""
    client = MLXClient(model)
    started = time.perf_counter()
    load_seconds = None
    normalized_model = normalize_model_name(model)
    has_python_api = getattr(client, "_has_python_api", None)
    ensure_model_loaded = getattr(client, "_ensure_model_loaded", None)
    external_prefixes = ("lmstudio:", "opencode:", "nous:")
    if (
        callable(has_python_api)
        and callable(ensure_model_loaded)
        and has_python_api()
        and not str(model).startswith(external_prefixes)
        and normalized_model != BONSAI_1BIT_MODEL
    ):
        load_started = time.perf_counter()
        ensure_model_loaded(normalized_model)
        load_seconds = time.perf_counter() - load_started
    generation_started = time.perf_counter()
    first_token_at = None
    chunks = []
    for chunk in client.generate_stream(
        model=model,
        prompt=prompt,
        system="You are a fiction benchmark. Output only the requested prose. /no_think",
        temperature=0.7,
        max_tokens=max_tokens,
    ):
        if first_token_at is None:
            first_token_at = time.perf_counter()
        chunks.append(chunk)
    ended = time.perf_counter()
    text = "".join(chunks)
    elapsed = ended - started
    generation_elapsed = ended - generation_started
    approx_tokens = round(len(text) / 4)
    return {
        "model": model,
        "max_tokens": max_tokens,
        "load_seconds": round(load_seconds, 3) if load_seconds is not None else None,
        "first_token_seconds": round((first_token_at - started) if first_token_at else elapsed, 3),
        "generation_first_token_seconds": round(
            (first_token_at - generation_started) if first_token_at else generation_elapsed,
            3,
        ),
        "total_seconds": round(elapsed, 3),
        "generation_seconds": round(generation_elapsed, 3),
        "characters": len(text),
        "approx_tokens": approx_tokens,
        "approx_tokens_per_second": round(approx_tokens / generation_elapsed, 2) if generation_elapsed else 0.0,
        "end_to_end_approx_tokens_per_second": round(approx_tokens / elapsed, 2) if elapsed else 0.0,
        "words": len(text.split()),
        "success": bool(text.strip()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=SETTINGS.model, help="Model ID, including lmstudio: prefix when needed")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    if args.max_tokens < 32 or args.max_tokens > 4096:
        parser.error("--max-tokens must be between 32 and 4096 for a bounded benchmark")
    try:
        report = run_benchmark(args.model, args.max_tokens, args.prompt)
    except Exception as exc:
        report = {"model": args.model, "success": False, "error": str(exc)}
        print(json.dumps(report, indent=2))
        return 1
    serialized = json.dumps(report, indent=2)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
