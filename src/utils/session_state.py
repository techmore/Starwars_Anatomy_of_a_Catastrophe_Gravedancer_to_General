"""Session-state helpers for the prototype UI shell."""

from copy import deepcopy
from typing import Iterable

from src.prompts.system_prompts import (
    STORY_GENERATION_SYSTEM_PROMPT,
    VISUAL_PROMPT_SYSTEM_PROMPT,
)
from src.utils.settings import SETTINGS


SESSION_DEFAULTS = {
    "current_episode_id": None,
    "current_story": "",
    "current_metadata": {},
    "mlx_model": SETTINGS.model,
    "drawthings_url": "http://localhost:7860",
    "model": "",
    "temperature": 0.8,
    "storage_path": str(SETTINGS.storage_path),
    "story_sys_prompt": STORY_GENERATION_SYSTEM_PROMPT,
    "visual_sys_prompt": VISUAL_PROMPT_SYSTEM_PROMPT,
    "show_manual_form_state": False,
    "auto_generate": False,
    "story_title": "",
    "story_days": 5,
    "generation_profile": "standard",
    "story_setting": "",
    "story_tone": [],
    "story_outline": "",
    "story_outline_days": [],
    "story_section_previews": {},
    "story_section_drafts": {},
    "story_day_drafts": {},
    "story_draft_only_mode": False,
    "story_outline_approved": False,
    "current_critique_report": None,
}


GENERATION_PROFILES = {
    "smoke": {
        "label": "Smoke test",
        "days": 1,
        "description": "Fast validation run for prompts, connectivity, and saving.",
        "estimate": "Usually a few minutes",
    },
    "standard": {
        "label": "Standard",
        "days": 5,
        "description": "Balanced episode draft for normal iteration.",
        "estimate": "Model-dependent; typically several minutes",
    },
    "long_form": {
        "label": "Long-form",
        "days": 8,
        "description": "Full-length production profile targeting roughly 45,000 output tokens per day.",
        "estimate": "May take an hour or more on a local 9B model",
    },
}


STORY_INPUT_KEYS = (
    "story_title",
    "story_days",
    "story_setting",
    "jedi_name",
    "jedi_species",
    "jedi_rank",
    "jedi_saber",
    "jedi_personality",
    "jedi_target",
    "story_additional",
)


def init_session_state(st):
    """Populate required defaults if they are not already present."""
    for key, value in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            # Defaults include lists/dicts. Copy them per session so one
            # browser session cannot mutate another session's initial state.
            st.session_state[key] = deepcopy(value)


def clear_story_inputs(st, keys: Iterable[str] = STORY_INPUT_KEYS) -> None:
    """Reset the story form fields to their blank/default values."""
    for key in keys:
        if key in st.session_state:
            st.session_state[key] = "" if key != "story_days" else 5
    st.session_state["story_tone"] = []


def clear_current_episode(st) -> None:
    """Clear the current episode/story state."""
    st.session_state["current_story"] = ""
    st.session_state["current_episode_id"] = None
    st.session_state["current_metadata"] = {}


def reset_story_flow(st) -> None:
    """Reset both the current episode and the story form inputs."""
    clear_current_episode(st)
    clear_story_inputs(st)
    st.session_state["story_outline"] = ""
    st.session_state["story_outline_days"] = []
    st.session_state["story_section_previews"] = {}
    st.session_state["story_section_drafts"] = {}
    st.session_state["story_day_drafts"] = {}
    st.session_state["story_draft_only_mode"] = False
    st.session_state["story_outline_approved"] = False
    st.session_state["current_critique_report"] = None


def hydrate_story_inputs(st, concept: dict) -> None:
    """Copy a parsed concept into the story form/session state."""
    st.session_state["story_title"] = concept.get("title", "")
    st.session_state["story_days"] = concept.get("days", 5)
    st.session_state["story_setting"] = concept.get("setting", "")
    st.session_state["jedi_name"] = concept.get("jedi_name", "")
    st.session_state["jedi_species"] = concept.get("jedi_species", "")
    st.session_state["jedi_rank"] = concept.get("jedi_rank", "")
    st.session_state["jedi_saber"] = concept.get("jedi_saber", "")
    st.session_state["jedi_personality"] = concept.get("jedi_personality", "")
    st.session_state["jedi_target"] = concept.get("jedi_target", "")
    st.session_state["story_tone"] = list(concept.get("tone", []) or [])
    st.session_state["story_additional"] = concept.get("additional_instructions", "")


def load_episode_into_session(st, episode: dict) -> bool:
    """Make a saved episode the active story and hydrate its editable fields."""
    if not isinstance(episode, dict):
        return False
    metadata = episode.get("metadata")
    if not isinstance(metadata, dict):
        return False
    episode_id = metadata.get("id") or episode.get("id")
    if not episode_id:
        return False

    target_jedi = metadata.get("target_jedi_name") or metadata.get("jedi_name", "")
    hydrate_story_inputs(
        st,
        {
            "title": metadata.get("title", ""),
            "days": metadata.get("num_days", 5),
            "setting": metadata.get("setting", ""),
            "jedi_name": target_jedi,
            "jedi_species": metadata.get("jedi_species", ""),
            "jedi_rank": metadata.get("jedi_rank", ""),
            "jedi_saber": metadata.get("jedi_lightsaber_color", ""),
            "jedi_personality": metadata.get("jedi_personality", ""),
            "jedi_target": metadata.get("jedi_why_targeted", ""),
            "tone": metadata.get("tone_focus", []),
            "additional_instructions": metadata.get("additional_instructions", ""),
        },
    )
    st.session_state["current_episode_id"] = episode_id
    st.session_state["current_story"] = episode.get("story", "") or ""
    st.session_state["current_metadata"] = dict(metadata)
    st.session_state["current_critique_report"] = None
    return True


def build_story_metadata(st, model: str, temperature: float) -> dict:
    """Build the canonical metadata payload for an episode from session state."""
    return {
        "title": st.session_state.get("story_title", ""),
        "num_days": st.session_state.get("story_days", 5),
        "jedi_name": st.session_state.get("jedi_name", ""),
        "target_jedi_name": st.session_state.get("jedi_name", ""),
        "jedi_species": st.session_state.get("jedi_species", ""),
        "jedi_rank": st.session_state.get("jedi_rank", ""),
        "jedi_lightsaber_color": st.session_state.get("jedi_saber", ""),
        "jedi_personality": st.session_state.get("jedi_personality", ""),
        "jedi_why_targeted": st.session_state.get("jedi_target", ""),
        "setting": st.session_state.get("story_setting", ""),
        "tone_focus": st.session_state.get("story_tone", []),
        "additional_instructions": st.session_state.get("story_additional", ""),
        "model": model,
        "temperature": temperature,
        "generation_profile": st.session_state.get("generation_profile", "standard"),
    }


def build_episode_payload(st, model: str, temperature: float) -> dict:
    """Build the canonical episode payload from session state."""
    return {
        "metadata": build_story_metadata(st, model, temperature),
        "jedi_details": build_jedi_details(st),
        "story_context": build_story_generation_context(st),
    }


def build_prompt_set(day_num: int, aspect_ratio: str, new_prompts: dict) -> dict:
    """Shape generated visual prompts into the stored prompt-set payload."""
    return {
        "day": day_num,
        "prompt_type": "Flux.2 Klein 4b - DrawThings",
        "aspect_ratio": aspect_ratio,
        "wide": new_prompts.get("wide", ""),
        "medium": new_prompts.get("medium", ""),
        "closeup": new_prompts.get("closeup", ""),
        "dramatic": new_prompts.get("dramatic", ""),
        "alternate": new_prompts.get("alternate", ""),
        "negative_prompt": new_prompts.get("negative_prompt", ""),
        "raw_response": new_prompts.get("raw_response", ""),
    }


def merge_prompt_sets(existing_prompts: list, day_num: int, aspect_ratio: str, new_prompts: dict, replace: bool = False) -> list:
    """Merge a prompt set into the existing stored prompt list."""
    if replace:
        prompts = [p for p in existing_prompts if p.get("day") != day_num]
    else:
        prompts = list(existing_prompts)
    prompts.append(build_prompt_set(day_num, aspect_ratio, new_prompts))
    return prompts


def save_day_prompt_sets(storage, episode_id, existing_prompts: list, day_num: int, aspect_ratio: str, new_prompts: dict, replace: bool = False) -> list:
    """Merge generated prompts and persist the episode prompt payload."""
    prompts = merge_prompt_sets(existing_prompts, day_num, aspect_ratio, new_prompts, replace=replace)
    storage.update_episode(
        episode_id=episode_id,
        prompts={"scenes": prompts, "aspect_ratio": aspect_ratio},
    )
    return prompts


def get_episode_prompt_sets(episode: dict) -> list:
    """Return the stored scene prompt sets for an episode."""
    prompts = episode.get("prompts") if episode else None
    scenes = prompts.get("scenes", []) if isinstance(prompts, dict) else []
    return [scene for scene in scenes if isinstance(scene, dict)] if isinstance(scenes, list) else []


def get_episode_day_prompt_sets(episode: dict, day_num: int) -> list:
    """Return the prompt sets for a specific day from an episode."""
    return [p for p in get_episode_prompt_sets(episode) if isinstance(p, dict) and p.get("day") == day_num]


def normalize_saved_prompt_sets_for_selection(prompt_sets: list) -> list:
    """Adapt stored prompt sets to the scene-selection shape used by the UI."""
    normalized = []
    for index, prompt_set in enumerate(prompt_sets or [], start=1):
        if not isinstance(prompt_set, dict):
            continue
        scene_text = (
            prompt_set.get("scene_text")
            or prompt_set.get("medium")
            or prompt_set.get("wide")
            or prompt_set.get("dramatic")
            or ""
        )
        normalized.append(
            {
                **prompt_set,
                "day": prompt_set.get("day", 1),
                "text": scene_text,
                "display_title": prompt_set.get("display_title") or f"Saved prompt set {index}",
                "visual_score": prompt_set.get("visual_score", 0),
            }
        )
    return normalized


def get_episode_target_jedi_name(episode: dict) -> str:
    """Return the canonical display name for the episode's target Jedi."""
    if not episode:
        return "Unknown"
    metadata = episode.get("metadata") if isinstance(episode.get("metadata"), dict) else episode
    return metadata.get("target_jedi_name") or metadata.get("jedi_name") or "Unknown"


def episode_selector_label(episode: dict) -> str:
    """Build a unique, readable label for episode picker controls."""
    metadata = episode.get("metadata") if isinstance(episode.get("metadata"), dict) else episode
    title = metadata.get("title", "Untitled")
    created_at = metadata.get("created_at", "")[:10] or "undated"
    episode_id = metadata.get("id") or episode.get("id") or "unknown"
    return f"{title} ({created_at}) · {episode_id[-8:]}"


def summarize_episode_prompt_archive(episode: dict) -> dict:
    """Summarize saved prompt coverage for one episode."""
    prompt_sets = get_episode_prompt_sets(episode)
    day_counts = {}
    for prompt_set in prompt_sets:
        if not isinstance(prompt_set, dict):
            continue
        day_num = prompt_set.get("day", "Unknown")
        day_counts[day_num] = day_counts.get(day_num, 0) + 1
    prompt_days = len({day for day in day_counts if isinstance(day, int) and day > 0})
    return {
        "prompt_sets": len(prompt_sets),
        "prompt_days": prompt_days,
        "day_counts": day_counts,
        "prompt_sets_list": prompt_sets,
    }


def render_episode_prompt_archive_summary(st, episode: dict, expanded: bool = False) -> dict:
    """Render the saved prompt coverage summary and return the computed summary."""
    summary = summarize_episode_prompt_archive(episode)
    if summary["prompt_sets"]:
        with st.expander("Prompt Set Breakdown", expanded=expanded):
            st.markdown(f"**Total saved prompt sets:** {summary['prompt_sets']}")
            for day_num in sorted(summary["day_counts"], key=lambda x: (x == "Unknown", x)):
                st.markdown(f"- Day {day_num}: {summary['day_counts'][day_num]} set(s)")
    return summary


def build_episode_full_json_export(episode: dict) -> dict:
    """Build the downloadable full JSON payload for an episode."""
    summary = summarize_episode_prompt_archive(episode)
    return {
        "metadata": episode.get("metadata", {}),
        "story": episode.get("story", ""),
        "prompts": episode.get("prompts"),
        "prompt_sets": summary["prompt_sets"],
        "prompt_days": summary["prompt_days"],
    }


def summarize_episode_collection(episodes: list) -> dict:
    """Summarize prompt/archive coverage across a list of episodes."""
    total_episodes = len(episodes)
    total_days = sum(ep.get("num_days", 0) for ep in episodes)
    unique_jedi = len({get_episode_target_jedi_name(ep) for ep in episodes})
    total_prompt_sets = sum(ep.get("prompt_sets", 0) for ep in episodes)
    episodes_with_prompts = sum(1 for ep in episodes if ep.get("prompt_sets", 0) > 0)
    total_prompt_days = sum(ep.get("prompt_days", 0) for ep in episodes)
    covered_episodes = sum(
        1 for ep in episodes
        if ep.get("prompt_days", 0) >= ep.get("num_days", 0) and ep.get("num_days", 0) > 0
    )
    return {
        "total_episodes": total_episodes,
        "total_days": total_days,
        "unique_jedi": unique_jedi,
        "total_prompt_sets": total_prompt_sets,
        "episodes_with_prompts": episodes_with_prompts,
        "total_prompt_days": total_prompt_days,
        "covered_episodes": covered_episodes,
    }


def get_episode_banner_prompt(episode: dict) -> str:
    """Return the stored banner prompt for an episode, or empty string."""
    prompts = episode.get("prompts") if episode else None
    return (prompts.get("banner") or {}).get("banner_prompt", "") if prompts else ""


def get_episode_chapter_prompts(episode: dict) -> list:
    """Return the stored chapter-level prompt sets for an episode."""
    prompts = episode.get("prompts") if episode else None
    return (prompts.get("chapters") or []) if prompts else []


def save_banner_prompt(storage, episode_id: str, banner_prompt: str, negative_prompt: str = "") -> dict:
    """Persist a banner prompt to the episode's prompt payload."""
    episode = storage.load_episode(episode_id)
    existing = dict(episode.get("prompts") or {})
    existing["banner"] = {
        "banner_prompt": banner_prompt,
        "negative_prompt": negative_prompt,
    }
    storage.update_episode(episode_id=episode_id, prompts=existing)
    return existing


def save_chapter_prompt(storage, episode_id: str, chapter_prompt: dict) -> list:
    """Append a chapter prompt set to the episode's prompt payload."""
    episode = storage.load_episode(episode_id)
    existing = dict(episode.get("prompts") or {})
    chapters = list(existing.get("chapters", []))
    existing_key = (chapter_prompt.get("day"), chapter_prompt.get("chapter"))
    chapters = [cp for cp in chapters if (cp.get("day"), cp.get("chapter")) != existing_key]
    chapters.append(chapter_prompt)
    existing["chapters"] = chapters
    storage.update_episode(episode_id=episode_id, prompts=existing)
    return chapters


def build_story_generation_context(st) -> dict:
    """Build the full story-generation context from session state."""
    return {
        "title": st.session_state.get("story_title", ""),
        "num_days": st.session_state.get("story_days", 5),
        "setting": st.session_state.get("story_setting", ""),
        "jedi_details": {
            "name": st.session_state.get("jedi_name", ""),
            "species": st.session_state.get("jedi_species", ""),
            "rank": st.session_state.get("jedi_rank", ""),
            "lightsaber_color": st.session_state.get("jedi_saber", ""),
            "personality": st.session_state.get("jedi_personality", ""),
            "why_targeted": st.session_state.get("jedi_target", ""),
        },
        "tone_focus": st.session_state.get("story_tone", []),
        "additional_instructions": st.session_state.get("story_additional", ""),
    }


def build_jedi_details(st) -> dict:
    """Build the Jedi target details from session state."""
    return {
        "name": st.session_state.get("jedi_name", ""),
        "species": st.session_state.get("jedi_species", ""),
        "rank": st.session_state.get("jedi_rank", ""),
        "lightsaber_color": st.session_state.get("jedi_saber", ""),
        "personality": st.session_state.get("jedi_personality", ""),
        "why_targeted": st.session_state.get("jedi_target", ""),
    }
