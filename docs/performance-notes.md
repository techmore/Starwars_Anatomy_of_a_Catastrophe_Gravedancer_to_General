# Performance Pass — 2026-08-20

Baseline measurements, fixes applied, and items deliberately left alone.

## Measured problems & fixes

### 1. Entry-point startup: `mlx_client` import cost 3,204 ms

`-X importtime` traced it to the module-level `import optiq` side-effect
registration, which eagerly pulls `mlx_lm` → `transformers` (530 ms) +
`tokenizer_utils` (236 ms) + the rest of the stack. Every entrypoint paid this
(`run_creative_pipeline.py`, `tui.py` via harness→models is unaffected, but any
path touching the client, including Streamlit's first paint, was not).

**Fix:** replaced the eager import with `_ensure_optiq_model_types()`
(just-in-time registration on the native-load path only, idempotent via module
flag). Gemma 4 OptiQ loads still get the patch — they just register when a
load actually happens.

| metric | before | after |
|---|---|---|
| `import src.utils.mlx_client` (warm) | 3,204 ms | **113 ms** |
| same, cold subprocess | ~3,300 ms | **134 ms** |

### 2. Cross-instance model-cache thrash (correctness + perf)

`@lru_cache(maxsize=1)` on the *instance method* `_load_model` stored the
cache on the class, keyed by `(self, model_name)`. Consequences:

- Two `MLXClient` instances shared one slot: whichever client called next
  evicted the other's entry, forcing a **full weight reload from disk**
  (tens of seconds + unified-memory spike) for a model that was already
  resident.
- `release_loaded_model()` on one client cleared the cache for all clients.
- `lru_cache` held strong references to every client (`self` in the key), so
  clients were never garbage-collected.

**Fix:** instance-level single-slot cache (`self._loaded_model`), cleared by
that client's own release. Semantics match the documented intent ("one cached
model per client") and the existing tests
(`test_model_cache_keeps_only_one_loaded_model`). Removed the now-unused
`functools.lru_cache` import.

### 3. O(n²) string joins in streaming progress

`_stream_generate` and the outline loop in `story_generator.py` rebuilt
`"".join(chunks)` on **every chunk** purely to feed token meters that sample
on a 2 s cadence downstream. For a 4,500-token section at per-token chunks
that is thousands of full-buffer copies per section.

**Fix:** refresh the joined snapshot at most twice per second; emit without
text in between. Both consumers (`run_creative_pipeline.py` meter,
`streaming_ui.render_stream_update`) already treat empty `text` as
"phase line only" and use `len(text)` otherwise, so behavior is preserved.

**Verified:** synthetic backend yielding 3,000 chunks — output byte-identical,
snapshot joins reduced from 3,000 → 1 (fast stream) / bounded at 2/s (real
streams).

## Evaluated, deliberately not changed

- **Regex precompilation** (`parse_days`, `extract_chapters`,
  `validate_outline_structure`): ~0.8–1.6 ms per call, called ~40× per run —
  ≈50 ms against runs measured in minutes of inference. Not worth the churn.
- **`EpisodeStorage.list_episodes`**: 8 ms for 13 episodes (reads all
  metadata/prompts JSON). Fine at library scale; revisit past ~100 episodes.
- **LM Studio HTTP connections**: urllib opens a fresh connection per call;
  ~1 ms each on localhost across ~60 calls. Negligible.
- **`tab_story.py` concept loops**: per-chunk join + markdown re-render, but
  bounded at `max_tokens=2048` (~15 ms total). UI-smoothness item, not perf.

## Verification

- `python -m compileall -q app.py run_creative_pipeline.py tui.py scripts src tests`
- `pytest`: 145 passed / 0 failed
- Streaming integrity: synthetic 3,000-chunk stream reproduces exact output
