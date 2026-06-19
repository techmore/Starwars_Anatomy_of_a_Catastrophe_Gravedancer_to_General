# Requirements Trace

This document ties the product brief in [`prompt.md`](../prompt.md) to the current implementation, tests, and planning docs.

## Hard requirements

| Requirement | Evidence |
| --- | --- |
| MLX for all story and prompt generation | `src/utils/mlx_client.py`, `src/utils/story_generator.py`, `src/utils/prompt_generator.py`, `src/components/sidebar.py`, `tests/test_prompt_generator.py`, `tests/test_workflow_smoke.py` |
| Draw Things for image generation and local visual workflow support | `src/utils/drawthings_client.py`, `src/components/tab_art.py`, `src/components/tab_prompts.py`, `README.md`, `docs/PROJECT-STATUS.md` |
| Flux.2 Klein 4b as the key still model | `src/prompts/system_prompts.py`, `src/components/tab_art.py`, `src/components/tab_prompts.py`, `tests/test_prompt_generator.py` |
| Wan 2.2 High Noise 6-bit SVDQuant as the video workflow target | `src/prompts/system_prompts.py`, `src/components/tab_prompts.py`, `README.md`, `tests/test_prompt_generator.py` |
| Local-first, offline-capable workflow | `README.md`, `prompt.md`, `docs/mac-ui-architecture.md`, `src/utils/mlx_client.py`, `src/utils/drawthings_client.py` |
| Mac-friendly UI with Streamlit as prototype only | `README.md`, `prompt.md`, `docs/mac-ui-architecture.md`, `docs/consistency-plan.md`, `docs/PROJECT-STATUS.md` |

## Product direction

| Requirement | Evidence |
| --- | --- |
| Story generation -> review/edit -> scene extraction -> prompt generation -> library/export | `app.py`, `src/components/tab_story.py`, `src/components/tab_viewer.py`, `src/components/tab_prompts.py`, `src/components/tab_library.py`, `tests/test_workflow_smoke.py` |
| Store episodes, prompts, and exports locally in a consistent structure | `src/utils/storage.py`, `tests/test_storage_metadata.py`, `docs/PROJECT-STATUS.md` |
| Support multiple scene prompt variations and copy-ready prompts | `src/utils/prompt_generator.py`, `src/components/tab_prompts.py`, `src/components/tab_art.py` |
| Support optional Draw Things handoff or keyframe generation | `src/utils/drawthings_client.py`, `src/components/tab_art.py`, `src/components/tab_prompts.py` |

## Story world and shape

| Requirement | Evidence |
| --- | --- |
| Qymaen jai Sheelal / Gravedancer protagonist on path toward Grievous | `src/prompts/system_prompts.py`, `src/utils/concepts.py`, `src/utils/story_generator.py` |
| Original Jedi antagonist, not canon reuse | `src/prompts/system_prompts.py`, `src/utils/concepts.py` |
| Day-by-day novella structure with transformation arc and hard landing | `src/prompts/system_prompts.py`, `src/utils/story_generator.py`, `tests/test_workflow_smoke.py` |

## Documentation and migration path

| Requirement | Evidence |
| --- | --- |
| Consistency plan for current alignment | `docs/consistency-plan.md` |
| Mac UI architecture note | `docs/mac-ui-architecture.md` |
| Shell swap checklist | `docs/ui-migration-checklist.md` |
| Shell swap roadmap | `docs/ui-migration-roadmap.md` |
| Project status handoff | `docs/PROJECT-STATUS.md` |
| Docs landing page | `docs/INDEX.md`, `README.md` |

## Notes

- Machine-readable prompt labels still use `DrawThings` in the parser contract and stored payloads where the tests expect that spelling.
- The current implementation satisfies the product brief through a Streamlit prototype shell; the docs explicitly leave the UI layer replaceable.
