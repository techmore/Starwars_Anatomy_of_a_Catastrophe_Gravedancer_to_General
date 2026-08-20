# Build Request: GitHub Pages Website for "Gravedancer to General: Anatomy of a Catastrophe"

## Context

You are building a static website for a Star Wars fan fiction series. The series follows **Qymaen jai Sheelal** (the Gravedancer) on his path toward becoming **General Grievous** — a pre-Clone Wars origin story. Each episode is a self-contained novella (~7,500 words per day, 3-8 days per episode) with a day-by-day chapter structure. New episodes will be released as **weekly installments**.

**Series title:** *Gravedancer to General: Anatomy of a Catastrophe*
**Author/creator:** techmore
**Tone:** Cinematic, visceral, atmospheric. Military thriller pacing, gothic war-story atmosphere, mythic tragedy.
**Format:** Each episode has a title, target Jedi, setting, and 3-8 daily chapters.

## Data Model

Each episode has:
- **title** — e.g. "The Silencing of Kaelen Voss"
- **episode number** — sequential (1, 2, 3...)
- **tagline** — a one-line hook
- **target_jedi** — name of the Jedi being hunted
- **setting** — planet/location
- **num_days** — how many daily chapters
- **story** — full markdown body with `## DAY N:` chapter headers
- **published_at** — release date
- **status** — `published`, `coming_soon`, or `draft`
- **word_count** — total word count across all days

## What to Build

A clean, mobile-first static site hosted on **GitHub Pages** (Jekyll or plain HTML/CSS/JS — your choice). The site must support:

### 1. Episode Archive
- A main page listing all episodes in reverse chronological order (newest first)
- Each entry shows: episode number, title, tagline, target Jedi, setting, word count, published date, status badge
- Sort/filter controls: by status (published/coming soon), by target Jedi, by setting
- A visual indicator for which episodes have been read

### 2. Episode Reader
- A dedicated page for each episode
- Day-by-day navigation (prev day / next day buttons, or a chapter dropdown)
- "Next Episode" and "Previous Episode" links at the bottom
- A progress indicator showing which day you're on
- Clean prose formatting: serif font, comfortable line height (1.8), max line width (~700px), dark mode toggle
- Word count and estimated reading time at the top

### 3. Weekly Installment UX
- A "Subscribe" / "Follow" section pointing to wherever updates are announced (RSS, Twitter, etc.)
- A "What's New" banner for the most recently published episode
- Coming soon / preview section for upcoming episodes

### 4. About / Lore Pages
- A page explaining the series premise and setting (Pre-Clone Wars, Kaleesh culture, Qymaen's transformation arc)
- A "Jedi Index" — a list of all original Jedi characters introduced so far, with their philosophy, species, and fate
- A "Glossary" for Kaleesh terms, technology, and factions

### 5. Design Direction
- **Star Wars aesthetic** but subdued — think Codex/archive, not movie poster
- Dark background (#1a1a2e or similar deep navy/charcoal), gold/amber accents (#d4a373), muted olive for secondary text
- Serif font for prose (e.g. EB Garamond, Lora, or Playfair Display from Google Fonts)
- Sans-serif for navigation and UI
- Mobile-first responsive design
- Fast loading — static HTML, no JS frameworks, minimal dependencies
- Dark mode as default, light mode toggle

### 6. Technical Requirements
- GitHub Pages compatible (no server-side rendering, no backend, no database)
- All episode content stored as flat markdown files or JSON
- A build script (Python or shell) that regenerates the site from episode data
- RSS feed generation for subscribers
- sitemap.xml for SEO
- Open Graph / Twitter Card meta tags for each episode page
- Zero external tracking — privacy-first

## What to Deliver

Your response should include:

1. **Architecture decision** — Jekyll vs plain HTML/CSS/JS? Why?
2. **File/folder structure** — the complete directory tree
3. **Build pipeline** — how new episodes get added and the site regenerated
4. **Key design decisions** — dark mode, navigation, responsive breakpoints
5. **The actual code** — index page, episode template, about page, CSS, and build script
6. **Deployment instructions** — how to set up GitHub Pages and deploy

Build this as if you're handing it off to a developer who will maintain and extend it. Every page, component, and script should be complete and functional.
