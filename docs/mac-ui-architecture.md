# Mac UI Architecture Notes

This project is currently implemented as a Streamlit prototype shell, but the product brief intentionally does not lock the team into Streamlit as the final UI. The goal is a Mac-friendly local creator console centered on MLX and Draw Things.

## What should stay stable

- Story generation logic
- Visual prompt generation logic
- Storage and export formats
- Draw Things integration
- MLX integration

These pieces should remain UI-agnostic so they can be reused by a future desktop shell.

## What should stay replaceable

- Tab layout
- Form controls
- Sidebar settings
- Export/download presentation
- The interaction model for episode review and prompt handoff

Those layers can be rebuilt without changing the core workflow.

## Candidate replacement paths

1. Native desktop shell
   - Best fit if the project needs a more Mac-like production workflow.
   - Could expose the same story/art/library concepts with a desktop-native feel.
2. Lightweight web shell
   - Keeps the current local-first browser experience.
   - Works if the main issue is Streamlit ergonomics rather than the browser itself.
3. Hybrid shell
   - Keeps Python backend modules and swaps only the presentation layer.
   - Lowest-risk path if the team wants to keep momentum while improving the UI.

## Practical design rule

The UI layer should never own business logic for episode generation, prompt parsing, storage shape, or export packaging. It should call into reusable modules and render the result.

## Current recommendation

Keep Streamlit for now as the prototype shell, but treat this repository as already structured for a future UI swap. If the current workflow starts to feel cramped, replace the shell without rewriting the story or prompt pipelines.
