# Word Count Analysis: Pipeline v1 → v2

## Results

| Version | Day 1 | Day 2 | Day 3 | Day 4 | Day 5 | Total | % of Target |
|---------|-------|-------|-------|-------|-------|-------|-------------|
| **v1** (original) | 1,110 | 1,101 | 976 | 1,135 | 1,100 | **5,422** | 14.5% |
| **v2** (expanded) | 4,954 | 3,386 | 3,565 | 2,438 | 2,565 | **16,908** | 45.1% |
| **Target** | 7,500 | 7,500 | 7,500 | 7,500 | 7,500 | **37,500** | 100% |

**v2 improvement: 3.1x over v1**, but still only 45% of target. Day 1 hit 66% before later days tapered off.

---

## Root Cause Analysis (Code-Level)

### Problem 1: "Approximately" Language

Every prompt in the pipeline uses softeners that the model treats as suggestions:

| Location | Current phrasing | Problem |
|----------|-----------------|---------|
| `prompt_schema.py:46` | `Target ~7,500 words per day` | "~" signals approximation |
| `story_generator.py:227` | `Write approximately 7,500 words for this day (roughly 30-40 paragraphs)` | "approximately" + "roughly" double-softens |
| `story_generator.py:289` | `Write approximately {n:,} words for this section` | Same issue at section level |
| `system_prompts.py:35` | `approximately 7,500 words` | Softeners propagate from system prompt |

**Fix:** Replace with hard requirements:
```python
# In build_day_expansion_prompt():
"- You MUST write at least 7,000 words for this day. Count your words before finishing."

# In build_section_expansion_prompt():
f"- You MUST write at least {section_word_target:,} words for this section."
```

### Problem 2: No Structural Enforcement

The prompts say "5-8 chapters per day" but don't require them. The model optimizes for conciseness.

**Fix:** Add explicit structural requirements with minimums:
```python
# In build_day_expansion_prompt():
"STRUCTURAL REQUIREMENTS (non-negotiable):
- This day MUST contain 6-8 chapters
- Each chapter MUST contain 6-8 micro-beats
- Each micro-beat MUST be 1-3 paragraphs of prose

WORD COUNT:
- Total for this day: at least 7,000 words
- If you finish and the count is below 7,000, ADD MORE beats or expand existing ones."
```

### Problem 3: Section max_tokens is Too Conservative

`story_generator.py:614` caps sections at 6,000 tokens. At ~0.75 tokens/word, that's ~4,500 words max per section — more than enough for a single section. But the model doesn't expand to fill it because the prompt doesn't require it.

**Fix:** Keep `max_tokens=6000` but add a minimum word requirement per section that totals to 7,500/day. If a day has 6 sections, each must be at least 1,250 words. At 6,000 tokens (~4,500 words), the cap has plenty of headroom.

### Problem 4: No Per-Day Word Count Monitoring

The pipeline logs word counts but doesn't act on them. The `day_word_ratio` at `story_generator.py:642` is logged but not used to trigger any action.

**Fix:** Add a post-generation check that flags short days:
```python
if day_word_count < TARGET_WORDS_PER_DAY * 0.7:
    LOGGER.warning(
        "Day %s is only %s words (%.0f%% of target %s). Quality may suffer.",
        day_number, day_word_count, day_word_ratio * 100, TARGET_WORDS_PER_DAY,
    )
```

### Problem 5: `build_story_word_budget()` Ignores `num_days`

`prompt_schema.py:104-105` always returns 7,500 regardless of days:
```python
def build_story_word_budget(num_days: int) -> int:
    return TARGET_WORDS_PER_DAY  # ignores num_days!
```

This function is used in the `regenerate_day()` prompt (story_generator.py:868). If someone has a 3-day episode, the per-day budget should arguably be higher (10,000-12,000 words) and for an 8-day episode, lower (5,000-6,000). The current flat 7,500 ignores the trade-off between day count and per-day depth.

### Problem 6: Duplicate Constants

Three files define `TARGET_WORDS = 7500` independently:
- `prompt_schema.py:13` — primary
- `concepts.py:33` — duplicate
- `story_validator.py:12` — duplicate

If someone changes the primary constant, the concept and validation thresholds will drift. Import from `prompt_schema.py` instead.

---

## Structural Formula for 7,500 Words/Day

My v2 used 6 chapters × 6 beats × ~100-150 words/beat = ~3,600-5,400 words. To hit 7,500:

| Component | Count | Words each | Total |
|-----------|-------|-----------|-------|
| Chapters per day | 7 | — | — |
| Beats per chapter | 6 | 180 | 7,560 |
| Paragraphs per beat | 2-3 | 60-90 | — |

The key change: **each beat needs 2-3 dense paragraphs** (sensory detail, interiority, tactical specifics, dialogue fragments) instead of 1 short paragraph. The app's `STORY_DEEPENING_REQUIREMENTS` block already asks for this — the model just needs the word minimum enforced.

---

## Recommended Code Changes

### 1. `prompt_schema.py` — Hard minimums

```python
STORY_BASE_CONSTRAINTS = [
    "Write a complete {num_days}-day novella following the series format.",
    f"Target exactly {TARGET_WORDS_PER_DAY:,} words per day. THIS IS A MINIMUM, NOT A TARGET.",
    "Each day MUST have 6-8 distinct chapters.",
    "Each chapter MUST contain 6-8 concrete beats.",
]
```

### 2. `story_generator.py` — Enforce in day expansion prompt

Replace `build_day_expansion_prompt()` line 227-234:
```python
f"""WORD COUNT REQUIREMENT (MANDATORY):
- This day must contain at least {TARGET_WORDS_PER_DAY:,} words.
- That is approximately 30-40 paragraphs of dense prose.
- If you reach the end of the outline and are below this count,
  expand existing scenes with more sensory detail, interiority,
  tactical specifics, and dialogue.
- Do NOT pad with filler. Add genuine content.

STRUCTURAL REQUIREMENT:
- This day MUST have 6-8 chapters.
- Each chapter MUST have 6-8 micro-beats.
- Each beat should be 2-3 paragraphs of fully developed prose.
"""
```

### 3. `system_prompts.py` — Remove softeners

```
"Each day MUST contain at least 7,500 words." (instead of "approximately")
```

### 4. Eliminate duplicate constants

```python
# concepts.py — import instead of redefine
from src.utils.prompt_schema import TARGET_WORDS_PER_DAY as TARGET_WORDS
```

---

## Summary

The pipeline structure is sound but the prompts lack enforceability. The model needs:
1. **Hard word minimums** ("at least 7,000 words") instead of soft targets ("approximately 7,500")
2. **Structural minimums** ("MUST have 6-8 chapters with 6-8 beats each")
3. **Post-generation warnings** for short days
4. **Single source of truth** for the word target constant

The structural formula works: 7 chapters × 6 beats × ~180 words = 7,560 words. The pipeline just needs to demand it.
