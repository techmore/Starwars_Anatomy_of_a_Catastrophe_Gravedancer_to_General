"""Story quality validation.

Catches the failure modes seen in early episodes (qwen3:8b produced five
near-identical days of content). Does NOT block — surfaces warnings only.
"""

import re
from typing import Any

from src.utils.prompt_schema import TARGET_WORDS_PER_DAY

# Below this fraction of the target length we flag a short story.
SHORT_FRACTION = 0.7
TARGET_WORDS = TARGET_WORDS_PER_DAY


def strip_saved_episode_header(story: str) -> str:
    """Return the generated body without the storage-owned Markdown header."""
    text = str(story or "")
    match = re.search(r"^##\s*DAY\s+\d+\b", text, re.MULTILINE | re.IGNORECASE)
    return text[match.start():].lstrip() if match else text.strip()


def deduplicate_story(story: str) -> tuple[str, dict[str, int]]:
    """Remove only repeated model output while preserving first occurrences.

    This is a recovery step for local models that occasionally copy a full
    paragraph or restart a sentence loop. Markdown headings and episode
    metadata are never removed. Sentence signatures are scoped globally so a
    repeated opening cannot recur across days.
    """
    parts = re.split(r"(\n\s*\n)", str(story or ""))
    seen_paragraphs = set()
    seen_sentence_starts = set()
    seen_metadata_lines = set()
    output = []
    removed_paragraphs = 0
    removed_sentences = 0
    for part in parts:
        if not part.strip():
            output.append(part)
            continue
        stripped = part.strip()
        if stripped.startswith(("#", "**Generated:", "**Days:", "**Target Jedi:", "**Setting:")):
            # Models can replay the complete episode header at the start of
            # several passes. Preserve the first copy, but remove exact
            # duplicate title/metadata lines from the saved artifact.
            if stripped in seen_metadata_lines:
                removed_paragraphs += 1
                continue
            seen_metadata_lines.add(stripped)
            output.append(part)
            continue
        normalized = re.sub(r"\s+", " ", stripped.lower())
        if len(stripped) > 80 and normalized in seen_paragraphs:
            removed_paragraphs += 1
            continue
        seen_paragraphs.add(normalized)
        kept_sentences = []
        for sentence in re.split(r"(?<=[.!?])\s+", stripped):
            sentence_clean = sentence.strip()
            signature = " ".join(sentence_clean.lower().split()[:8])
            if 40 < len(sentence_clean) < 400 and signature in seen_sentence_starts:
                removed_sentences += 1
                continue
            if 40 < len(sentence_clean) < 400:
                seen_sentence_starts.add(signature)
            kept_sentences.append(sentence_clean)
        output.append(" ".join(kept_sentences))
    return "".join(output), {
        "removed_paragraphs": removed_paragraphs,
        "removed_sentence_starts": removed_sentences,
    }


def validate_story(story: str, expected_days: int | None = None) -> dict[str, Any]:
    """Return a report dict with warnings + raw metrics."""
    report: dict[str, Any] = {
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

    if expected_days and num_days != expected_days:
        report["warnings"].append(
            f"Story has {num_days} day(s) but {expected_days} were requested."
        )

    # Word count
    target_word_count = TARGET_WORDS * max(expected_days or 1, 1)
    if word_count < int(target_word_count * SHORT_FRACTION):
        report["warnings"].append(
            f"Story is only ~{word_count:,} words (target ~{target_word_count:,}). "
            "It may be truncated."
        )

    # Duplicate paragraph detection — the qwen3:8b failure mode.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", story) if len(p.strip()) > 80]
    seen: dict[str, int] = {}
    dupes: list[str] = []
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
    sig_seen: dict[str, int] = {}
    near_dupes: list[str] = []
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

    report.update(canon_check(story))
    report["warnings"].extend(report.get("canon_violations", []))

    fuzzy_dupes = near_duplicate_paragraphs(story)
    report["near_duplicate_paragraphs"] = fuzzy_dupes
    if fuzzy_dupes:
        report["warnings"].append(
            f"{len(fuzzy_dupes)} paraphrase-duplicated paragraph(s) found — "
            "likely a generation loop; regenerate the affected section."
        )

    return report


# Era-appropriateness checklist. The series is explicitly pre-Clone Wars:
# no Republic clone army, no Separatist droid armies, and Qymaen has not
# yet become Grievous. Terms are matched case-insensitively.
_CANON_TERM_RE = re.compile(
    r"\b(clone\s+troopers?|the\s+clone\s+wars|separatist[sz]?m?|"
    r"confederacy\s+of\s+independent\s+systems|general\s+grievous|"
    r"count\s+dooku)\b",
    re.IGNORECASE,
)
# Qymaen must never wield a lightsaber; Jedi targets may.
_QYMAEN_SABER_RE = re.compile(
    r"(?:qymaen|gravedancer)[^.!?]{0,80}?\blightsaber\b|"
    r"\blightsaber\b[^.!?]{0,80}?(?:qymaen|his own lightsaber)",
    re.IGNORECASE,
)


def canon_check(story: str) -> dict[str, Any]:
    """Scan for anachronisms against the series' pre-Clone Wars premise.

    Returns {"canon_violations": [str, ...]} — human-readable warnings, also
    mirrored into the report's warning list by validate_story().
    """
    violations: list[str] = []
    text = str(story or "")
    for m in _CANON_TERM_RE.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        violations.append(
            f"canon: era-inappropriate term '{m.group(0)}' near line {line_no} "
            "(series is pre-Clone Wars)"
        )
    for m in _QYMAEN_SABER_RE.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        violations.append(
            f"canon: Qymaen appears to wield a lightsaber near line {line_no} "
            "(he fights with rifle/blade until his cybernetic era)"
        )
    return {"canon_violations": violations}


def near_duplicate_paragraphs(story: str, min_words: int = 35,
                              overlap: float = 0.7) -> list[str]:
    """Detect paragraphs that paraphrase-repeat (not exact matches).

    Two long paragraphs whose 8-word shingle sets overlap beyond ``overlap``
    are considered a generation loop even when wording drifts slightly.
    """
    paragraphs = [
        p.strip() for p in re.split(r"\n\s*\n", str(story or ""))
        if len(p.strip().split()) >= min_words
    ]
    shingles = []
    for p in paragraphs:
        words = re.sub(r"\s+", " ", p.lower()).split()
        shingles.append({tuple(words[i:i + 8]) for i in range(len(words) - 7)})
    flagged: list[str] = []
    reported: set[int] = set()
    for i in range(len(paragraphs)):
        if i in reported or not shingles[i]:
            continue
        for j in range(i + 1, len(paragraphs)):
            if j in reported or not shingles[j]:
                continue
            inter = len(shingles[i] & shingles[j])
            smaller = min(len(shingles[i]), len(shingles[j]))
            if smaller and inter / smaller > overlap:
                flagged.append(paragraphs[j][:120])
                reported.add(j)
                break
    return flagged
