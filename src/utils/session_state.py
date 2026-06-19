"""Session-state helpers for the prototype UI shell."""

from typing import Iterable

from src.prompts.system_prompts import (
    STORY_GENERATION_SYSTEM_PROMPT,
    VISUAL_PROMPT_SYSTEM_PROMPT,
)


SESSION_DEFAULTS = {
    "current_episode_id": None,
    "current_story": "",
    "current_metadata": {},
    "mlx_model": "mlx-community/Qwen3.6-27B-4bit",
    "drawthings_url": "http://localhost:7860",
    "model": "",
    "temperature": 0.8,
    "storage_path": "episodes",
    "story_sys_prompt": STORY_GENERATION_SYSTEM_PROMPT,
    "visual_sys_prompt": VISUAL_PROMPT_SYSTEM_PROMPT,
    "show_manual_form_state": False,
    "auto_generate": False,
    "story_title": "",
    "story_days": 5,
    "story_setting": "",
    "story_tone": [],
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
            st.session_state[key] = value


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
    st.session_state["story_tone"] = concept.get("tone", [])


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
    return list(prompts.get("scenes", [])) if prompts else []


def get_episode_day_prompt_sets(episode: dict, day_num: int) -> list:
    """Return the prompt sets for a specific day from an episode."""
    return [p for p in get_episode_prompt_sets(episode) if p.get("day") == day_num]


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
