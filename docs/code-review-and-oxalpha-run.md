# Codebase Review & Ox-Alpha Pipeline Run — 2026-08-20

Review of improvement opportunities, plus a full end-to-end pipeline run with an
in-session LLM (ox-alpha) serving as the generation backend in place of MLX.

## Part 1: Review Findings

### High value

1. **Broken dead function** — `src/utils/creative_tables.py:323` `generate_title()`
   references a module-level `rng` that does not exist; any call raises
   `NameError`. No callers found. Fix or delete.
2. **LM Studio port mismatch** — `harness.py:101` defaults to port **1235**
   while `mlx_client.py:33`, its error text (`:620`), and the sidebar guidance
   (`sidebar.py:126`) all use **1234**. TUI health checks probe the wrong port.
3. **No-op token math** — `story_generator.py:423` `max(8000, 11000)` is always
   11000; `:451`/`:955` `max(12000, num_days * 11000)` yields 44k–66k tokens,
   silently clamped by LM Studio's 8192 ceiling.
4. **Stale tests after model migration** — `tests/test_session_state.py`
   asserts `DEFAULT_MODEL == "prism-ml/Bonsai-27B-mlx-1bit"` but the working
   tree default is now `mlx-community/Qwen3.8-27B-OptiQ-4bit`. Suite currently
   reports 136 passed / 2 failed for this reason alone.
5. **Contradictory outline instructions** — outline template shows Chapters 1–5
   (`story_generator.py:201-217`) while rule text demands "exactly 10 chapters"
   (`:223`); validator accepts 5–10 (`prompt_schema.py:229`). Models receive
   conflicting specs.
6. **Wrong word targets in CLI summary** — `run_creative_pipeline.py:223,314`
   hardcodes `7500` instead of `TARGET_WORDS_PER_DAY`, so progress bars and
   ratios are off by ~4.6x under default settings.

### Reliability

7. **No retries on text backends** — Draw Things client retries 3x
   (`drawthings_client.py:47-60`); MLX/LM Studio/Ollama paths fail on first
   transient error.
8. **Model weights not released on failure** — `release_loaded_model()` runs at
   normal completion (`run_creative_pipeline.py:353`) but not in `try/finally`;
   a mid-run exception leaves ~15–20GB resident.
9. **Class-level lru_cache on instance method** — `mlx_client.py:384`
   `@lru_cache(maxsize=1)` on `_load_model` shares cache across instances;
   one client's release evicts for all while `_active_model` flags stay set.
10. **stderr handling** — subprocess fallback merges stderr into stdout
    (`mlx_client.py:734`), contaminating prose; OpenCode/Bonsai read stderr
    only after stdout EOF (deadlock risk).
11. **Effectively unbounded LM Studio timeout** — `timeout=max(180,
    max_tokens//2)` ≈ 68 minutes at 8192 tokens; no overall deadline.
12. **CLI pipeline cannot resume** — checkpoint/resume is Streamlit-only;
    `run_creative_pipeline.py` never passes `checkpoint_callback`, though it is
    the long-running path most likely to fail mid-run.

### Hygiene / duplication

13. `.gitignore` does not cover `.models/`, `Images/`, `episodes/`,
    `.pytest_cache/`; root `conftest.py` and `pyproject.toml` are untracked.
14. `pyproject.toml [tool.pytest.ini_options]` duplicates `pytest.ini`
    (pytest.ini wins; two sources of truth).
15. Keyframe rendering duplicated between `tab_art.py:177-201` and
    `tab_viewer.py:348-370`; chat-template formatting duplicated in
    `bonsai_runner.py:12-22` vs `mlx_client.py:146-178`.
16. Dead code cluster: `creative_tables.format_creative_seed` /
    `generate_multiple_seeds`, `story_generator.build_continuity_prompt` /
    `regenerate_day_from_draft` / `generate_story_stream`,
    `concepts.parse_full_episode_concept`,
    `prompt_schema.build_concept_common_constraints`, and the unreachable
    `"resolutions"` branch (`creative_tables.py:292`).
17. Test coverage gaps: no tests for `harness.py`, `remoter.py`,
    `bonsai_runner.py`, `creative_tables.py` (a test would have caught #1),
    `app_context.py`.

### Docs vs reality

18. README presents Wan 2.2 I2V video generation as a working step-by-step
    workflow; `drawthings_client.generate_video` is best-effort with fallback
    returns, and README `:263` concedes clips remain manual.

## Part 2: Pipeline Run with ox-alpha as the Model

Approach: everything behind the `TextGenerationBackend` protocol
(`contracts.py:10`) was kept; a new driver (`scripts/run_oxalpha_pipeline.py`)
mirrors `run_creative_pipeline.py` stage-for-stage and serves pre-authored
responses from `.oxalpha-run/responses/` through the real streaming interface.
All prompts were captured to `.oxalpha-run/prompts/` for inspection.

Run record (seed 42 → "The Ashen Chain", 6 days):

| Stage | Result |
|---|---|
| Creative seed | Deterministic tables, seed=42 |
| Outline | Passed `validate_outline_structure` AND `validate_outline_quality` |
| Story multi-pass | 6 days × 5 sections = 30 calls, 3,993 words |
| Chapter extraction | 30 chapters via real regex parser |
| Banner prompt | 801 chars, cleaned by real `_clean_visual_prompt` |
| Chapter prompts | 30 sets; wide/medium/closeup parsed 90/90 shots |
| Storage | Saved via real `EpisodeStorage.save_episode` |

Episode: `episodes/episode-20260820-181840586514-the-ashen-chain-ce2bfa0f/`
(metadata marks `pipeline: oxalpha-in-session-v1`.)

Deviation note: section prose (~130 words each) is far below the production
target (~34,600 words/day) — this was a structural demonstration sized for an
in-session model, not a replacement for the local 27B runtime. All validation,
parsing, and storage gates executed unmodified.
