"""Title overlay for generated cover art.

Composites the episode title (and byline) onto the 2:3 cover render with a
cinematic gradient scrim so the text stays legible over any artwork.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)

# macOS ships these; fall back gracefully if missing.
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Trajan Pro.ttf",
    "/Library/Fonts/Trajan Pro.ttf",
    "/System/Library/Fonts/Supplemental/Futura.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font(size: int):
    from PIL import ImageFont
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def overlay_title(
    image_path: Path,
    title: str,
    subtitle: str = "",
    output_path: Path | None = None,
) -> Path:
    """Draw title/subtitle onto the lower third of the cover image.

    Overwrites ``image_path`` in place unless ``output_path`` is given.
    Returns the path written.
    """
    from PIL import Image, ImageDraw

    img = Image.open(image_path).convert("RGB")
    out = output_path or image_path
    w, h = img.size
    draw = ImageDraw.Draw(img)

    # Gradient scrim across the lower 45% for legibility.
    scrim = Image.new("L", (1, h), 0)
    scrim_draw = ImageDraw.Draw(scrim)
    scrim_top = int(h * 0.55)
    for y in range(scrim_top, h):
        alpha = int(200 * ((y - scrim_top) / max(1, h - scrim_top)) ** 1.4)
        scrim_draw.point((0, y), fill=alpha)
    scrim = scrim.resize((w, h))
    black = Image.new("RGB", (w, h), (8, 8, 12))
    img = Image.composite(black, img, scrim)

    draw = ImageDraw.Draw(img)

    # Auto-size: title wraps within 86% width.
    title = title.upper()
    size = int(w * 0.085)
    while size > 18:
        font = _load_font(size)
        if _fits(draw, font, title, int(w * 0.86)):
            break
        size -= 4
    lines = _wrap(draw, _load_font(size), title, int(w * 0.86))

    line_h = int(size * 1.18)
    sub_size = max(16, int(w * 0.032))
    sub_font = _load_font(sub_size)
    block_h = len(lines) * line_h + (sub_size * 2 if subtitle else 0)
    y = h - block_h - int(h * 0.06)

    for line in lines:
        lw = draw.textlength(line, font=_load_font(size))
        # Soft shadow then fill.
        x = (w - lw) / 2
        draw.text((x + 2, y + 2), line, font=_load_font(size), fill=(0, 0, 0))
        draw.text((x, y), line, font=_load_font(size), fill=(232, 226, 210))
        y += line_h

    if subtitle:
        sw = draw.textlength(subtitle, font=sub_font)
        x = (w - sw) / 2
        draw.text((x + 1, y + 6), subtitle, font=sub_font, fill=(0, 0, 0))
        draw.text((x, y + 5), subtitle, font=sub_font, fill=(190, 160, 90))

    img.save(out, format="PNG")
    LOGGER.info("cover title overlay written path=%s", out)
    return out


def _fits(draw, font, text: str, max_w: int) -> bool:
    return draw.textlength(text, font=font) <= max_w


def _wrap(draw, font, text: str, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines
