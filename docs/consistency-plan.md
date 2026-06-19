# Consistency Plan

This project now has a clear target pipeline:

- Story generation via MLX
- Visual prompt generation for Draw Things
- Keyframe / clip handoff for Flux.2 Klein 4b and Wan 2.2 High Noise 6-bit SVDQuant
- Local episode storage with reproducible exports
- A Mac-friendly UI that may evolve beyond Streamlit

## What is already aligned

1. `prompt.md` now states the product intent clearly: MLX + Draw Things are the hard requirements, Streamlit is only acceptable as a prototype, and ComfyUI is not the target.
2. The app structure is modular:
   - `src/utils/story_generator.py`
   - `src/utils/prompt_generator.py`
   - `src/utils/storage.py`
   - `src/utils/drawthings_client.py`
   - `src/components/*`
3. Storage exports are now more consistent:
   - canonical bundle JSON
   - ZIP archive with `bundle.json`
   - `manifest.json` integrity metadata
   - source episode files when present
4. Test coverage already exercises:
   - MLX prompt parsing
   - Draw Things client fallbacks
   - storage normalization and archive output

## Remaining consistency work

1. Separate the UI contract from the prototype shell.
   - Keep Streamlit as the current interface.
   - Make it easy to replace the view layer without touching storage or generation logic.
2. Normalize naming everywhere.
   - Prefer `Draw Things` in user-facing copy.
   - Keep `drawthings` / `DrawThings` only where code or API names require it.
   - Keep `target_jedi_name` as the canonical metadata field while preserving legacy compatibility.
3. Tighten prompt and UI parity.
   - Every user-facing prompt field in the UI should map cleanly to the system prompts.
   - The story form, prompt form, and library export views should expose the same conceptual episode model.
4. Add one integration check for the full local workflow.
   - Story generation -> storage -> scene extraction -> archive export.
   - This should prove the app still behaves like a production pipeline, not only a collection of unit-tested utilities.
5. Revisit the UI stack once the workflow is stable.
   - If Streamlit remains the best Mac-first option, keep it.
   - If not, move to a shell that better matches repeated local production work.

## Practical next step

If we keep going, the highest-value follow-up is an end-to-end smoke test that runs the local episode flow through the current app structure and verifies the exported artifacts stay consistent with `prompt.md`.

## Follow-on planning

When the UI starts to feel constrained, use [`docs/ui-migration-checklist.md`](./ui-migration-checklist.md) as the implementation sequence for a shell swap.
