"""Episode concept generation + parsing.

Moved out of app.py so the Story tab and any future UI can reuse it.
Includes the markdown-bold stripping fix (LLMs sometimes wrap parsed
fields in **bold**, which leaks into metadata and double-formats on render).
"""

import json
import re
from typing import Dict, Any, List, Tuple
from src.utils.prompt_schema import validate_concept_dict

# Canonical tone options — shared between the manual multiselect and the
# concept parser's whitelist. Keep in sync with the Story tab.
VALID_TONES = [
    "More battles and skirmishes",
    "Psychological horror",
    "Action-heavy combat",
    "Transformation focus",
    "Gravedancer origin elements",
    "Droid engagement focus",
    "Jedi POV chapters",
    "Traps and ambushes",
    "Honor and ritual",
    "Mystical / Force elements",
    "Political intrigue",
    "Survival horror",
    "Narrow escapes",
    "Ongoing pursuit (no kill)",
]

# Target novella length — kept here so concept + story prompts agree.
TARGET_WORDS = 7500


_REASONING_STARTER = re.compile(
    r"^(?:Thinking|Analysis|Planning|Let me|I['’]?ll?|We['’]?ll?|First,?|Okay,?|Alright,?|Here['’]?s?)",
    re.IGNORECASE,
)


def _strip_context_reasoning(text: str) -> str:
    """Strip plain-text reasoning that Qwen models emit before the actual prose.

    Qwen 3.5 sometimes outputs chain-of-thought as **plain text** (not inside
    ``<think>`` tags) using patterns like::

        Thinking in Qwen: 1. **Analyze the Request:**
        * **Topic:** Episode concept...

    The function discards any prefix that reads like reasoning and returns
    only the prose paragraphs.  If **no** prose paragraph is found the entire
    text is returned unchanged so callers can still attempt to work with it.
    """
    paragraphs = re.split(r"\n\s*\n", text)
    prose_start = 0
    for i, para in enumerate(paragraphs):
        stripped = para.strip()
        if not stripped:
            continue
        first_line = stripped.split("\n")[0].strip()
        # Skip numbered bold headers: 1. **Analyze**
        if re.match(r"^\d+\.\s*\*\*", first_line):
            continue
        # Skip reasoning starters
        if _REASONING_STARTER.match(first_line):
            continue
        # Skip markdown list items that start with **bold**
        if re.match(r"^[\*\-]\s+\*\*", first_line):
            continue
        # This looks like prose — everything from here stays
        prose_start = i
        break
    return "\n\n".join(paragraphs[prose_start:]).strip()


def get_used_jedi_names(episodes: List[Dict[str, Any]]) -> List[str]:
    """Collect Jedi names already used across the library (for dedup)."""
    names = []
    for ep in episodes:
        jedi_name = str(ep.get("target_jedi_name") or ep.get("jedi_name") or "").strip()
        if jedi_name and jedi_name.lower() != "unknown":
            names.append(jedi_name)
    return names


def _strip_markdown(value: str) -> str:
    """Remove markdown bold/italic markers and stray list bullets."""
    if not value:
        return ""
    # Drop **bold**, __bold__, *italic*, _italic_ wrappers and leading bullets.
    value = re.sub(r"\*{1,2}|_{1,2}", "", value)
    value = re.sub(r"^\s*[-*]\s+", "", value)
    return value.strip()


def build_concept_context_prompt(used_names: List[str]) -> str:
    """Build a free-form concept generation prompt (creative context pass).

    The LLM should write a vivid, natural-language episode concept with no
    structural constraints — just good creative writing.  A separate extraction
    pass will parse the structured fields from whatever the model produces.
    """
    used = ""
    if used_names:
        used = f"\n- Avoid Jedi already used in previous episodes: {', '.join(used_names)}"
    return f"""Create one episode concept for "Gravedancer to General: Anatomy of a Catastrophe".

Story constraints:
- Pre-Clone Wars.
- Qymaen jai Sheelal hunts one original Jedi.
- Target length: about {TARGET_WORDS:,} words per day.
- Structure: 3-8 days, usually 5.

Cover these elements in your description:
- A unique Jedi (name, species, rank, lightsaber, personality, fighting style) with their own philosophy and reason for being in Qymaen's way
- A memorable setting with tactical and atmospheric weight
- The tone — what kind of episode this will be (combat, horror, pursuit, intrigue, etc.){used}

Write 2-4 paragraphs. Be vivid, specific, and cinematic. No formatting, no lists — just prose."""


def build_concept_extraction_prompt(context_text: str) -> str:
    """Build a self-contained extraction prompt that converts concept prose to
    structured JSON.  The prompt is fully self-contained (lists every allowed
    tone so the LLM doesn't have to guess) and explicitly prohibits extra text."""
    tones_block = "\n".join(f"- {t}" for t in VALID_TONES)
    return f"""You are a precise data-extraction system.  Below is a creative episode
concept.  Extract exactly the fields listed and return ONLY valid JSON — no
explanations, no chain-of-thought, no markdown formatting.

CONCEPT TEXT TO EXTRACT FROM:
{context_text.strip() or "(empty)"}

REQUIRED JSON:
{{
  "title": "A short, punchy episode title",
  "days": <integer 3-8 — how many days the episode spans>,
  "setting": "The planet and specific location",
  "jedi_name": "Full name of the Jedi target",
  "jedi_species": "Species of the Jedi (e.g. Togruta, Miraluka, Kaleesh)",
  "jedi_rank": "Rank (e.g. Jedi Knight, Jedi Master)",
  "jedi_saber": "Lightsaber colour or description",
  "jedi_personality": "Personality, philosophy, or fighting style",
  "jedi_target": "Why this Jedi is targeted — what makes them a target",
  "tone": ["pick 2-4 tone strings from the allowed list below"]
}}

Allowed tone values (pick 2-4, must match exactly):
{tones_block}

RULES:
- If a field is not explicitly stated in the concept, infer the most likely value.
- days must be an integer between 3 and 8.
- tone entries must match one of the allowed values above (case-sensitive).
- Use double quotes.
- Return ONLY the JSON object — no introductions, no conclusions, no markdown formatting."""


def build_missing_fields_repair_prompt(
    context_text: str,
    extracted_so_far: Dict[str, Any],
    missing_fields: List[str],
    used_names: List[str] | None = None,
) -> str:
    """Build a focused prompt that fills in only the missing concept fields.

    Unlike the full extraction prompt, this one is short and targeted — it
    tells the LLM exactly which fields are missing and asks for a minimal
    JSON containing just those fields.
    """
    partial = json.dumps(extracted_so_far, indent=2)
    missing_list = "\n".join(f"- {f}" for f in missing_fields)
    tones_block = "\n".join(f"- {t}" for t in VALID_TONES)
    # Build the excluded-names line only if we have names to exclude.
    excluded = ""
    all_names = list(used_names or [])
    if extracted_so_far.get("jedi_name"):
        all_names.append(str(extracted_so_far["jedi_name"]))
    if all_names:
        excluded = f"\n- jedi_name must NOT be one of: {', '.join(all_names)}"
    return f"""Fill in the missing fields for an episode concept.

Context (for reference):
{context_text.strip() or "(empty)"}

Already extracted:
{partial}

Missing fields:
{missing_list}

Generate values for ONLY the missing fields listed above.  Return a valid
JSON object with those fields.  Use the context as inspiration.

Constraints:
- days: integer 3-8.
- tone entries must match one of the allowed values (case-sensitive):
{tones_block}{excluded}
- If you can't determine a value from the context, infer a reasonable default.
- Return ONLY the JSON object — no explanations, no markdown."""


_RANK_WS = (
    "Master", "Knight", "Padawan", "General", "Consular",
    "Guardian", "Sentinel", "Battlemaster", "Commander",
)
"""Known Jedi ranks used in prose-extraction fallback."""


def _extract_from_prose(concept: Dict[str, Any], prose: str, _raw_response: str = "") -> None:
    """Second-chance extraction of missing concept fields from creative prose.

    *prose* is the free-form context response (2-4 paragraphs of vivid
    description).  *concept* is updated **in place** for any fields that
    are currently empty or falsy.  Markdown bold/italic is stripped.
    """
    # --- tone: match VALID_TONES case-insensitively in prose (first pass) ---
    if not concept.get("tone"):
        found: List[str] = []
        prose_lower = prose.lower()
        for t in VALID_TONES:
            if t.lower() in prose_lower:
                found.append(t)
        if found:
            concept["tone"] = found

    # --- jedi_species:  e.g. "a Togruta Jedi" / "the Kaleesh Jedi" ---
    if not concept.get("jedi_species"):
        m = re.search(r"(?i)(?:a|an|the|—|,)\s+(\w+)\s+Jedi\b", prose)
        if m:
            concept["jedi_species"] = _strip_markdown(m.group(1).strip())

    # --- jedi_rank:  e.g. "Jedi Master Valdris" ---
    if not concept.get("jedi_rank"):
        m = re.search(r"(?i)Jedi\s+(" + "|".join(_RANK_WS) + r")\b", prose)
        if m:
            concept["jedi_rank"] = _strip_markdown(m.group(1).strip().title())
            if not concept["jedi_rank"].startswith("Jedi "):
                concept["jedi_rank"] = "Jedi " + concept["jedi_rank"]

    # --- jedi_saber:  e.g. "viridian blade" / "green lightsaber" ---
    if not concept.get("jedi_saber"):
        m = re.search(r"(?i)(\w+)\s+(?:lightsaber|blade|saber)\b", prose)
        if m:
            concept["jedi_saber"] = _strip_markdown(m.group(1).strip())

    # --- jedi_personality:  attributes & style near the jedi_name ---
    if not concept.get("jedi_personality") and concept.get("jedi_name"):
        jn = re.escape(concept["jedi_name"])
        # Sentence containing the jedi_name
        m = re.search(
            rf"(?i)(?:{jn}[^.]*\.|[^.]*?{jn}[^.]*\.)",
            prose, re.DOTALL,
        )
        if m:
            sent = m.group(0)
            # Strip out known patterns to leave descriptive content
            for pat in [
                rf"(?i){jn}[,\s]*(?:a|an|the|—)?\s*",
                rf"(?i)(?:a|an|the)\s+\w+\s+Jedi\s+\w+\s+who\s+",
                rf"(?i)(?:a|an|the)\s+\w+\s+Jedi\s+",
                "Jedi ",
                r"\b(?:wields|wielding|carries|carrying|uses|using)\s+\w+\s+(?:lightsaber|blade|saber)",
                rf"(?i){jn}",
            ]:
                sent = re.sub(pat, "", sent).strip(" ,;—")
            sent = re.sub(r"\s+", " ", sent).strip(" ,;—.")
            if sent:
                concept["jedi_personality"] = _strip_markdown(sent)

    # --- jedi_target:  rationale for being hunted ---
    if not concept.get("jedi_target") and concept.get("jedi_name"):
        jn = re.escape(concept["jedi_name"])
        # Look for phrases around "target", "hunt", "pursue" near the jedi_name
        m = re.search(
            rf"(?:target[s]?|hunt[s]?|pursue[s]?|track[s]?|seek[s]?|stalk[s]?|ambush[es]?|guard[s]?|protect[s]?|command[s]?|leads?|controls?|holds?)\b[^.]*?{jn}[^.]*\.|"
            rf"{jn}[^.]*?(?:target[s]?|hunt[s]?|pursue[s]?|track[s]?|seek[s]?|stalk[s]?|ambush[es]?|guard[s]?|protect[s]?|command[s]?|leads?|controls?|holds?)[^.]*\.",
            prose, re.IGNORECASE | re.DOTALL,
        )
        if m:
            concept["jedi_target"] = _strip_markdown(m.group(0).strip())
        else:
            # Last resort: first sentence that contains the jedi_name
            m = re.search(
                rf"(?i)(?:{jn}[^.]*\.|[^.]*?{jn}[^.]*\.)",
                prose, re.DOTALL,
            )
            if m:
                concept["jedi_target"] = _strip_markdown(m.group(0).strip())

    # --- setting from prose (if still missing) ---
    if not concept.get("setting"):
        # Try to match proper-plane-name patterns like
        # "on [Name]" / "the world of [Name]" / "at [Name]"
        m = re.search(
            r"(?i)(?:on|at|above|to|beneath|beyond|the\s+(?:world|planet|moon|system|desert|city|jungle|ocean|ruin)\s+of)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)",
            prose,
        )
        if m:
            concept["setting"] = _strip_markdown(m.group(1).strip())

    # --- title from prose (if still missing) ---
    if not concept.get("title"):
        # Look for quoted text that might be an episode title
        m = re.search(r"""[""]([A-Z][a-zA-Z ]{6,60})[""]""", prose)
        if m:
            concept["title"] = _strip_markdown(m.group(1).strip())


def _try_close_truncated_json(text: str) -> Dict[str, Any] | None:
    """Attempt to parse truncated JSON by closing open brackets/braces.

    When the LLM runs out of tokens mid-JSON, the output is cut off with
    open ``[`` and ``{`` delimiters.  This function tries progressively
    more aggressive truncation to find a valid JSON prefix.
    """
    text = text.strip()

    # Strategy 1: Cut back to last complete value (after a closing quote
    # followed by comma, or after a complete bracket/brace), then close.
    for cut_pattern in [r'",', r'"', r'\]', r'\}', r'\d', r'true|false|null']:
        m = None
        for m in re.finditer(cut_pattern, text):
            pass  # find last match
        if m:
            candidate = text[: m.end()]
            # Remove trailing comma if present
            candidate = candidate.rstrip().rstrip(",")
            open_b = candidate.count("{") - candidate.count("}")
            open_sq = candidate.count("[") - candidate.count("]")
            if open_b <= 0 and open_sq <= 0:
                continue
            suffix = "]" * max(open_sq, 0) + "}" * max(open_b, 0)
            try:
                parsed = json.loads(candidate + suffix)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

    return None


def _extract_tone_from_truncated(response: str) -> list[str]:
    """Extract tone values from a truncated ``"tone": [...]`` array.

    When the JSON is cut off mid-array (e.g. ``"tone": ["Psychological
    horror", "Traps``), this regex finds all complete quoted strings
    after ``"tone"`` and matches them against ``VALID_TONES``.
    """
    tone_section = re.search(
        r'"tone"\s*:\s*\[(.*?)(?:\]|\Z)',
        response, re.DOTALL,
    )
    if not tone_section:
        return []
    raw = tone_section.group(1)
    # Extract all complete quoted strings
    quoted = re.findall(r'"([^"]+)"', raw)
    if not quoted:
        return []
    tones = [_strip_markdown(q.strip()) for q in quoted]
    return [t for t in tones if t in VALID_TONES] or tones


def try_parse_full_episode_concept(response: str, fallback_text: str = "") -> Tuple[Dict[str, Any], List[str]]:
    """Parse LLM response into an episode concept dict.

    Same as :func:`parse_full_episode_concept` but **does not raise** on
    validation errors — returns ``(concept, errors)`` instead so callers can
    inspect which fields are missing and attempt a repair pass.
    """
    concept: Dict[str, Any] = {
        "title": "",
        "days": 5,
        "setting": "",
        "jedi_name": "",
        "jedi_species": "",
        "jedi_rank": "",
        "jedi_saber": "",
        "jedi_personality": "",
        "jedi_target": "",
        "tone": [],
    }

    json_candidate = response.strip()
    # Find ```json … ``` fences anywhere in the response, not just at position 0.
    fence_match = re.search(
        r"```(?:json)?\s*\n?(.*?)\n?```", json_candidate, re.DOTALL | re.IGNORECASE
    )
    if fence_match:
        json_candidate = fence_match.group(1).strip()
    else:
        # No closing fence — try to grab everything after ```json up to end
        open_fence = re.search(r"```(?:json)?\s*\n?(.*)", json_candidate, re.DOTALL | re.IGNORECASE)
        if open_fence:
            json_candidate = open_fence.group(1).strip()

    parsed = None
    try:
        parsed = json.loads(json_candidate)
    except json.JSONDecodeError:
        # JSON is likely truncated (model ran out of tokens mid-output).
        # Try to auto-close by appending missing brackets/braces.
        parsed = _try_close_truncated_json(json_candidate)

    if isinstance(parsed, dict):
        concept["title"] = _strip_markdown(str(parsed.get("title", "")).strip())
        try:
            concept["days"] = max(3, min(8, int(parsed.get("days", 5))))
        except (TypeError, ValueError):
            concept["days"] = 5
        concept["setting"] = _strip_markdown(str(parsed.get("setting", "")).strip())
        concept["jedi_name"] = _strip_markdown(str(parsed.get("jedi_name", "")).strip())
        concept["jedi_species"] = _strip_markdown(str(parsed.get("jedi_species", "")).strip())
        concept["jedi_rank"] = _strip_markdown(str(parsed.get("jedi_rank", "")).strip())
        concept["jedi_saber"] = _strip_markdown(str(parsed.get("jedi_saber", "")).strip())
        concept["jedi_personality"] = _strip_markdown(str(parsed.get("jedi_personality", "")).strip())
        # Accept both jedi_target and jedi_why_targeted as JSON keys.
        concept["jedi_target"] = _strip_markdown(
            str(parsed.get("jedi_target") or parsed.get("jedi_why_targeted", "")).strip()
        )
        raw_tone = parsed.get("tone", [])
        if isinstance(raw_tone, list):
            tones = [_strip_markdown(str(t).strip()) for t in raw_tone]
            concept["tone"] = [t for t in tones if t in VALID_TONES] or tones
        elif isinstance(raw_tone, str):
            tones = [_strip_markdown(t.strip()) for t in raw_tone.split(",")]
            concept["tone"] = [t for t in tones if t in VALID_TONES] or tones

        # Short-circuit: if JSON parse gave us all required fields, skip the
        # expensive regex/prose fallback cascade below.
        errors = validate_concept_dict(concept)
        if not errors:
            return concept, errors

    # If tone is still empty, try to extract quoted strings from a
    # truncated "tone": [...] array (model ran out of tokens mid-array).
    if not concept["tone"]:
        concept["tone"] = _extract_tone_from_truncated(response)

    field_patterns = {
        "title": r"(?:\*\*)?TITLE(?:\*\*)?:\s*(.*?)(?=\n(?:\*\*)?[A-Z_]+(?:\*\*)?:|\Z)",
        "days": r"(?:\*\*)?DAYS(?:\*\*)?:\s*(\d+)",
        "setting": r"(?:\*\*)?SETTING(?:\*\*)?:\s*(.*?)(?=\n(?:\*\*)?[A-Z_]+(?:\*\*)?:|\Z)",
        "jedi_name": r"(?:\*\*)?JEDI_NAME(?:\*\*)?:\s*(.*?)(?=\n(?:\*\*)?[A-Z_]+(?:\*\*)?:|\Z)",
        "jedi_species": r"(?:\*\*)?JEDI_SPECIES(?:\*\*)?:\s*(.*?)(?=\n(?:\*\*)?[A-Z_]+(?:\*\*)?:|\Z)",
        "jedi_rank": r"(?:\*\*)?JEDI_RANK(?:\*\*)?:\s*(.*?)(?=\n(?:\*\*)?[A-Z_]+(?:\*\*)?:|\Z)",
        "jedi_saber": r"(?:\*\*)?JEDI_SABER(?:\*\*)?:\s*(.*?)(?=\n(?:\*\*)?[A-Z_]+(?:\*\*)?:|\Z)",
        "jedi_personality": r"(?:\*\*)?JEDI_PERSONALITY(?:\*\*)?:\s*(.*?)(?=\n(?:\*\*)?[A-Z_]+(?:\*\*)?:|\Z)",
        "jedi_target": r"(?:\*\*)?JEDI_TARGET(?:\*\*)?:\s*(.*?)(?=\n(?:\*\*)?[A-Z_]+(?:\*\*)?:|\Z)",
        "tone": r"(?:\*\*)?TONE(?:\*\*)?:\s*(.*?)(?=\n(?:\*\*)?[A-Z_]+(?:\*\*)?:|\Z)",
    }

    for key, pattern in field_patterns.items():
        match = re.search(pattern, response, re.DOTALL)
        if not match:
            continue
        value = match.group(1).strip()
        if key == "days":
            try:
                concept["days"] = max(3, min(8, int(value)))
            except ValueError:
                concept["days"] = 5
        elif key == "tone":
            tones = [t.strip() for t in value.split(",")]
            tones = [_strip_markdown(t) for t in tones]
            concept["tone"] = [t for t in tones if t in VALID_TONES] or tones
        else:
            concept[key] = _strip_markdown(value)

    # Fallbacks for slightly different wording.
    if not concept["title"]:
        match = re.search(r"(?:\*\*)?(?:EPISODE\s+)?TITLE(?:\*\*)?:\s*(.*?)(?=\n|$)", response, re.IGNORECASE)
        if match:
            concept["title"] = _strip_markdown(match.group(1).strip())
    if concept["days"] == 5:
        match = re.search(r"(?:\*\*)?(?:NUMBER\s+OF\s+)?DAYS(?:\*\*)?:\s*(\d+)", response, re.IGNORECASE)
        if match:
            try:
                concept["days"] = max(3, min(8, int(match.group(1).strip())))
            except ValueError:
                pass
    if not concept["jedi_name"]:
        match = re.search(r"(?:\*\*)?JEDI\s+NAME(?:\*\*)?:\s*(.*?)(?=\n|$)", response, re.IGNORECASE)
        if match:
            concept["jedi_name"] = _strip_markdown(match.group(1).strip())
    if not concept["setting"]:
        match = re.search(r"(?:\*\*)?(?:SETTING|PLANET|LOCATION)(?:\*\*)?:\s*(.*?)(?=\n|$)", response, re.IGNORECASE)
        if match:
            concept["setting"] = _strip_markdown(match.group(1).strip())
    # Accept jedi_why_targeted / JEDI_WHY_TARGETED as a variant.
    if not concept["jedi_target"]:
        match = re.search(r"(?:\*\*)?(?:JEDI_WHY_TARGETED|WHY_TARGETED)(?:\*\*)?:\s*(.*?)(?=\n(?:\*\*)?[A-Z_]+(?:\*\*)?:|\Z)", response, re.IGNORECASE)
        if match:
            concept["jedi_target"] = _strip_markdown(match.group(1).strip())

    # JSON-key–style regex fallback for when the LLM returns bare JSON-like text
    # that was not captured by the code-block extraction above.
    json_key_patterns = {
        "title": r'"title"\s*:\s*"(.*?)"',
        "days": r'"days"\s*:\s*(\d+)',
        "setting": r'"setting"\s*:\s*"(.*?)"',
        "jedi_name": r'"jedi_name"\s*:\s*"(.*?)"',
        "jedi_species": r'"jedi_species"\s*:\s*"(.*?)"',
        "jedi_rank": r'"jedi_rank"\s*:\s*"(.*?)"',
        "jedi_saber": r'"jedi_saber"\s*:\s*"(.*?)"',
        "jedi_personality": r'"jedi_personality"\s*:\s*"(.*?)"',
        "jedi_target": r'"(?:jedi_target|jedi_why_targeted)"\s*:\s*"(.*?)"',
        "tone": r'"tone"\s*:\s*"([^"]+)"|"tone"\s*:\s*\[(.*?)\]',
    }
    for key, pattern in json_key_patterns.items():
        if concept.get(key) if key != "tone" else None:
            continue
        match = re.search(pattern, response, re.DOTALL)
        if not match:
            continue
        if key == "tone":
            value = match.group(1) or match.group(2) or ""
            tones = [t.strip().strip('"') for t in value.split(",")]
            tones = [_strip_markdown(t) for t in tones]
            concept["tone"] = [t for t in tones if t in VALID_TONES] or tones
            continue
        value = match.group(1).strip()
        if key == "days":
            try:
                concept["days"] = max(3, min(8, int(value)))
            except ValueError:
                pass
        else:
            concept[key] = _strip_markdown(value)

    # ------------------------------------------------------------------
    # Fallback: prose extraction from the creative context
    # When the extraction LLM ran out of tokens (or <think> blocks ate
    # the budget), the first N fields may be set but the rest missing.
    # The creative context (fallback_text) still contains all the info.
    # ------------------------------------------------------------------
    if fallback_text and any(
        not concept.get(k) for k in ("jedi_species", "jedi_rank", "jedi_saber",
                                     "jedi_personality", "jedi_target", "tone")
    ):
        _extract_from_prose(concept, fallback_text, response)

    errors = validate_concept_dict(concept)
    return concept, errors


def parse_full_episode_concept(response: str, fallback_text: str = "") -> Dict[str, Any]:
    """Parse LLM response into an episode concept dict.

    Strips markdown bold/italic from every value so metadata never carries
    stray ``**`` markers that double-format on render.

    When *fallback_text* is provided (the rich creative prose from the
    context pass), missing fields are extracted from it via prose-specific
    regex patterns as a second-chance mechanism.

    Raises ``ValueError`` on validation failure.  Use
    :func:`try_parse_full_episode_concept` if you need to inspect missing
    fields without an exception.
    """
    concept, errors = try_parse_full_episode_concept(response, fallback_text)
    if errors:
        raise ValueError(f"Invalid concept output: {', '.join(errors)}")
    return concept
