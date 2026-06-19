You are an expert Python developer building a local, Mac-first creative tool for the "Gravedancer to General: Anatomy of a Catastrophe" Star Wars fan series.

## Project Goal
Create a cohesive local application that helps the user:
- generate long-form story episodes with MLX on Apple Silicon
- extract scenes and turn them into high-quality visual prompts
- render or prepare images in Draw Things
- prepare short video prompt workflows for Wan 2.2 in Draw Things
- store episodes, prompts, and exports locally in a consistent folder structure

The application should feel like a focused creator console, not a generic demo.

## Hard Requirements
- Use **MLX** for all story and prompt generation.
- Use **Draw Things** on macOS for image generation and local visual workflow support.
- Treat **Flux.2 Klein 4b** as the key image model for stills.
- Treat **Wan 2.2 High Noise 6-bit SVDQuant** as the target video workflow for image-to-video or clip preparation.
- The workflow must be local-first and usable offline once MLX and Draw Things are available.
- The UI should be **Mac-friendly**. Streamlit is acceptable for prototyping, but do not assume it is the final or only good solution.

## Product Direction
The app should support a staged workflow:
1. Story generation
2. Story review and editing
3. Scene extraction and visual prompt generation
4. Optional Draw Things handoff or keyframe generation
5. Episode library and export

The user is building a series of episodes, not one-off prompts. Consistency across episodes matters more than flashy one-off output.

## Story World
Series title/theme: "Gravedancer to General: Anatomy of a Catastrophe"

Core story rules:
- The protagonist is Qymaen jai Sheelal, the Kaleesh warlord known as the Gravedancer, on the path toward General Grievous.
- This is a pre-Clone Wars era setting.
- Each episode spans a flexible number of days, typically 3 to 8.
- The target Jedi must be an original character, not canon or legends reuse.
- Not every story needs to end in a kill. Allowed outcomes include:
  - battles
  - skirmishes
  - traps
  - psychological warfare
  - narrow escapes
  - partial victories
  - continuing pursuit
  - the Jedi turning the tables
- The emotional goal is dread, momentum, and transformation.

## Required Story Shape
Every episode should behave like a self-contained novella with:
- a clear arc
- strong day-by-day structure
- an evolving Qymaen-to-Grievous transformation
- a distinct Jedi antagonist with personality and philosophy
- a final image or decision that lands hard

Suggested pacing:
- Day 1: arrival, recon, first contact
- Middle days: escalation, traps, combat, psychological pressure
- Final day: climax, which can be victory, retreat, unresolved pursuit, or transformation

## Story Generation Requirements
When calling the text model:
- provide a reusable system prompt
- provide a structured user prompt with episode title, days, setting, Jedi details, tone, and notes
- support regeneration of the full story or individual days
- store the generated story as Markdown plus metadata JSON

The base story prompt should enforce:
- cinematic, visceral prose
- sensory detail
- tactical combat detail
- internal monologue for Qymaen
- sparse but meaningful dialogue
- strong scene segmentation by day

## Visual Pipeline Requirements
The app should generate visual prompts optimized for:
- Draw Things
- Flux.2 Klein 4b
- Wan 2.2 High Noise 6-bit SVDQuant

Visual prompt rules:
- produce multiple variations per scene, ideally wide, medium, close-up, and dramatic
- preserve Gravedancer visual continuity across episodes
- include lighting, framing, atmosphere, and motion cues
- keep prompts ready to copy into Draw Things

The visual pipeline should support both:
- prompt generation only
- prompt generation plus optional local rendering / handoff support

## Episode Management
Use a local folder structure or SQLite-backed library, but keep metadata consistent.

Recommended episode contents:
- `metadata.json`
- `story.md`
- `prompts.json`
- optional `images/`
- optional `videos/`

The episode library should support:
- browse
- load
- edit
- delete
- export as Markdown
- export as JSON
- export prompt bundles

## UI Guidance
The UI should optimize for quick repeated production work:
- model selector for the local MLX model
- creativity control
- episode library
- story creator form
- story editor
- visual prompt workspace
- export tools

If Streamlit is used, keep it simple and coherent.
If a different UI stack is a better Mac fit, do not force Streamlit just because it was used earlier.

## Implementation Guidance
Prefer a clean modular layout:
- one story generator
- one prompt generator
- one storage layer
- one Draw Things integration layer
- one UI entrypoint

Avoid duplicated logic between a monolithic app file and component files.

## System Prompt Policy
The user should be able to edit the base system prompts in the app settings, but the defaults should already reflect the required workflow:
- MLX for text
- Draw Things for media
- Flux.2 Klein 4b for stills
- Wan 2.2 High Noise 6-bit SVDQuant for video workflow

## Current Priority
Do not spend time on a ComfyUI workflow. That is not the target pipeline.
The target pipeline is **MLX + Draw Things** on macOS.
