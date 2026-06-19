# UI Migration Checklist

This checklist turns the Mac UI architecture notes into a sequence we can actually execute when the Streamlit prototype starts to feel limiting.

## Phase 1: Freeze the stable core

- Keep story generation in `src/utils/story_generator.py`
- Keep prompt generation in `src/utils/prompt_generator.py`
- Keep storage and export in `src/utils/storage.py`
- Keep MLX and Draw Things clients isolated in `src/utils/`
- Avoid moving business logic into the UI layer

## Phase 2: Define the UI contract

- Episode creation
- Story review and editing
- Scene extraction and visual prompt generation
- Draw Things handoff
- Episode library and export

The replacement UI should support the same concepts without needing the old Streamlit tab structure.

## Phase 3: Replace one surface at a time

1. Sidebar / settings panel
   - model selection
   - temperature
   - storage path
   - system prompts
2. Story workflow
   - create episode
   - generate story
   - review and edit
3. Prompt workflow
   - extract scenes
   - generate image and video prompts
   - copy or hand off to Draw Things
4. Library workflow
   - browse
   - load
   - delete
   - export

## Phase 4: Preserve compatibility checks

- Keep the smoke test for the end-to-end local flow
- Keep storage export tests intact
- Keep prompt parsing tests intact
- Re-run the suite after each UI-layer change

## Exit criteria

The UI migration is done only when the replacement shell can:

- generate a story via MLX
- produce scene prompts
- hand off or prepare content for Draw Things
- persist and export episodes using the same storage contract

## Roadmap

Use [`docs/ui-migration-roadmap.md`](./ui-migration-roadmap.md) for the step-by-step implementation order once work starts on the shell swap.
