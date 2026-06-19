# Project Status

## Verified working pieces

- Story generation is modular and uses MLX.
- Visual prompt generation is modular and geared toward Draw Things.
- Episode storage exports a canonical bundle plus archive artifacts.
- The workflow from story -> scene extraction -> prompt generation -> export is covered by tests.
- Machine-readable prompt labels still use `DrawThings` where the parser and stored data expect that spelling.

## Current UI state

- Streamlit is the current prototype shell.
- The repo is structured so the presentation layer can be replaced later.

## Documentation map

- [`prompt.md`](../prompt.md) - product brief and hard requirements
- [`docs/INDEX.md`](INDEX.md) - docs landing page
- [`docs/consistency-plan.md`](consistency-plan.md) - current alignment checklist
- [`docs/mac-ui-architecture.md`](mac-ui-architecture.md) - future UI boundaries
- [`docs/ui-migration-checklist.md`](ui-migration-checklist.md) - shell swap phases
- [`docs/ui-migration-roadmap.md`](ui-migration-roadmap.md) - implementation order

## Next likely step

If the prototype shell starts to feel limiting, follow the migration roadmap and replace the UI one surface at a time without moving the backend workflow.
