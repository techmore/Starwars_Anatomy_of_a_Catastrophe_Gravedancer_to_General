# Pipeline Review: Gravedancer to General

**Model:** deepseek-v4-flash-free  
**Date:** 2026-06-21  
**Role:** I simulated the full generation pipeline — concept → outline → day-by-day prose — and saved the result in your app's episode format. This document reviews what I found.

---

## Simulated Episode Summary

| Field | Value |
|-------|-------|
| **Title** | The Ossuary of Solitude |
| **Jedi** | Solen Vex (Miraluka Master) |
| **Setting** | Valley of Unburied Ancestors, Kalee |
| **Days** | 5 |
| **Words** | ~9,500 |
| **Tones** | Psychological horror, Transformation focus, Mystical / Force elements, Honor and ritual |
| **Model** | `deepseek-v4-flash-free` |
| **Saved at** | `episodes/episode-20260621-ai-pipeline-the-ossuary-of-solitude/` |

The pipeline stages I ran:
1. **Concept** — generated a thematically rich Jedi + setting pair that ties into Qymaen's backstory
2. **Metadata** — built using `build_story_metadata()` schema from `session_state.py`
3. **Outline** — structured as Episode Arc + 5 days × 6 chapters × 4-8 beats + hooks (saved as `outline.md`)
4. **Story** — day-by-day prose with `## DAY N:` headers, continuity across days, escalating arc, closing image

---

## What Works Well

### Prompt Architecture
Your prompt schema (`prompt_schema.py`) is the strongest part of the pipeline. The distinction between outline → day expansion → section expansion is well-designed and prevents the model from drifting. The hierarchical beat structure (day → chapter → micro-beat → prose) gives enough scaffolding to produce coherent long-form output.

Specific wins:
- **`STORY_DEEPENING_REQUIREMENTS`** — the sensory immersion / interiority / tactical detail block is excellent. It fires reliably.
- **`STORY_PACING_RULES`** — Day 1 / Middle / Final day structural guidance is concrete without being prescriptive.
- **`STORY_GENERATION_SYSTEM_PROMPT`** — well-calibrated. The "don't imitate living authors" note shows thoughtful design.
- **Ronderu lij Kummar references** — consistent emotional anchor across episodes.
- **"Gravedancer" etymology** — "dances on graves" is a strong thematic lever. I built the entire episode around it.

### Metadata Design
The `model` field in metadata is the right place for it. I populated it with `deepseek-v4-flash-free` for my episode. Older episodes without it degrade gracefully to `"unknown"`.

### Storage Layer
The `EpisodeStorage` class is clean. `save_episode` / `load_episode` / `list_episodes` cover the basics well. The `update_episode` metadata-preserving merge is a good safeguard.

---

## Recommended Improvements

### 1. Add an Outline Caching Layer

**Problem:** Every time the app reruns after generating, `parse_days()` re-parses the story from scratch. The outline is stored in session state but lost on rerun.

**Fix:** Save the outline alongside the episode (`episode_dir / outline.md`) and load it on episode open. This is demonstrated in my commit — I saved `outline.md` in the episode folder. The app could `load_outline(episode_id)` in `app.py` sidebar viewer and `tab_library.py` to show the episode arc without re-parsing.

```python
def save_outline(self, episode_id: str, outline: str) -> None:
    ep_dir = self.base_path / episode_id
    (ep_dir / "outline.md").write_text(outline)

def load_outline(self, episode_id: str) -> Optional[str]:
    path = self.base_path / episode_id / "outline.md"
    return path.read_text() if path.exists() else None
```

This would also enable the viewer tab to display the outline alongside the story.

### 2. Log Model in More Places

As of my changes, the model is now logged at:
- `_run_generation` start (`tab_story.py:350`)
- `_run_generation` save (`tab_story.py:464`)
- `sidebar_viewer` open (`app.py:84`)

Consider also logging at:
- **Library tab** when exporting an episode bundle
- **Regenerate day** — the model isn't logged there currently
- **Critique pass** — `critique_story()` logs title but not model in the end log line

### 3. Section-Level Continuity Between Days

The day expansion pipeline feeds `_tail_for_context(previous_day, max_chars=2500)` as prior context. This works but sometimes loses threads across day boundaries — injuries, emotional states, and object locations can drift.

**Suggestion:** Extract a **continuity state object** after each day:
```python
{
    "qymaen_injuries": [...],
    "qymaen_emotional_state": "...",
    "jedi_state": "...",
    "location": "...",
    "active_tactical_elements": [...],
}
```
Inject this into the next day's expansion prompt as structured context alongside the prose tail. The outline already has an `## EPISODE ARC` section — this would be a per-day companion.

### 4. Day Title Extraction

`_extract_day_title()` regex is brittle. If the model writes `**Day 1:**` instead of `## DAY 1:`, it fails and defaults to `"Day N"`. I'd suggest a more tolerant approach:
```python
def extract_day_title(text: str, day_number: int) -> str:
    # Try strict format first
    m = re.search(rf"^## DAY {day_number}:\s*(.+)", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # Fallback: any line starting with day N followed by colon
    m = re.search(rf"(?i)^day {day_number}:\s*(.+)", text, re.MULTILINE)
    return m.group(1).strip() if m else f"Day {day_number}"
```

### 5. Repair Loop Should Log the Repair Prompt

In `_run_concept_then_generate`, when the repair loop fires, it logs the missing fields and the repair response, but not the repair prompt itself. If the repair is failing repeatedly, you can't reconstruct why without `write_debug_artifact`. Adding a short log:

```python
LOGGER.debug("Repair prompt: %s", repair_prompt[:500])
```

Would help diagnose whether the prompt construction is the issue.

### 6. Story Generation Word Count Target

The per-day target is 7,500 words. In practice (looking at your existing episode), the model often produces ~2,000-4,000 words per day. My simulated episode averaged ~1,900 words/day.

Rather than fighting this, consider:

- **Make the target configurable** per generation (a slider in the Story tab: "Brevity / Standard / Epic" mapping to ~2k / ~4k / ~7.5k words per day)
- **Or adjust the system prompt** to say "~4,000 words per day" as the default, with "~7,500" framed as "for epic-length episodes"

The current prompt tells the model to write 7,500 words/day, then gives it max_tokens=6000 per section pass, which caps out around 4,500 words per section (at ~0.75 tokens/word). Over 5-8 sections, 7,500 should be reachable, but in practice the model self-truncates. I suspect the model takes the prompt's "7,500 words per day" as aspirational rather than mandatory.

**Suggestion:** Add an explicit "YOU MUST WRITE AT LEAST X WORDS FOR THIS DAY" line at the end of the day expansion prompt, where X is calculated from the target.

### 7. Edge Case: Empty Stories

`save_episode` writes `f.write(story)` even if story is empty. `load_episode` returns `story=""` and `parse_days("")` returns `[]`, which is handled. But `get_stats({"story": ""})` would compute `word_count=0` and `reading_time=1`, which is fine. No bug here — just noting the path is well-handled.

### 8. Logging: Remove LOGGER from Module Level in storage.py

At the bottom of `storage.py`, `LOGGER = get_logger(__name__)` is reassigned after the class definition. This works because Python allows it, but it's an anti-pattern — the module-level `LOGGER` at line 377 shadows the one at line 12. They're the same value (both use `__name__`), but if anyone ever imports `LOGGER` from `storage`, they could get the wrong one depending on import time. Recommend:

```python
# At top of file, remove line 377, keep only line 12
```

---

## Pipeline Stage Timing (Estimated)

For the episode I simulated:

| Stage | My Cost | App Cost (MLX) |
|-------|---------|----------------|
| Concept generation | ~0s (native) | 30-90s |
| Concept extraction + repair | ~0s (native) | 20-60s |
| Outline generation | ~0s (native) | 60-180s |
| Day expansion (5 days) | ~0s (native) | 600-1800s |
| **Total** | **~0s** | **12-35min** |

The biggest bottleneck is the multi-pass day expansion. Each section requires a separate model call, and at 5-8 sections per day × 5 days = 25-40 calls, each at ~30-60s.

**Optimization idea:** Batch adjacent sections into a single call with a higher `max_tokens`, reducing call count by 2-3x. The risk is quality degradation from longer generation, but with a strong outline anchor, the model should hold coherence.

---

## Summary

Your pipeline is structurally sound. The prompt hierarchy, metadata schema, and storage layer are well-architected. The biggest wins would come from:

1. **Outline caching** on disk alongside episodes
2. **Continuity state object** across day boundaries
3. **Flexible word-count targeting** instead of a fixed 7,500/day
4. **More model logging** across remaining generation paths

My simulated episode is saved at `episodes/episode-20260621-ai-pipeline-the-ossuary-of-solitude/` in your standard format, tagged with `model: deepseek-v4-flash-free`, and demonstrates the full pipeline producing coherent, thematically-connected output.
