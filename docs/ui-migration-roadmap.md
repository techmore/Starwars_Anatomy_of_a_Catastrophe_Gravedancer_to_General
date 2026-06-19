# UI Migration Roadmap

This roadmap is the concrete execution plan behind the current Mac UI notes and migration checklist.

## Goal

Preserve the current MLX + Draw Things workflow while making the presentation layer replaceable.

## Backend contract

These modules are treated as stable interfaces:

- `src/utils/story_generator.py`
- `src/utils/prompt_generator.py`
- `src/utils/storage.py`
- `src/utils/drawthings_client.py`
- `src/utils/mlx_client.py`
- `src/utils/concepts.py`

The UI should call these modules, not duplicate their logic.

## Roadmap

### 1. Lock the UI surface area

- Enumerate the screens that must exist in any shell:
  - settings
  - story creation
  - story review
  - prompt generation
  - library/export
- Keep the names and responsibilities stable even if the widgets change.

### 2. Keep Streamlit thin

- Treat `app.py` as the composition root only.
- Keep per-tab logic in small modules.
- Move any reusable state or formatting logic into backend helpers.

### 3. Extract shell-neutral state

- Make sure the current episode, metadata, and prompt payloads can be passed between views without relying on widget-specific state.
- Prefer plain dicts and small dataclasses over UI-bound globals when possible.

### 4. Migrate one screen at a time

1. Settings and sidebar
2. Story generation and review
3. Prompt generation and Draw Things handoff
4. Library and export

### 5. Validate each step

- Keep the smoke test green.
- Keep storage export tests green.
- Keep prompt parsing tests green.
- Re-run the full suite after each migration slice.

## Exit condition

The migration is only done when a replacement shell can render the same workflow without changing the stable backend contract.
