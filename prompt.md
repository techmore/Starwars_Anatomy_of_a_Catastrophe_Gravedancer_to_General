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
- prefer a multi-pass structure over a single monolithic generation:
  1. outline the full episode
  2. break each day into 3 to 5 named sections or chapters
  3. break each section into 2 to 4 concrete micro-beats
  4. expand each section into prose from the outline
  5. optionally run a continuity pass to remove contradictions
- treat each day as an episode-sized installment, roughly 7,500 words per day, with a 5-day run acting as five linked episodes that maintain flow
- keep the daily target word count high, but never allow rambling to replace structure
- preserve continuity of injuries, locations, emotional state, and tactical positioning across days

The base story prompt should enforce:
- cinematic, visceral prose
- sensory detail
- tactical combat detail
- internal monologue for Qymaen
- sparse but meaningful dialogue
- strong scene segmentation by day
- explicit anti-ramble guidance
- no invention of major plot turns during expansion passes
- explicit day-to-chapter-to-micro-beat-to-prose layering so the model stays anchored
- style guidance should be defined by traits, not direct imitation of living authors
- useful style traits include military thriller pacing, gothic war-story atmosphere, and lean, high-tension prose

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

## Prompt Architecture Recommendation
Use layered prompts that keep responsibilities separate:
- episode prompt: high-level arc and constraints
- outline prompt: one short named micro-beat list per day
- day expansion prompt: expand only the current day from the outline
- section expansion prompt: expand only the current section or chapter
- micro-beat structure inside each section: concrete cause-and-effect beats, not vague mood language
- continuity prompt: clean up contradictions after generation
- shared schema prompt file: keep the canonical wording for episode, outline, day, section, and continuity prompts in one place so the app, tests, and docs stay aligned

This hierarchy is the best fit for long-form episodic writing because it keeps the model anchored to structure before style.

## Current Implementation Notes
The codebase already follows this layered shape:
- `StoryGenerator` builds the episode prompt, outline prompt, day expansion prompt, section expansion prompt, and continuity cleanup prompt
- `PromptGenerator` extracts scenes from the day structure and turns them into Draw Things + Wan prompts
- `EpisodeStorage` persists the episode, prompt sets, and archive exports locally
- the UI should keep exposing generation progress clearly so the user can tell which pass is running
- the concept pass should stay short and strict, with a hard validator for the final structured output

## Current Priority
Do not spend time on a ComfyUI workflow. That is not the target pipeline.
The target pipeline is **MLX + Draw Things** on macOS.
