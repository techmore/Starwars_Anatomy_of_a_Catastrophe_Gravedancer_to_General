"""Cross-episode memory ("series bible").

Episode n+1 should know episode n. After each completed episode a compact
JSON entry (Jedi fate, injuries, artifacts, unresolved threads) is merged
into ``episodes/series-bible.json``; new runs inject a digest of earlier
entries into concept and outline prompts so the series accumulates
continuity instead of restarting from zero every episode.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union

from src.utils.logging_utils import get_logger


LOGGER = get_logger(__name__)

BIBLE_FILENAME = "series-bible.json"
# Injection cap: the digest rides along in every outline/section prompt, so it
# must stay small even after dozens of episodes (newest entries win).
BIBLE_PROMPT_MAX_CHARS = 4000
BIBLE_PROMPT_MAX_EPISODES = 8


def bible_path(base_path: Union[str, Path]) -> Path:
    return Path(base_path) / BIBLE_FILENAME


def load_entries(base_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Read all episode entries; a missing or corrupt file means empty history."""
    path = bible_path(base_path)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("series bible unreadable path=%s error=%s", path, exc)
        return []
    entries = payload.get("episodes") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def update_entry(base_path: Union[str, Path], entry: Dict[str, Any]) -> Path:
    """Merge *entry* into the bible (replacing any prior entry with the same title)."""
    base = Path(base_path)
    base.mkdir(parents=True, exist_ok=True)
    path = bible_path(base)
    title = str(entry.get("title") or "").strip()
    entries = [
        existing
        for existing in load_entries(base)
        if str(existing.get("title") or "").strip() != title
    ]
    stored = dict(entry)
    stored["recorded_at"] = datetime.now().isoformat()
    entries.append(stored)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"episodes": entries}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)
    LOGGER.info("series bible updated path=%s entries=%s title=%s", path, len(entries), title)
    return path


def build_entry_prompt(title: str, story: str) -> str:
    """Build the extraction prompt that turns a finished episode into one JSON entry."""
    return f"""Summarize the completed episode "{title}" as ONE JSON object for the series bible of "Gravedancer to General".

**EPISODE STORY:**
{story}

Return ONLY the JSON object — no markdown fence, no commentary — with exactly these keys:
{{
  "title": "<episode title>",
  "jedi": {{"name": "<jedi name>", "species": "<species>", "fate": "<final outcome in one clause>"}},
  "setting": "<one-line location summary>",
  "key_events": ["<3-6 short factual plot beats>"],
  "injuries": ["<lasting wounds for Qymaen or others, if any>"],
  "artifacts": ["<notable objects and where they ended up>"],
  "unresolved_threads": ["<open loops a future episode could continue>"]
}}
Facts only, drawn from the story above. Do not invent events."""


def parse_entry(text: str) -> Dict[str, Any] | None:
    """Extract a bible entry from a model response; None when unusable."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not str(data.get("title") or "").strip():
        return None
    return data


def format_for_prompt(
    entries: List[Dict[str, Any]],
    max_chars: int = BIBLE_PROMPT_MAX_CHARS,
) -> str:
    """Render earlier-episode digests for injection into concept/outline prompts."""
    blocks: List[str] = []
    for entry in entries[-BIBLE_PROMPT_MAX_EPISODES:]:
        lines = [f'- Episode "{str(entry.get("title") or "Untitled").strip()}"']
        jedi = entry.get("jedi")
        if isinstance(jedi, dict):
            name = str(jedi.get("name") or "").strip()
            fate = str(jedi.get("fate") or "").strip()
            if name:
                lines.append(f"  Jedi: {name}" + (f" — {fate}" if fate else ""))
        setting = str(entry.get("setting") or "").strip()
        if setting:
            lines.append(f"  Setting: {setting}")
        for key, label in (
            ("key_events", "Events"),
            ("injuries", "Injuries"),
            ("artifacts", "Artifacts"),
            ("unresolved_threads", "Unresolved"),
        ):
            values = [str(v).strip() for v in (entry.get(key) or []) if str(v).strip()]
            if values:
                lines.append(f"  {label}: " + "; ".join(values))
        blocks.append("\n".join(lines))
    text = "\n".join(blocks).strip()
    if len(text) > max_chars:
        text = text[-max_chars:]
        newline = text.find("\n")
        if newline != -1:
            text = text[newline + 1:]
    return text
