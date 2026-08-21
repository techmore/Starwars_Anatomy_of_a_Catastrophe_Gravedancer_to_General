"""Run the full story pipeline from a structured creative seed.

Usage:
    python run_creative_pipeline.py [--seed SEED] [--model MODEL]

The seed is generated from the creative randomization tables, then expanded
by the LLM into a full episode with outline → story → banner → chapter prompts.
"""

import argparse
import atexit
import json
import signal
import sys
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from src.utils.creative_tables import generate_creative_seed
from src.utils.logging_utils import get_logger
from src.utils.mlx_client import MLXClient
from src.utils.story_generator import GenerationCancelled, StoryGenerator
from src.utils.storage import EpisodeStorage
from src.utils.prompt_generator import PromptGenerator
from src.utils.prompt_schema import TARGET_WORDS_PER_DAY
from src.utils.settings import SETTINGS, stage_model

try:
    from rich.console import Console
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    Console = None
    Table = None
    RICH_AVAILABLE = False


LOGGER = get_logger(__name__)

# Default creative seed that the user picked: "The Ashen Chain".
DEFAULT_SEED_VALUE = 42


def _map_seed_to_metadata(seed: Dict[str, Any]) -> Dict[str, Any]:
    """Map a creative seed dict to the metadata format expected by the pipeline."""
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
        "pipeline": "structured-randomization-v1",
        # Apple Silicon model defaults
        "model_outline": "",
        "model_story": "",
        "model_banner": "",
        "model_chapters": "",
        "model_scenes": "",
    }


def _install_cancel_handler() -> None:
    """Turn SIGTERM into GenerationCancelled so per-day checkpoints survive a stop."""
    def _handler(signum, _frame):
        raise GenerationCancelled(f"Received signal {signum}; completed days are checkpointed.")
    signal.signal(signal.SIGTERM, _handler)


def _find_checkpoint(storage: EpisodeStorage, title: str) -> Optional[Dict[str, Any]]:
    """Return the newest resumable checkpoint payload for *title*, if any."""
    for entry in storage.list_checkpoints():
        if entry.get("title") == title:
            loaded = storage.load_checkpoint(entry.get("path", ""))
            if loaded:
                return loaded
    return None


def main(
    seed_value: int = DEFAULT_SEED_VALUE,
    model: Optional[str] = None,
    outline_model: Optional[str] = None,
    story_model: Optional[str] = None,
    recap_model: Optional[str] = None,
    visual_model: Optional[str] = None,
):
    _install_cancel_handler()
    console = Console() if RICH_AVAILABLE else None
    pipeline_start = time.perf_counter()
    stage_times: Dict[str, float] = {}

    def stage_complete(name: str, started: float) -> None:
        elapsed = time.perf_counter() - started
        stage_times[name] = elapsed
        if console:
            console.print(f"  [green]✓[/green] {name}: {elapsed:.1f}s ({elapsed / 60:.1f} min)")
        else:
            print(f"  ✓ {name}: {elapsed:.1f}s ({elapsed / 60:.1f} min)", flush=True)

    # ── 1. Generate the creative seed ────────────────────────────────────
    print("\n" + "=" * 72)
    print("  GRAVEDANCER → GENERAL — STRUCTURED CREATIVE PIPELINE")
    print("=" * 72 + "\n")

    seed = generate_creative_seed(seed=seed_value)
    print(f"CREATIVE SEED (value={seed['seed']})")
    print("-" * 40)
    print(f"  Title:  {seed['title']}")
    print(f"  Days:   {seed['num_days']}")
    print(f"  Setting: {seed['setting'][:120]}...")
    print(f"  Arc:    {seed['story_arc']}")
    print(f"  Tones:  {', '.join(seed['tone_focus'])}")
    print(f"  Jedi:   {seed['jedi_name']} ({seed['jedi_species']}, {seed['jedi_rank']})")
    print(f"  Saber:  {seed['jedi_lightsaber_color']}")
    print(f"  Personality: {seed['jedi_personality']}")
    print(f"  Why targeted: {seed['jedi_why_targeted']}")
    print()

    # Pick model if not specified; per-stage overrides (CLI flag > env > main)
    # let weak stages go to a cheap fast model and hard stages to the strongest.
    resolved_model = model or SETTINGS.model
    model_outline = stage_model("outline", resolved_model, outline_model or "")
    model_story = stage_model("story", resolved_model, story_model or "")
    model_recap = stage_model("recap", resolved_model, recap_model or "")
    model_visual = stage_model("visual", resolved_model, visual_model or "")
    print(f"Using model: {resolved_model}")
    if len({model_outline, model_story, model_recap, model_visual}) > 1:
        print(f"  outline: {model_outline}")
        print(f"  story:   {model_story}")
        print(f"  recap:   {model_recap}")
        print(f"  visual:  {model_visual}")
    print()

    # ── 2. Initialize pipeline components ────────────────────────────────
    print("Initializing MLX client...")
    mlx = MLXClient()
    # Guarantee weight release even when a phase raises: atexit runs after the
    # exception propagates, and double-release is harmless (idempotent).
    atexit.register(mlx.release_loaded_model)
    story_gen = StoryGenerator(mlx)
    prompt_gen = PromptGenerator(mlx)
    storage = EpisodeStorage(str(SETTINGS.storage_path))

    metadata = _map_seed_to_metadata(seed)

    # ── Resume support: reuse a checkpoint from a previous interrupted run ─
    checkpoint_scope = f"cli:{seed_value}:{uuid.uuid4().hex[:8]}"
    resumed = _find_checkpoint(storage, seed["title"])
    day_drafts: Dict[int, str] = {}
    day_recaps: Dict[int, str] = {}
    draft_only = False
    if resumed and (resumed.get("metadata") or {}).get("num_days") in (None, seed["num_days"]):
        drafts = resumed.get("day_drafts") or {}
        day_drafts = {int(day): str(text) for day, text in drafts.items()}
        recaps = resumed.get("day_recaps") or {}
        day_recaps = {int(day): str(text) for day, text in recaps.items()}
        draft_only = True
        metadata["resumed_from_checkpoint"] = datetime.now().isoformat()
        print(f"Resuming from checkpoint: {len(day_drafts)} completed day(s) will be reused.")
    else:
        resumed = None

    def save_day_checkpoint(day_number: int, day_text: str, recap: str = "") -> None:
        day_drafts[day_number] = day_text
        if recap.strip():
            day_recaps[day_number] = recap.strip()
        path = storage.save_checkpoint(
            title=seed["title"],
            metadata=metadata,
            day_drafts=day_drafts,
            outline=outline,
            scope=checkpoint_scope,
            day_recaps=day_recaps,
        )
        print(f"  [checkpoint] Day {day_number} saved ({len(day_drafts)}/{seed['num_days']} days)", flush=True)
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
        f"This episode was created by structured randomization, "
        f"not pure LLM generation. The core creative choices (Jedi, "
        f"setting, arc, tone) were pre-determined by random tables "
        f"to ensure maximum variety. The LLM's role is to expand "
        f"these seeds into coherent prose."
    )

    # ── 3. Generate outline ──────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  PHASE 1: OUTLINE — \"{seed['title']}\"")
    print(f"{'='*72}\n")
    outline_start = time.perf_counter()

    if draft_only and (resumed.get("outline") or "").strip():
        outline = resumed["outline"].strip()
        print(f"Outline reused from checkpoint ({len(outline):,} chars)")
    else:
        outline = story_gen.generate_episode_outline(
            model=model_outline,
            title=seed["title"],
            num_days=seed["num_days"],
            jedi_details=jedi_details,
            setting=seed["setting"],
            tone_focus=seed["tone_focus"],
            additional_instructions=additional_instructions,
            temperature=0.6,  # slightly creative but structured
        )
        metadata["model_outline"] = model_outline
        stage_complete("Outline", outline_start)
        print(f"\nOutline generated ({len(outline):,} chars) in "
              f"{time.perf_counter() - outline_start:.1f}s")
        print(f"\nOutline preview:\n{outline[:600]}...\n")

    # ── 4. Generate story (multi-pass: day-by-day, section-by-section) ──
    print(f"\n{'='*72}")
    print(f"  PHASE 2: STORY GENERATION")
    print(f"{'='*72}\n")
    story_start = time.perf_counter()

    last_progress = {"value": None, "started": 0.0, "last_update": 0.0}

    def progress_callback(stage: str, message: str, text: str = ""):
        """Print phase changes and a compact live token meter."""
        progress_key = (stage, message)
        now = time.perf_counter()
        if progress_key != last_progress["value"]:
            if last_progress["value"] is not None:
                print(flush=True)
            last_progress.update(value=progress_key, started=now, last_update=0.0)
            print(f"  [{stage}] {message}", end="", flush=True)

        # Callbacks arrive once per generated chunk. Update one terminal line
        # at a modest cadence so users can see progress without log spam.
        if now - last_progress["last_update"] < 2.0:
            return
        elapsed = max(now - last_progress["started"], 0.001)
        # Exact token counts are available from the VLM result at completion;
        # during streaming this character-based estimate is intentionally
        # labeled approximate and avoids re-tokenizing every chunk.
        approx_tokens = max(0, len(text) // 4)
        rate = approx_tokens / elapsed
        # Replace the current terminal row instead of appending a new meter
        # for every callback. ANSI is harmless when output is redirected.
        print(
            f"\r\033[2K  [{stage}] {message} | ~{approx_tokens:,} tokens | ~{rate:.1f} tok/s",
            end="",
            flush=True,
        )
        last_progress["last_update"] = now

    try:
        story = story_gen.generate_episode_story_multi_pass(
            model=model_story,
            title=seed["title"],
            num_days=seed["num_days"],
            jedi_details=jedi_details,
            setting=seed["setting"],
            tone_focus=seed["tone_focus"],
            additional_instructions=additional_instructions,
            temperature=0.8,
            outline=outline,
            day_drafts=day_drafts or None,
            day_recaps=day_recaps or None,
            recap_model=model_recap,
            draft_only=draft_only,
            progress_callback=progress_callback,
            checkpoint_callback=save_day_checkpoint,
        )
    except GenerationCancelled as exc:
        print(f"\n⚠ Generation cancelled: {exc}")
        print(f"  Checkpoint preserved under {storage.base_path / '.checkpoints'}")
        print(f"  Rerun with --seed {seed_value} to resume from the last completed day.")
        mlx.release_loaded_model()
        return None
    metadata["model_story"] = model_story
    stage_complete("Story generation", story_start)
    print(f"\nStory generated ({len(story):,} chars, "
          f"{len(story.split()):,} words) in "
          f"{time.perf_counter() - story_start:.1f}s")

    # Show per-day word counts
    days = story_gen.parse_days(story)
    print(f"\nPer-day word counts (target {TARGET_WORDS_PER_DAY:,} words/day):")
    for d in days:
        wc = d["word_count"]
        pct = (wc / TARGET_WORDS_PER_DAY) * 100
        filled = min(20, int(pct / 5))
        bar = "█" * filled + "░" * (20 - filled)
        print(f"  DAY {d['number']:>2}: {wc:>6,} words ({pct:>5.1f}%) {bar}")

    # ── 5. Extract chapters ──────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  PHASE 3: EXTRACTING CHAPTERS FROM STORY")
    print(f"{'='*72}\n")
    extraction_start = time.perf_counter()
    chapters = prompt_gen.extract_chapters(story)
    stage_complete("Chapter extraction", extraction_start)
    print(f"  Extracted {len(chapters)} chapters across {len(days)} days")

    # ── 6. Generate banner prompt ────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  PHASE 4: BANNER PROMPT")
    print(f"{'='*72}\n")
    banner_start = time.perf_counter()

    banner_result = prompt_gen.generate_banner_prompt(
        metadata=metadata,
        model=model_visual,
        temperature=0.7,
    )
    metadata["model_banner"] = model_visual
    stage_complete("Banner prompt", banner_start)
    print(f"  Banner prompt generated in "
          f"{time.perf_counter() - banner_start:.1f}s")
    print(f"  Banner: {banner_result['banner_prompt'][:150]}...\n")

    # ── 7. Generate chapter prompts (one per extracted chapter) ─────────
    print(f"\n{'='*72}")
    print(f"  PHASE 5: CHAPTER PROMPTS ({len(chapters)} chapters)")
    print(f"{'='*72}\n")

    chapter_prompts_start = time.perf_counter()
    chapter_prompts = []
    for i, ch in enumerate(chapters):
        chap_start = time.perf_counter()
        print(f"  Chapter {i+1}/{len(chapters)} "
              f"(Day {ch['day']}, Ch {ch['chapter_index']}: {ch['chapter_title'][:40]})...",
              end=" ", flush=True)
        result = prompt_gen.generate_chapter_prompt(
            chapter_text=ch["text"],
            day_number=ch["day"],
            chapter_index=ch["chapter_index"],
            chapter_title=ch["chapter_title"],
            model=model_visual,
            temperature=0.7,
        )
        result["day"] = ch["day"]
        result["chapter_index"] = ch["chapter_index"]
        result["chapter_title"] = ch["chapter_title"]
        chapter_prompts.append(result)
        elapsed = time.perf_counter() - chap_start
        print(f"done ({elapsed:.1f}s)")
    metadata["model_chapters"] = model_visual
    stage_complete("Chapter prompts", chapter_prompts_start)

    # ── 8. Assemble prompts payload ──────────────────────────────────────
    prompts_payload = {
        "banner": {
            "prompt": banner_result["banner_prompt"],
            "negative_prompt": banner_result["negative_prompt"],
        },
        "chapters": chapter_prompts,
        "scenes": [],  # backward-compat key
        "generated_at": datetime.now().isoformat(),
        "pipeline": "structured-randomization-v1",
        "model": resolved_model,
    }

    # ── 9. Save episode ──────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  PHASE 6: SAVING EPISODE")
    print(f"{'='*72}\n")

    save_start = time.perf_counter()
    episode_id = storage.save_episode(
        title=seed["title"],
        story=story,
        metadata=metadata,
        prompts=prompts_payload,
    )
    if resumed is not None and resumed.get("path"):
        storage.delete_checkpoint_file(resumed["path"])
    elif day_drafts:
        # Remove this run's scoped checkpoint; the resume lookup matches by
        # title, so stale entries must not linger after a successful save.
        for entry in storage.list_checkpoints():
            if entry.get("title") == seed["title"]:
                storage.delete_checkpoint_file(entry.get("path", ""))
    stage_complete("Save episode", save_start)
    print(f"  Episode saved: {episode_id}")
    print(f"  Location: episodes/{episode_id}/")

    # ── 10. Summary ──────────────────────────────────────────────────────
    total_words = len(story.split())
    total_target = TARGET_WORDS_PER_DAY * seed["num_days"]
    ratio = total_words / max(total_target, 1)

    print(f"\n{'='*72}")
    print(f"  PIPELINE COMPLETE — SUMMARY")
    print(f"{'='*72}")
    print(f"  Title:         {seed['title']}")
    print(f"  Seed value:    {seed['seed']}")
    print(f"  Days:          {seed['num_days']}")
    print(f"  Model:         {resolved_model}")
    if len({model_outline, model_story, model_recap, model_visual}) > 1:
        print(f"  Stage models:  outline={model_outline}")
        print(f"                 story={model_story} recap={model_recap}")
        print(f"                 visual={model_visual}")
    print(f"  Total words:   {total_words:,}")
    print(f"  Target words:  {total_target:,}")
    print(f"  Word ratio:    {ratio:.2f}x")
    print(f"  Chapters:      {len(chapters)}")
    print(f"  Banner prompt: {'✓' if banner_result['banner_prompt'] else '✗'}")
    print(f"  Chapter prompts: {len(chapter_prompts)}/{len(chapters)}")
    total_elapsed = time.perf_counter() - pipeline_start
    if console:
        table = Table(title="Stage Runtime")
        table.add_column("Stage")
        table.add_column("Seconds", justify="right")
        table.add_column("Minutes", justify="right")
        for stage_name, elapsed in stage_times.items():
            table.add_row(stage_name, f"{elapsed:.1f}", f"{elapsed / 60:.1f}")
        table.add_row("TOTAL PIPELINE", f"{total_elapsed:.1f}", f"{total_elapsed / 60:.1f}", style="bold green")
        console.print(table)
    else:
        print(f"\n  STAGE RUNTIME")
        print(f"  {'Stage':<24} {'Seconds':>10} {'Minutes':>10}")
        print(f"  {'-' * 46}")
        for stage_name, elapsed in stage_times.items():
            print(f"  {stage_name:<24} {elapsed:>10.1f} {elapsed / 60:>10.1f}")
        print(f"  {'TOTAL PIPELINE':<24} {total_elapsed:>10.1f} {total_elapsed / 60:>10.1f}")
    print(f"  Episode ID:    {episode_id}")
    print(f"  Directory:     episodes/{episode_id}/")
    print(f"{'='*72}\n")

    # The pipeline is intentionally single-workload on unified-memory Macs.
    # Release the active weights before returning control to the UI or shell.
    mlx.release_loaded_model()
    return episode_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the structured creative pipeline for story generation."
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED_VALUE,
        help=f"Random seed for the creative tables (default: {DEFAULT_SEED_VALUE})",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="MLX model to use for generation (default: auto-detect)",
    )
    parser.add_argument(
        "--outline-model", type=str, default=None,
        help="Model for outline planning (overrides GRAVEDANCER_MODEL_OUTLINE)",
    )
    parser.add_argument(
        "--story-model", type=str, default=None,
        help="Model for prose expansion (overrides GRAVEDANCER_MODEL_STORY)",
    )
    parser.add_argument(
        "--recap-model", type=str, default=None,
        help="Model for per-day continuity recaps (overrides GRAVEDANCER_MODEL_RECAP)",
    )
    parser.add_argument(
        "--visual-model", type=str, default=None,
        help="Model for banner/chapter visual prompts (overrides GRAVEDANCER_MODEL_VISUAL)",
    )
    parser.add_argument(
        "--run-token", type=str, default="",
        help="Unique token remote stops match on; not used programmatically.",
    )
    args = parser.parse_args()
    try:
        result = main(
        seed_value=args.seed,
        model=args.model,
        outline_model=args.outline_model,
        story_model=args.story_model,
        recap_model=args.recap_model,
        visual_model=args.visual_model,
    )
    except GenerationCancelled as exc:
        print(f"\n⚠ Cancelled before a checkpoint existed: {exc}")
        sys.exit(130)
    sys.exit(0 if result else 130)
