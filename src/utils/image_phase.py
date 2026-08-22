"""Image generation phase for the creative pipelines.

Generates keyframe images for a saved episode via Draw Things, with a
generation budget controlled by ``--max-images``:

    cover          1 image (episode banner)            — always first
    day            1 per day (day hero shot)           — default mode
    chapter        1 per chapter (~5/day + banner)     — full mode

Default is "day" mode: a 6-day episode = 7 generations total
(1 cover + 6 day heroes). Chapter mode on the same episode = 36.

Character reference images from ``<episode>/refs/`` are noted in prompts so
the operator can load them as multi-reference anchors in Draw Things.
"""

from __future__ import annotations

from typing import Any

from src.utils.drawthings_client import DrawThingsClient
from src.utils.export_formats import parse_story_sections
from src.utils.logging_utils import get_logger
from src.utils.storage import EpisodeStorage

LOGGER = get_logger(__name__)

MODE_DAY = "day"
MODE_CHAPTER = "chapter"


def count_planned_images(
    story_md: str,
    mode: str = MODE_DAY,
) -> dict[str, int]:
    """Return how many images a run would generate without generating them."""
    sections = parse_story_sections(story_md)
    days = len(sections)
    chapters = sum(len(s.chapters) or 1 for s in sections)
    if mode == MODE_CHAPTER:
        return {"cover": 1, "days": 0, "chapters": chapters, "total": 1 + chapters}
    return {"cover": 1, "days": days, "chapters": 0, "total": 1 + days}


def _scene_text_for_day(section) -> str:
    """Best text to describe a day's hero shot."""
    if section.intro:
        return section.intro[:1200]
    if section.chapters:
        return f"{section.heading}. {section.chapters[0]['text']}"[:1200]
    return section.heading


def build_day_prompt(title: str, section, metadata: dict[str, Any]) -> str:
    setting = str(metadata.get("setting", "")).split(".")[0]
    jedi = metadata.get("jedi_name", "")
    return (
        f"Cinematic Star Wars illustration, painterly sci-fi realism. "
        f"Episode '{title}', Day {section.number}: {section.title}. "
        f"{_scene_text_for_day(section)} "
        f"Setting: {setting}. "
        + (f"The Jedi {jedi} looms in the background as a distant silhouette. " if jedi else "")
        + "Wide establishing composition, volumetric light, dramatic atmosphere, NO text, no letters."
    )


def build_chapter_prompt(title: str, section, chapter: dict[str, Any]) -> str:
    return (
        f"Cinematic Star Wars illustration, painterly sci-fi realism. "
        f"Episode '{title}', Day {section.number}, Chapter {chapter['number']}: "
        f"{chapter['title']}. {chapter['text'][:900]} "
        f"Single character focus or wide-distant silhouettes; never medium-shot two characters. "
        f"Volumetric light, dramatic atmosphere, NO text, no letters."
    )


def generate_episode_images(
    storage: EpisodeStorage,
    dt_client: DrawThingsClient,
    episode_id: str,
    story_md: str,
    metadata: dict[str, Any],
    mode: str = MODE_DAY,
    max_images: int | None = None,
    aspect_ratio: str = "16:9",
    steps: int = 4,
    cfg: float = 2.5,
    width: int = 1024,
    height: int = 576,
    progress=None,
) -> list[dict[str, Any]]:
    """Generate and save episode images. Returns a manifest of results.

    Budget: the cover counts against max_images. Generation stops cleanly
    when the budget is exhausted, so --max-images 3 on a 6-day episode
    yields cover + 2 day heroes.
    """
    title = str(metadata.get("title", "Episode"))
    sections = parse_story_sections(story_md)
    results: list[dict[str, Any]] = []
    budget = max_images if max_images is not None else 10**9

    def _generate(label: str, prompt: str, day: int, shot: str) -> dict[str, Any] | None:
        nonlocal budget
        if budget <= 0:
            return None
        LOGGER.info("image gen begin label=%s budget_left=%s", label, budget)
        try:
            png = dt_client.generate_image(
                prompt=prompt, width=width, height=height, steps=steps, cfg=cfg)
            rel = storage.save_image(episode_id, day=day, shot=shot, image_bytes=png)
            budget -= 1
            entry = {"label": label, "path": rel, "prompt_chars": len(prompt)}
            results.append(entry)
            LOGGER.info("image gen done label=%s path=%s", label, rel)
            return entry
        except Exception as exc:
            LOGGER.warning("image gen failed label=%s error=%s", label, exc)
            results.append({"label": label, "error": str(exc)})
            return None

    # Cover always comes first.
    banner_setting = str(metadata.get("setting", "")).split(".")[0]
    cover_prompt = (
        f"Epic cinematic banner, painterly Star Wars realism. Episode '{title}'. "
        f"{banner_setting}. The hunter-warlord and the Jedi adversary in opposition, "
        f"wide-distant silhouettes across a monumental landscape. "
        f"Volumetric light, NO text, no letters."
    )
    _generate("cover", cover_prompt, 0, "banner")

    def _emit(msg: str) -> None:
        if progress:
            progress(msg)

    if mode == MODE_CHAPTER:
        for sec in sections:
            for ch in sec.chapters:
                if budget <= 0:
                    break
                _emit(f"Day {sec.number} ch{ch['number']}: {ch['title']}")
                _generate(
                    f"d{sec.number}-c{ch['number']}",
                    build_chapter_prompt(title, sec, ch),
                    sec.number,
                    f"day{sec.number}-ch{ch['number']}",
                )
    else:
        for sec in sections:
            if budget <= 0:
                break
            _emit(f"Day {sec.number}: {sec.title}")
            _generate(
                f"d{sec.number}-hero",
                build_day_prompt(title, sec, metadata),
                sec.number,
                f"day{sec.number}-hero",
            )

    return results
