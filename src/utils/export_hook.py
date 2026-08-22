"""Post-save export hook: write reading formats alongside a saved episode.

Used by the creative pipelines so every generated episode lands on disk with
its reader-facing exports (plain text, standalone HTML, EPUB) already written
— no separate export step required. Failures are non-fatal: an episode must
never fail at bookkeeping.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.utils.export_formats import (
    suggest_file_stem,
    to_epub_bytes,
    to_html,
    to_plain_text,
)

LOGGER = logging.getLogger(__name__)


def write_reading_formats(
    storage,  # EpisodeStorage
    episode_id: str,
    story_md: str,
    metadata: dict[str, Any],
    images_dir_name: str = "images",
) -> list[str]:
    """Write .txt/.html/.epub exports into the episode directory.

    Returns the list of written paths; on any per-format failure the error is
    logged and the remaining formats are still attempted.
    """
    written: list[str] = []
    try:
        ep_dir = Path(storage._resolve_episode_dir(episode_id))
    except Exception:
        LOGGER.warning("export skip: cannot resolve episode dir id=%s", episode_id)
        return written

    title = str(metadata.get("title", "Episode"))
    stem = suggest_file_stem(episode_id, title)

    # Cover: newest banner image if one exists.
    cover: bytes | None = None
    try:
        imgs = ep_dir / images_dir_name
        if imgs.is_dir():
            pngs = sorted(imgs.glob("*.png"))
            banners = [p for p in pngs if "banner" in p.name.lower()]
            candidates = banners or pngs
            if candidates:
                cover = max(candidates, key=lambda p: p.stat().st_mtime).read_bytes()
    except OSError as exc:
        LOGGER.warning("export cover lookup failed: %s", exc)

    jobs = (
        (f"{stem}.txt", lambda: to_plain_text(title, story_md, metadata).encode("utf-8")),
        (f"{stem}.html", lambda: to_html(title, story_md, metadata).encode("utf-8")),
        (f"{stem}.epub", lambda: to_epub_bytes(title, story_md, metadata, cover_image=cover)),
    )
    for filename, build in jobs:
        try:
            path = ep_dir / filename
            path.write_bytes(build())
            written.append(str(path))
            LOGGER.info("export written path=%s", path)
        except Exception as exc:
            LOGGER.warning("export failed name=%s error=%s", filename, exc)
    return written
