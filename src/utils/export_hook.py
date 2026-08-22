"""Post-save export hook: write reading formats alongside a saved episode.

Used by the creative pipelines so every generated episode lands on disk with
its reader-facing exports (plain text, standalone HTML, EPUB) already written
— no separate export step required. Failures are non-fatal: an episode must
never fail at bookkeeping.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.utils.export_formats import (
    suggest_file_stem,
    to_epub_bytes,
    to_html,
    to_plain_text,
)

LOGGER = logging.getLogger(__name__)


def _auto_open_enabled() -> bool:
    """True when exports should auto-open on completion (macOS, not disabled)."""
    flag = os.environ.get("GRAVEDANCER_AUTO_OPEN", "1").strip().lower()
    return flag not in {"0", "false", "off"} and sys.platform == "darwin"


def _collect_episode_images(ep_dir: Path) -> dict[str, bytes]:
    """Map saved keyframe images to export keys.

    File naming from EpisodeStorage.save_image: ``day-NN-<shot>[-vN].png``.
    Keys: "banner" (banner shot), "day-N" (day-N-hero), "day-N-chM".
    """
    images: dict[str, bytes] = {}
    imgs = ep_dir / "images"
    if not imgs.is_dir():
        return images
    pattern = re.compile(
        r"^day-(\d+)-(.+?)(?:-v\d+)?\.png$", re.IGNORECASE)
    for path in sorted(imgs.glob("*.png")):
        m = pattern.match(path.name)
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if path.name.startswith("day-00-") or "banner" in path.name.lower():
            images.setdefault("banner", data)
            continue
        if not m:
            continue
        day, shot = int(m.group(1)), m.group(2).lower()
        if "-ch" in shot:
            day_part, ch_part = shot.split("-ch", 1)
            ch_num = re.sub(r"\D", "", ch_part) or "1"
            images.setdefault(f"day-{day}-ch{int(ch_num)}", data)
        elif "hero" in shot:
            images.setdefault(f"day-{day}", data)
        else:
            images.setdefault(f"day-{day}", data)
    return images


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

    # Collect saved keyframes: cover + per-day/chapter plates.
    episode_images = _collect_episode_images(ep_dir)
    cover = episode_images.get("banner")
    if cover is None:
        try:
            imgs = ep_dir / images_dir_name
            if imgs.is_dir():
                pngs = sorted(imgs.glob("*.png"))
                if pngs:
                    cover = max(pngs, key=lambda p: p.stat().st_mtime).read_bytes()
        except OSError as exc:
            LOGGER.warning("export cover lookup failed: %s", exc)

    jobs = (
        (f"{stem}.txt", lambda: to_plain_text(title, story_md, metadata).encode("utf-8")),
        (f"{stem}.html", lambda: to_html(
            title, story_md, metadata,
            images={"banner": cover} if cover and not episode_images else (
                episode_images or ({"banner": cover} if cover else {}))).encode("utf-8")),
        (f"{stem}.epub", lambda: to_epub_bytes(
            title, story_md, metadata, cover_image=cover,
            images=episode_images)),
    )
    for filename, build in jobs:
        try:
            path = ep_dir / filename
            path.write_bytes(build())
            written.append(str(path))
            LOGGER.info("export written path=%s", path)
        except Exception as exc:
            LOGGER.warning("export failed name=%s error=%s", filename, exc)

    if written and _auto_open_enabled():
        # Open the richest reading format first (epub > html > txt).
        best = written[-1]
        try:
            subprocess.Popen(["open", best])
            LOGGER.info("export auto-opened path=%s", best)
        except OSError as exc:
            LOGGER.warning("auto-open failed path=%s error=%s", best, exc)
    return written
