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

from src.utils.mlx_client import MLXClient
from src.utils.settings import SETTINGS

DEFAULT_PROMPT = (
    "Write a 250-word atmospheric opening scene for a science-fiction pursuit. "
    "Output prose only, with no headings, analysis, or explanation."
)


def run_benchmark(model: str, max_tokens: int, prompt: str) -> dict:
    """Measure first-token latency, total latency, output size, and rate."""
    client = MLXClient(model)
    started = time.perf_counter()
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
    approx_tokens = round(len(text) / 4)
    return {
        "model": model,
        "max_tokens": max_tokens,
        "first_token_seconds": round((first_token_at - started) if first_token_at else elapsed, 3),
        "total_seconds": round(elapsed, 3),
        "characters": len(text),
        "approx_tokens": approx_tokens,
        "approx_tokens_per_second": round(approx_tokens / elapsed, 2) if elapsed else 0.0,
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
