"""Run the creative pipeline with ox-alpha (in-session LLM) as the generation backend.

Mirrors run_creative_pipeline.py stage-for-stage, but replaces the MLX client
with OxAlphaBackend, which serves pre-authored responses from a run directory.
Every prompt the pipeline would send to a local model is written to
.oxalpha-run/prompts/ for inspection, and every response is consumed through
the real TextGenerationBackend interface, so validation, parsing, checkpoint
formatting, and storage behave exactly as in a native run.

Usage:
    python scripts/run_oxalpha_pipeline.py [--seed 42] [--run-dir .oxalpha-run]
"""

import argparse
import json
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.creative_tables import generate_creative_seed
from src.utils.logging_utils import get_logger
from src.utils.story_generator import StoryGenerator
from src.utils.storage import EpisodeStorage
from src.utils.prompt_generator import PromptGenerator
from src.utils.settings import SETTINGS
from src.utils.prompt_schema import validate_outline_structure

LOGGER = get_logger(__name__)

MODEL_ID = "ox-alpha (in-session LLM)"


class MissingResponseError(RuntimeError):
    """Raised when the model seat has not filled in a required response."""


class OxAlphaBackend:
    """TextGenerationBackend backed by authored response files.

    Requests are mapped to response files by stable markers in the prompt:
      - outline:        responses/outline.md
      - day section:    responses/day{d}-s{i}.md
      - banner:         responses/banner.md
      - chapter prompt: responses/chap-d{d}-c{c}.md
    """

    def __init__(self, run_dir: Path, collect_prompts: bool = True):
        self.response_dir = run_dir / "responses"
        self.prompt_dir = run_dir / "prompts"
        self.prompt_dir.mkdir(parents=True, exist_ok=True)
        self.collect_prompts = collect_prompts
        self.calls: list[Dict[str, str]] = []
        self._counter = 0

    def resolve_response_path(self, prompt: str) -> Path:
        marker = re.search(r"Plan a (\d+)-day episode", prompt)
        if marker:
            return self.response_dir / "outline.md"
        marker = re.search(r"Expand Section (\d+) of Day (\d+) into prose", prompt)
        if marker:
            section, day = int(marker.group(1)), int(marker.group(2))
            return self.response_dir / f"day{day}-s{section}.md"
        if "banner image prompt" in prompt:
            return self.response_dir / "banner.md"
        marker = re.search(r"\*\*CHAPTER:\*\* Day (\d+), Chapter (\d+)", prompt)
        if marker:
            day, chapter = int(marker.group(1)), int(marker.group(2))
            return self.response_dir / f"chap-d{day}-c{chapter}.md"
        raise MissingResponseError("Unrecognized prompt shape; cannot map to a response file.")

    def _record(self, prompt: str) -> Path:
        self._counter += 1
        path = self.resolve_response_path(prompt)
        if self.collect_prompts:
            slug = f"{self._counter:03d}-{path.stem}.txt"
            (self.prompt_dir / slug).write_text(prompt, encoding="utf-8")
        self.calls.append({"response": str(path), "prompt_chars": len(prompt)})
        return path

    def _load(self, prompt: str) -> str:
        path = self._record(prompt)
        if not path.is_file():
            raise MissingResponseError(
                f"Model seat has not answered yet: expected {path}"
            )
        return path.read_text(encoding="utf-8").strip()

    def generate_stream(self, *, model: str, prompt: str, system: str | None = None,
                        temperature: float = 0.7, top_p: float = 0.9,
                        max_tokens: int = 4096, **_: Any):
        text = self._load(prompt)
        for i in range(0, len(text), 240):
            yield text[i:i + 240]

    def generate(self, *, model: str, prompt: str, system: str | None = None,
                 temperature: float = 0.7, top_p: float = 0.9,
                 max_tokens: int = 4096, stream: bool = False, **_: Any) -> str:
        return self._load(prompt)


def _map_seed_to_metadata(seed: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": seed["title"],
        "num_days": seed["num_days"],
        "setting": seed["setting"],
        "tone_focus": seed["tone_focus"],
        "jedi_name": seed["jedi_name"],
        "jedi_species": seed["jedi_species"],
        "jedi_rank": seed["jedi_rank"],
        "jedi_lightsaber_color": seed["jedi_lightsaber_color"],
        "jedi_personality": seed["jedi_personality"],
        "jedi_target": seed["jedi_why_targeted"],
        "target_jedi_name": seed["jedi_name"],
        "seed_value": seed["seed"],
        "story_arc": seed["story_arc"],
        "story_conflict": seed["story_conflict"],
        "story_resolution": seed["story_resolution"],
        "transformation_arc": seed["transformation_arc"],
        "pipeline": "oxalpha-in-session-v1",
        "model_outline": MODEL_ID,
        "model_story": MODEL_ID,
        "model_banner": MODEL_ID,
        "model_chapters": MODEL_ID,
        "model_scenes": "",
    }


def main(seed_value: int, run_dir: Path) -> int:
    print("=" * 72)
    print("  GRAVEDANCER -> GENERAL — OX-ALPHA IN-SESSION PIPELINE RUN")
    print("=" * 72)

    seed = generate_creative_seed(seed=seed_value)
    print(f"\nCreative seed {seed['seed']}: \"{seed['title']}\" "
          f"({seed['num_days']} days, Jedi: {seed['jedi_name']})")

    backend = OxAlphaBackend(run_dir)
    mlx = backend  # same protocol surface
    story_gen = StoryGenerator(mlx)
    prompt_gen = PromptGenerator(mlx)
    storage = EpisodeStorage(str(SETTINGS.storage_path))
    metadata = _map_seed_to_metadata(seed)

    checkpoint_scope = f"oxalpha:{seed_value}:{uuid.uuid4().hex[:8]}"
    resumed = next(
        (
            loaded
            for entry in storage.list_checkpoints()
            if entry.get("title") == seed["title"]
            and (loaded := storage.load_checkpoint(entry.get("path", "")))
            and (loaded.get("metadata") or {}).get("num_days") in (None, seed["num_days"])
        ),
        None,
    )
    day_drafts: Dict[int, str] = {}
    draft_only = False
    if resumed:
        drafts = resumed.get("day_drafts") or {}
        day_drafts = {int(day): str(text) for day, text in drafts.items()}
        draft_only = True
        metadata["resumed_from_checkpoint"] = datetime.now().isoformat()
        print(f"  [checkpoint] resuming with {len(day_drafts)} completed day(s)", flush=True)

    def save_day_checkpoint(day_number: int, day_text: str) -> None:
        day_drafts[day_number] = day_text
        path = storage.save_checkpoint(
            title=seed["title"],
            metadata=metadata,
            day_drafts=day_drafts,
            outline=outline,
            scope=checkpoint_scope,
        )
        LOGGER.info("Story checkpoint saved path=%s day=%s", path, day_number)

    jedi_details = {
        "name": seed["jedi_name"],
        "species": seed["jedi_species"],
        "rank": seed["jedi_rank"],
        "lightsaber_color": seed["jedi_lightsaber_color"],
        "personality": seed["jedi_personality"],
        "why_targeted": seed["jedi_why_targeted"],
    }
    additional_instructions = (
        f"Story Arc: {seed['story_arc']}\n"
        f"Conflict: {seed['story_conflict']}\n"
        f"Resolution: {seed['story_resolution']}\n"
        f"Transformation: {seed['transformation_arc']}\n"
        "This episode was created by structured randomization; expand the seeds "
        "into coherent prose."
    )

    def log(stage: str, msg: str) -> None:
        print(f"  [{stage}] {msg}", flush=True)

    # ── Phase 1: outline ────────────────────────────────────────────────
    t0 = time.perf_counter()
    if draft_only and (resumed.get("outline") or "").strip():
        outline = resumed["outline"].strip()
        log("outline", f"reused from checkpoint ({len(outline):,} chars)")
    else:
        log("outline", "requesting outline from model seat...")
        outline = story_gen.generate_episode_outline(
            model=MODEL_ID,
            title=seed["title"],
            num_days=seed["num_days"],
            jedi_details=jedi_details,
            setting=seed["setting"],
            tone_focus=seed["tone_focus"],
            additional_instructions=additional_instructions,
            temperature=0.6,
        )
        errors = validate_outline_structure(outline, expected_days=seed["num_days"])
        if errors:
            print(f"OUTLINE REJECTED by repository validator: {errors}", file=sys.stderr)
            return 2
        log("outline", f"validated ({len(outline):,} chars) in {time.perf_counter() - t0:.1f}s")

    # ── Phase 2: multi-pass story ───────────────────────────────────────
    t0 = time.perf_counter()
    story = story_gen.generate_episode_story_multi_pass(
        model=MODEL_ID,
        title=seed["title"],
        num_days=seed["num_days"],
        jedi_details=jedi_details,
        setting=seed["setting"],
        tone_focus=seed["tone_focus"],
        additional_instructions=additional_instructions,
        temperature=0.8,
        outline=outline,
        day_drafts=day_drafts or None,
        draft_only=draft_only,
        progress_callback=lambda stage, message, text="": log(stage, message)
        if text == "" else None,
        checkpoint_callback=save_day_checkpoint,
    )
    log("story", f"multi-pass complete ({len(story.split()):,} words) "
                 f"in {time.perf_counter() - t0:.1f}s")
    for d in story_gen.parse_days(story):
        log("story", f"DAY {d['number']:>2}: {d['word_count']:>6,} words — {d['title']}")

    # ── Phase 3: chapters ───────────────────────────────────────────────
    chapters = prompt_gen.extract_chapters(story)
    log("chapters", f"extracted {len(chapters)} chapters")

    # ── Phase 4: banner ─────────────────────────────────────────────────
    banner_result = prompt_gen.generate_banner_prompt(metadata=metadata, model=MODEL_ID)
    log("banner", f"{len(banner_result['banner_prompt'])} chars")

    # ── Phase 5: chapter prompts ────────────────────────────────────────
    chapter_prompts = []
    for ch in chapters:
        result = prompt_gen.generate_chapter_prompt(
            chapter_text=ch["text"],
            day_number=ch["day"],
            chapter_index=ch["chapter_index"],
            chapter_title=ch["chapter_title"],
            model=MODEL_ID,
        )
        result["day"] = ch["day"]
        result["chapter_index"] = ch["chapter_index"]
        result["chapter_title"] = ch["chapter_title"]
        empty = [k for k in ("wide", "medium", "closeup") if not result.get(k)]
        if empty:
            log("warn", f"d{ch['day']} c{ch['chapter_index']}: unparsed shots {empty}")
        chapter_prompts.append(result)
    log("chapters", f"{len(chapter_prompts)} visual prompt sets parsed")

    prompts_payload = {
        "banner": {
            "prompt": banner_result["banner_prompt"],
            "negative_prompt": banner_result["negative_prompt"],
        },
        "chapters": chapter_prompts,
        "scenes": [],
        "generated_at": datetime.now().isoformat(),
        "pipeline": "oxalpha-in-session-v1",
        "model": MODEL_ID,
    }

    episode_id = storage.save_episode(
        title=seed["title"], story=story, metadata=metadata, prompts=prompts_payload,
    )
    for entry in storage.list_checkpoints():
        if entry.get("title") == seed["title"]:
            storage.delete_checkpoint_file(entry.get("path", ""))
    print("\n" + "=" * 72)
    print(f"  PIPELINE COMPLETE — episode saved: episodes/{episode_id}/")
    print(f"  Words: {len(story.split()):,} | Chapters: {len(chapters)} | "
          f"Model calls: {len(backend.calls)}")
    print("=" * 72)
    (run_dir / "call-log.json").write_text(
        json.dumps(backend.calls, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run-dir", type=Path, default=Path(".oxalpha-run"))
    args = parser.parse_args()
    sys.exit(main(args.seed, args.run_dir))
