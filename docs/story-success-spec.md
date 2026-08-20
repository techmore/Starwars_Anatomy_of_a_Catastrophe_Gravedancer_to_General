# Story Success Specification

## Purpose

Define what a successful episode of *Gravedancer to General: Anatomy of a
Catastrophe* looks like, so generation, review, validation, visual prompts,
and exports all serve the same series direction.

## Series continuity

This is a **canon-adjacent original fan series**. It is inspired by Qymaen jai
Sheelal's path toward General Grievous, but it has its own continuity and is
not required to resolve every official-canon detail.

- The protagonist is Qymaen jai Sheelal, the Kaleesh warlord known as the
  Gravedancer.
- The setting is pre-Clone Wars in feel and technology. Qymaen is living,
  masked, and only partly augmented; he is not yet the fully cybernetic
  General Grievous.
- Existing Star Wars lore is a texture and constraint against obvious
  contradictions, not a source of mandatory plot beats.
- Do not use canon Jedi as targets. The Jedi adversary is always an original
  character with a real philosophy, tactical competence, and a meaningful
  choice.
- Unknown biography, chronology, alliances, losses, and future milestones are
  intentionally open. The model may **propose** them in a concept, but must not
  present them as permanent series fact until the creator approves and saves
  them.

## Core tone

The dominant mode is **survival horror and dread with Grievous/Qymaen at its
center**.

- Horror comes from pursuit, failing environments, isolation, body cost,
  compromised survival choices, and the sense that something is hunting or
  changing.
- Qymaen is dangerous, intelligent, wounded, and increasingly alien to
  himself; he is never merely a generic armored villain.
- Tactical action supports the dread. Combat has terrain, consequences,
  injury continuity, and cause-and-effect rather than spectacle for its own
  sake.
- Prose is cinematic, visceral, lean, and mythic without imitating a living
  author.

## Creator-led concept workflow

Every episode begins with a short creator seed. The seed may be incomplete;
the concept pass exists to turn it into a structured proposal.

### Required creator input

One free-form prompt describing any combination of:

- desired horror situation or image
- location or environmental threat
- Qymaen's immediate objective or vulnerability
- Jedi concept, if the creator already has one
- desired emotional turn or final image
- constraints, exclusions, or references for the current episode

Example seed:

> A dead mining monastery in an acid-rain forest. Qymaen hunts an original
> Jedi healer while a trapped civilian crew begins to believe the mask is a
> local death spirit. The episode should end with Qymaen choosing survival
> over an old Kaleesh promise.

### Concept-pass output

Before prose generation, the LLM must produce a reviewable structured proposal
containing:

1. title and 3–8 day count
2. setting and environmental-horror engine
3. Qymaen's starting state, pressure, compromise, and transformation
4. original Jedi profile: identity, philosophy, fighting style, reason for
   conflict, and possible choice
5. thematic spine
6. day-by-day escalation and final image/decision
7. proposed continuity facts, explicitly marked **provisional**
8. forbidden elements inferred from the creator seed

No story prose begins until the creator approves the concept. Approved
continuity facts are stored with the episode and become available to later
episodes; unapproved proposals do not become series canon.

## Episode structure

The normal production target is a 3–8 day novella. A day is an
episode-sized installment, normally about 45,000 output tokens (roughly 35,000 words), not a short scene.

Each day must contain:

- 5–8 named chapters
- 2–4 concrete micro-beats per chapter
- a distinct local goal, reversal, and hook
- continuity of location, injuries, equipment, emotional state, and tactical
  position from the preceding day

The full episode must contain:

- a setup → escalation → climax → aftermath/open-ending arc
- a visible Qymaen-to-Grievous movement: colder, more tactical, more altered,
  or more willing to cross a line
- a Jedi antagonist who changes the pressure rather than functioning as a
  disposable obstacle
- a final image, decision, or revelation that lands hard

The pilot should use three days unless the creator requests otherwise. Its
purpose is to establish Qymaen's current code, force a first meaningful
compromise, and open the wider series question.

## Hard rejection rules

Reject or regenerate an output when it:

- treats Qymaen as fully formed General Grievous or generic villain armor
- replaces Qymaen with a generic character called “Gravedancer”
- uses a canon or Legends Jedi target instead of an original Jedi
- invents permanent biography or series history without marking it provisional
  and receiving approval
- ignores the requested day count, chapter/micro-beat structure, or survival
  horror engine
- resolves the Jedi as a simple mandatory kill
- uses generic sci-fi factions or plot turns that are not grounded in the
  creator seed, approved concept, or story world
- loses continuity of wounds, equipment, setting, or tactical position
- pads length with atmosphere that does not advance plot, character, or dread
- includes model reasoning, planning commentary, or non-story notes in prose

## Visual-prompt success

Visual prompts are generated only from approved, stable story prose.

For each selected scene, prompts must preserve:

- Qymaen's living Kaleesh anatomy, weathered ancestral bone mask, visible
  early cybernetics, amber/predatory eyes, and practical warlord gear
- the approved Jedi design and current injury/equipment state
- the episode's environmental-horror engine and current tactical situation
- shot-specific framing: wide, medium action, close-up detail, dramatic low
  angle, and alternate treatment

Prompts must remain ready for Draw Things with Flux.2 Klein 4b still settings
and Wan 2.2 image-to-video motion guidance. No image is represented as
generated unless Draw Things actually returned and saved it.

## Acceptance checklist

An episode is ready to save/export only when:

1. the creator approved the concept and provisional continuity facts
2. each day satisfies its structural target and has a hook
3. the episode satisfies the transformation, Jedi, and final-image tests
4. automated validation reports no hard rejection rule
5. the creator reviewed/edited the stable story before visual extraction
6. `metadata.json`, `story.md`, `prompts.json` when applicable, canonical JSON
   bundle, and ZIP archive reload without loss

## Current implementation gap

The current application has layered outline/day/section generation, but it
does not yet enforce creator approval of a structured concept, provisional
continuity status, the survival-horror rubric, or the rejection checklist.
Those are the next implementation targets; a successful local-model smoke run
is not a successful series episode unless it meets this specification.
