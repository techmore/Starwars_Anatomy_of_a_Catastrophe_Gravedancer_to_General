# Publishing Plan: Pipeline → Gravedancer_to_General site

## Two-repo layout

- **Pipeline repo** (this repo, `Starwars_Anatomy_of_a_Catastrophe_Gravedancer_to_General`):
  private working repo — generation code, episode run outputs, images, tests.
  Never published directly.
- **Publishing repo** (`techmore/Gravedancer_to_General`): separate public
  repo that is the website. Publishing = converting a finished pipeline
  episode into its format and pushing there.

Goal: after a pipeline run completes an episode, a single command turns the
episode dir into a publish-ready Markdown file in
`github.com/techmore/Gravedancer_to_General` and (optionally) pushes it,
triggering the GitHub Pages deploy.

## Current state

- **Pipeline repo** (`~/Projects/Starwars_Anatomy_of_a_Catastrophe_...`):
  `episodes/episode-<ts>-<slug>-<hash>/` containing `metadata.json`,
  `story.md` (with `## DAY N: Title` headers — matches the site's reader
  format already), `images/`, auto-exported `.html/.epub/.txt`.
- **Site repo** (techmore/Gravedancer_to_General): static site; episodes are
  single files `episodes/NN-slug.md` with YAML frontmatter:
  `title, episode, tagline, target_jedi, jedi_species, jedi_philosophy,
  jedi_fate, setting, status (published|coming_soon|draft), published_at`.
  Push to main → Actions builds → Pages. Currently 2 published episodes.
  No image support yet.

## Design

### 1. New script: `scripts/publish_episode.py`

```
python scripts/publish_episode.py <episode_dir> [--status draft] [--episode N]
    [--no-push] [--site-repo ~/Projects/Gravedancer_to_General]
```

Steps:
1. Read `metadata.json` + `story.md`.
2. Strip pipeline preamble from story.md (the title/Generated/Days/Target
   Jedi/Setting block before the first `## DAY 1:`) — the site computes its
   own word counts and takes metadata from frontmatter.
3. Map frontmatter:
   - `title` ← metadata.title
   - `episode` ← next available number on the site (highest existing + 1),
     or explicit `--episode`
   - `target_jedi` ← jedi_name / target_jedi_name
   - `jedi_species`, `jedi_philosophy` (if present), `jedi_rank` → note in
     body or new field, `setting` ← setting
   - `tagline` ← NOT in metadata today. Options: add tagline to pipeline
     metadata generation (preferred), or derive from banner response /
     outline hook / first line of Day 1. Default: require `--tagline` flag
     or prompt if interactive.
   - `jedi_fate` ← derive from `story_resolution` (e.g. "Killed by Qymaen")
     or default `Unresolved`; allow override via flag.
   - `status` ← default `draft` so nothing goes live without review;
     `--publish` sets published + today's date.
4. Write `NN-<slug>.md` into the site repo's `episodes/`.
5. Validate: day headers parse, frontmatter fields present, no `DAY 0`
   preamble leakage. Fail loudly rather than publishing garbage.
6. Commit locally in the site repo with message
   `publish: EP-title (from pipeline episode-dir)`. Push unless `--no-push`.

### 2. Site repo handling

Keep a persistent clone at `~/Projects/Gravedancer_to_General`
(`git clone git@github.com:techmore/Gravedancer_to_General.git`).
The script pulls before writing, commits, pushes. Never force-push.

### 3. Images (phase 2)

The site has no image support today. Plan:
- Copy chosen images to site repo under `assets/img/<slug>/cover.jpg` etc.
- Add `cover:` and optional `images:` fields to frontmatter; extend the
  Jinja2 templates (archive card cover, hero image in reader) and build.py.
- Selection rule for now: cover = first generated image (or `--image` flag).

### 4. Post-pipeline integration

After PIPELINE COMPLETE, print the exact publish command as the last line of
the run summary, e.g.:

    Next: python scripts/publish_episode.py episodes/episode-2026...-hollow-bridge-c4b23835 --tagline "..." 

Optionally add `--auto-publish-draft` to run_creative_pipeline.py that runs
the publish step automatically (still lands as draft).

### 5. Safety rails

- Never publish straight to `published` by default (review pass first).
- Idempotent: re-running detects an existing file for the same episode dir
  (store source episode id in an HTML comment in the md) and updates it
  instead of duplicating.
- Word-count sanity check: warn if body < 5k words (a truncated run).

## Decisions (Sean, 2026-08-22)

1. **Push from script** — publish_episode.py pushes via `gh` (already authed on this machine).
2. **Text first, images phase 2.**
3. **Only fully-successful pipeline runs are publishable** — publish step
   refuses if the run didn't reach PIPELINE COMPLETE (check for a
   completion marker in metadata.json or the run log; add one if absent).
4. **Unpublish support** — `--unpublish <NN-slug>` removes the episode file
   and pushes; Pages rebuilds and it's gone (works fine — Pages is just the
   rebuilt dist/). Also support flipping status to `draft` (hidden from
   archive but file retained) as a softer option.
5. **Taglines not required** — omit from frontmatter mapping; site template
   should fall back gracefully (first sentence of Day 1 or nothing).

## Reading experience (new site work, in priority order)

1. **Hype/landing page per episode**: cover-style card page with title,
   tagline/hook, setting, target Jedi teaser, cover image (phase 2), and a
   "Begin Reading" CTA into the reader. `coming_soon` status shows the hype
   page without the read link.
2. **Page-turn reader mode**: default stays normal scroll (34k-word
   episodes make forced page-flips hostile to reading). Add a "book mode"
   toggle that presents one DAY at a time on an aged-document page with a
   CSS 3D page-turn transition between days. Keyboard ←/→ nav, progress
   indicator, remembers mode in localStorage.
3. **Aged-document toning (experimental)**: in book mode, render prose on a
   parchment-toned page — tan/yellow gradient, darker vignetted edges,
   subtle paper grain (tiny tiled CSS noise or one generated parchment
   texture image), sepia-tinted serif text. Behind the page: blurred,
   darkened starfield/nebula backdrop fitting the Star Wars tone. Keep the
   existing dark navy theme for normal mode; parchment is book-mode-only.
   Cheap to try: pure CSS gradients first, generated texture image only if
   CSS reads as flat.

## Open decisions

1. Repo auth: use `gh` credential helper (HTTPS) — confirm `gh auth status`.
2. Parchment via pure CSS vs generated texture asset — decide after first
   CSS attempt.

## Milestones

- M1: `publish_episode.py` — conversion + completion-gate + local commit,
  tested against hollow-bridge episode, dry-run mode.
- M2: push via `gh` + Pages deploy verified end-to-end; `--unpublish`.
- M3: site reader upgrades — hype/landing page, book-mode page-turn reader
  with parchment toning (CSS-first).
- M4: image support — covers in archive/hype pages, images embedded in
  reader; publish step copies them.
- M5: post-pipeline hint / optional auto-publish of successful runs.
