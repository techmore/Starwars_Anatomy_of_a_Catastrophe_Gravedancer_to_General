"""Story quality validation.

Catches the failure modes seen in early episodes (qwen3:8b produced five
near-identical days of content). Does NOT block — surfaces warnings only.
"""

import re
from typing import Dict, Any, List

# Below this fraction of the target length we flag a short story.
SHORT_FRACTION = 0.7
TARGET_WORDS = 7500


def validate_story(story: str, expected_days: int | None = None) -> Dict[str, Any]:
    """Return a report dict with warnings + raw metrics."""
    report: Dict[str, Any] = {
        "warnings": [],
        "word_count": 0,
        "num_days_found": 0,
        "expected_days": expected_days,
        "duplicate_paragraphs": [],
        "duplicate_sentences": [],
    }
    if not story or not story.strip():
        report["warnings"].append("Story is empty.")
        return report

    words = story.split()
    word_count = len(words)
    report["word_count"] = word_count

    # Day count
    days = re.findall(r"^##\s*DAY\s+(\d+)", story, re.MULTILINE | re.IGNORECASE)
    num_days = len(days)
    report["num_days_found"] = num_days

    if expected_days and num_days and num_days < expected_days:
        report["warnings"].append(
            f"Story has {num_days} day(s) but {expected_days} were requested."
        )

    # Word count
    if word_count < int(TARGET_WORDS * SHORT_FRACTION):
        report["warnings"].append(
            f"Story is only ~{word_count:,} words (target ~{TARGET_WORDS:,}). "
            "It may be truncated."
        )

    # Duplicate paragraph detection — the qwen3:8b failure mode.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", story) if len(p.strip()) > 80]
    seen: Dict[str, int] = {}
    dupes: List[str] = []
    for p in paragraphs:
        norm = re.sub(r"\s+", " ", p.lower())
        if norm in seen:
            dupes.append(p[:120])
        else:
            seen[norm] = 1
    report["duplicate_paragraphs"] = dupes
    if dupes:
        report["warnings"].append(
            f"{len(dupes)} duplicated paragraph(s) found — the model may be "
            "repeating itself. Try a larger model or regenerate the affected day(s)."
        )

    # Near-duplicate sentence detection (catches paraphrased repetition).
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", story))
    sentences = [s.strip().lower() for s in sentences if 40 < len(s.strip()) < 400]
    sig_seen: Dict[str, int] = {}
    near_dupes: List[str] = []
    for s in sentences:
        # 8-word signature — cheap near-dup heuristic.
        sig = " ".join(s.split()[:8])
        if sig in sig_seen:
            near_dupes.append(s[:120])
        else:
            sig_seen[sig] = 1
    if len(near_dupes) >= 3:
        report["duplicate_sentences"] = near_dupes[:5]
        report["warnings"].append(
            f"{len(near_dupes)} sentence(s) start identically — possible "
            "copy-paste repetition across days."
        )

    return report


def render_warnings(report: Dict[str, Any]) -> None:
    """Render quality warnings as Streamlit alert cards (if any)."""
    import streamlit as st

    warnings = report.get("warnings") or []
    if not warnings:
        return

    body = "\n".join(f"• {w}" for w in warnings)
    st.markdown(
        f'<div class="quality-warn"><strong>⚠️ Quality check</strong><br/>{body}</div>',
        unsafe_allow_html=True,
    )
