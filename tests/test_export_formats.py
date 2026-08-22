"""Tests for src/utils/export_formats.py."""

from pathlib import Path

import pytest

from src.utils.export_formats import (
    episode_meta_line,
    parse_story_sections,
    suggest_file_stem,
    to_epub_bytes,
    to_html,
    to_plain_text,
)

STORY_MD = """# The Ashen Chain

**Generated:** 2026-08-22T10:17:29

**Days:** 2

---

## DAY 1: Red Sun Landing

### Chapter 1: Shot Out of the Sky
The interdictor flare took the gunship apart at altitude.

He rode the wreck down through a dying red sun.

### Chapter 2: The Skinned Scout
He found the scout at dusk, strung high in the ashvines.

## DAY 2: The Cage and the Chain

Dawn came up bruise-colored.

### Chapter 1: Terms Under Truce Flag
Dawn came up bruise-colored, and with it walked Nyx Vex.
"""

META = {
    "title": "The Ashen Chain",
    "jedi_name": "Nyx Vex",
    "num_days": 2,
    "setting": "Jungle moon with ruins of an ancient civilization. Perpetual twilight.",
}


def test_parse_story_sections_extracts_days_and_chapters():
    sections = parse_story_sections(STORY_MD)
    assert [s.number for s in sections] == [1, 2]
    assert sections[0].title == "Red Sun Landing"
    assert [c["number"] for c in sections[0].chapters] == [1, 2]
    assert sections[0].chapters[0]["text"].startswith("The interdictor flare")
    # Day 2 has intro prose before its first chapter
    assert sections[1].intro.startswith("Dawn came up bruise-colored.")


def test_parse_story_sections_empty_and_unstructured():
    assert parse_story_sections("") == []
    unstructured = parse_story_sections("Just some prose without day markers.")
    assert len(unstructured) == 1
    assert "Just some prose" in unstructured[0].intro


def test_plain_text_wraps_and_cleans_markdown():
    text = to_plain_text("The Ashen Chain", STORY_MD, META, width=60)
    assert "DAY 1: RED SUN LANDING" in text
    assert "Chapter 2: The Skinned Scout" in text
    assert "**" not in text
    assert "# The Ashen Chain" not in text
    for line in text.splitlines():
        assert len(line) <= 80


def test_html_is_standalone_document():
    out = to_html("The Ashen Chain", STORY_MD, META)
    assert out.startswith("<!DOCTYPE html>")
    assert "<style>" in out
    assert "Red Sun Landing" in out or "RED SUN LANDING" in out
    assert "Shot Out of the Sky" in out


def test_html_escapes_html_in_story():
    story = "## DAY 1: X\n\n<script>alert(1)</script>"
    out = to_html("T", story, {})
    assert "<script>" not in out.replace("<h2", "").replace("<body", "")
    assert "&lt;script&gt;" in out


def test_epub_bytes_produce_valid_zip(tmp_path: Path):
    data = to_epub_bytes("The Ashen Chain", STORY_MD, META)
    import zipfile
    from io import BytesIO

    zf = zipfile.ZipFile(BytesIO(data))
    names = zf.namelist()
    assert "mimetype" in names
    assert any(n.endswith(".xhtml") for n in names)
    content = zf.read("EPUB/day-1.xhtml").decode("utf-8")
    assert "Red Sun Landing" in content


def test_episode_meta_line():
    line = episode_meta_line(META)
    assert "Nyx Vex" in line
    assert "2 days" in line


def test_suggest_file_stem():
    stem = suggest_file_stem("episode-20260822-101729-the-ashen-chain-x", "The Ashen Chain!")
    assert stem.startswith("20260822-")
    assert stem == stem.strip("-")


@pytest.mark.parametrize("fmt", ["txt", "html"])
def test_roundtrip_from_saved_episode(fmt):
    """Formatters accept the exact story.md shape saved by EpisodeStorage."""
    saved = (
        "# The Ashen Chain\n\n**Generated:** x\n**Days:** 2\n\n---\n" + STORY_MD.split("---", 1)[1]
    )
    if fmt == "txt":
        out = to_plain_text("T", saved, META)
    else:
        out = to_html("T", saved, META)
    assert "Red Sun Landing" in out or "RED SUN LANDING" in out
