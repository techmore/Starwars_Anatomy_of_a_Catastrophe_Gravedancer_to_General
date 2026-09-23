"""Compatibility helpers for saved visual-prompt payloads."""

from typing import Any


def prompt_sets_from_payload(prompts: object) -> list[dict[str, Any]]:
    """Return visual prompt sets from legacy or structured payloads.

    The Streamlit prompt tools historically stored sets under ``scenes``.
    The structured pipeline stores chapter-level visual sets under
    ``chapters`` and deliberately leaves ``scenes`` empty.  Prefer a
    non-empty legacy list when present, then fall back to the structured
    list so both formats remain readable without double-counting them.
    """
    if not isinstance(prompts, dict):
        return []
    for key in ("scenes", "chapters", "prompt_sets"):
        value = prompts.get(key)
        if not isinstance(value, list):
            continue
        entries = [item for item in value if isinstance(item, dict)]
        if entries:
            return entries
    return []


def banner_prompt_from_payload(prompts: object) -> str:
    """Return a banner prompt from either supported banner field name."""
    if not isinstance(prompts, dict):
        return ""
    banner = prompts.get("banner")
    if not isinstance(banner, dict):
        return ""
    for key in ("banner_prompt", "prompt"):
        value = banner.get(key)
        if isinstance(value, str) and value:
            return value
    return ""
