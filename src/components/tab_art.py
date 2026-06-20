"""Art tab: per-day image prompts + Draw Things keyframe generation.

Ports the working per-day prompt generation and layers on:
  - copy-to-clipboard buttons on every prompt (Phase 4)
  - "Generate Keyframe" -> Draw Things txt2img, saved into episodes/<id>/images/ (Phase 3)
"""

import streamlit as st

from src.components.ui import copy_button, aspect_to_dims
from src.prompts.system_prompts import NEGATIVE_PROMPT_DEFAULT
from src.utils.session_state import (
    get_episode_day_prompt_sets,
    get_episode_prompt_sets,
    render_episode_prompt_archive_summary,
    save_day_prompt_sets,
)
from src.utils.logging_utils import start_new_run_log


def render_art_stage(context):
    """Stage 2: Art prompts + keyframe generation."""
    mlx = context.mlx
    dt_client = context.dt_client
    model = context.mlx_model
    temperature = context.temperature
    storage = context.storage
    prompt_gen = context.prompt_gen
    story_gen = context.story_gen
    st.markdown("## 🎨 Art")
    st.markdown("Generate image prompts for each day, then render keyframes via Draw Things + Flux.2 Klein 4b.")
    st.markdown("---")

    if not st.session_state.get("current_episode_id"):
        st.info("Generate a story first (Story tab).")
        return

    ep_id = st.session_state["current_episode_id"]
    episode = storage.load_episode(ep_id)
    if not episode:
        st.error("Failed to load episode.")
        return

    story = episode["story"]
    metadata = episode["metadata"]
    st.markdown(f"**Episode:** {metadata.get('title', 'Untitled')}")

    # Generation settings
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        aspect_ratio = st.selectbox(
            "Aspect ratio",
            ["16:9", "21:9", "4:3", "3:2", "1:1", "9:16", "2:3"],
            index=0,
            key="art_aspect",
        )
    with col2:
        steps = st.slider("Steps", min_value=10, max_value=40, value=25, key="art_steps")
    with col3:
        cfg = st.slider("CFG", min_value=1.0, max_value=8.0, value=2.5, step=0.1, key="art_cfg")

    save_mode = st.radio(
        "When saving day prompts",
        ["Replace matching days", "Append as alternates"],
        index=0,
        key="art_save_mode",
        horizontal=True,
    )

    dt_ok = dt_client.check_connection()
    if not dt_ok:
        st.warning("Draw Things offline — you can still generate text prompts; keyframe rendering will be unavailable.")

    st.markdown("---")

    days = story_gen.parse_days(story)
    if not days:
        st.warning("No days found in story.")
        return

    st.markdown("## Generate Art for Each Day")

    existing_prompts = get_episode_prompt_sets(episode)
    prompt_summary = render_episode_prompt_archive_summary(st, episode)

    for idx, day in enumerate(days):
        day_num = day["number"]
        day_title = day["title"]
        day_content = day["content"]
        day_key = f"{ep_id}_{idx}_{day_num}"

        with st.expander(f"Day {day_num}: {day_title}", expanded=False):
            st.markdown(f"```\n{day_content[:300]}...\n```")

            day_prompts = get_episode_day_prompt_sets(episode, day_num)
            have_prompts = bool(day_prompts)

            if have_prompts:
                st.markdown(f"**✓ {len(day_prompts)} prompt set(s) already generated**")
                for prompt_set in day_prompts:
                    _render_prompt_set(prompt_set, dt_client, dt_ok, storage, ep_id, day_num, aspect_ratio, steps, cfg, day_key)
            else:
                if st.button(f"Generate Prompts — Day {day_num}", key=f"gen_art_{day_key}", type="primary"):
                    st.session_state["log_run_path"] = str(start_new_run_log("art-prompts"))
                    _generate_day_prompts(
                        prompt_gen, storage, ep_id, existing_prompts,
                        day_num, day_content, model, aspect_ratio, temperature,
                        replace=(save_mode == "Replace matching days"),
                    )

            # Regenerate button always available once we have a set.
            if have_prompts:
                if st.button(f"🔄 Regenerate Day {day_num}", key=f"regen_art_{day_key}"):
                    st.session_state["log_run_path"] = str(start_new_run_log("art-regen"))
                    _regenerate_day_prompts(
                        prompt_gen, storage, ep_id, existing_prompts,
                        day_num, day_content, model, aspect_ratio, temperature,
                        replace=(save_mode == "Replace matching days"),
                    )


def _render_prompt_set(prompt_set, dt_client, dt_ok, storage, ep_id, day_num, aspect_ratio, steps, cfg, day_key):
    """Render one prompt set with copy buttons + optional keyframe generation."""
    label = prompt_set.get("prompt_type", "Flux.2 Klein 4b - DrawThings")
    st.markdown(f"**{label}**")

    variants = [
        ("Wide / Establishing", prompt_set.get("wide", "")),
        ("Medium / Action", prompt_set.get("medium", "")),
        ("Close-up / Detail", prompt_set.get("closeup", "")),
        ("Dramatic / Low Angle", prompt_set.get("dramatic", "")),
        ("Alternate Style", prompt_set.get("alternate", "")),
    ]
    neg = prompt_set.get("negative_prompt", NEGATIVE_PROMPT_DEFAULT)

    # Show each variant with a copy button.
    for vlabel, vtext in variants:
        if not vtext:
            continue
        st.caption(f"**{vlabel}**")
        c_btn, _ = st.columns([1, 6])
        with c_btn:
            copy_button(vtext, label="Copy", key=f"art_{day_key}_{vlabel[:4].lower()}")
        st.code(vtext, language="text")

    # Negative prompt + copy.
    if neg:
        st.caption("**Negative**")
        copy_button(neg, label="Copy negative", key=f"art_{day_key}_neg")
        st.code(neg, language="text")

    # --- Keyframe rendering via Draw Things (Phase 3) ---
    st.markdown("---")
    st.markdown("**Render keyframe**")
    kf_prompt = st.selectbox(
        "Use prompt",
        [v[0] for v in variants if v[1]],
        key=f"kf_sel_{day_key}",
        label_visibility="collapsed",
    )
    chosen = next((v[1] for v in variants if v[0] == kf_prompt), "")

    seed = st.number_input("Seed (-1 = random)", value=-1, step=1, key=f"kf_seed_{day_key}")

    can_render = dt_ok and bool(chosen)
    if st.button(
        f"🖼 Generate Keyframe — Day {day_num}",
        key=f"kf_gen_{day_key}",
        disabled=not can_render,
        type="primary",
        help=None if can_render else "Requires Draw Things connected + a prompt variant",
    ):
        st.session_state["log_run_path"] = str(start_new_run_log("keyframe"))
        _render_keyframe(dt_client, storage, ep_id, day_num, chosen, neg, aspect_ratio, steps, cfg, int(seed))


def _render_keyframe(dt_client, storage, ep_id, day_num, prompt, negative, aspect_ratio, steps, cfg, seed):
    """Call Draw Things txt2img and store the result."""
    w, h = aspect_to_dims(aspect_ratio)
    with st.spinner(f"Rendering keyframe for Day {day_num} via Flux.2 Klein 4b..."):
        try:
            png = dt_client.generate_image(
                prompt=prompt,
                negative_prompt=negative,
                width=w,
                height=h,
                steps=steps,
                cfg=cfg,
                seed=seed,
            )
            rel = storage.save_image(ep_id, day=day_num, shot="keyframe", image_bytes=png)
            st.success(f"Keyframe saved to `{rel}`")
            st.image(png, caption=f"Day {day_num} keyframe ({w}×{h})", use_container_width=True)
        except Exception as e:
            st.error(f"Draw Things render failed: {e}")
            with st.expander("Troubleshooting"):
                st.markdown(
                    "- Confirm Draw Things is running with the **API Server** enabled.\n"
                    "- Confirm **Flux.2 Klein 4b** is the active model.\n"
                    "- Try lowering the resolution or step count."
                )


def _generate_day_prompts(prompt_gen, storage, ep_id, existing_prompts, day_num, day_content, model, aspect_ratio, temperature, replace: bool = False):
    with st.spinner(f"Generating prompts for Day {day_num}..."):
        try:
            _save_day_prompts(prompt_gen, storage, ep_id, existing_prompts, day_num, day_content, model, aspect_ratio, temperature, replace=replace)
            st.success(f"Generated Day {day_num}")
            st.rerun()
        except Exception as e:
            st.error(f"Failed: {e}")


def _regenerate_day_prompts(prompt_gen, storage, ep_id, existing_prompts, day_num, day_content, model, aspect_ratio, temperature, replace: bool = False):
    with st.spinner(f"Regenerating prompts for Day {day_num}..."):
        try:
            _save_day_prompts(prompt_gen, storage, ep_id, existing_prompts, day_num, day_content, model, aspect_ratio, temperature, replace=replace)
            st.success(f"Regenerated Day {day_num}")
            st.rerun()
        except Exception as e:
            st.error(f"Failed: {e}")


def _save_day_prompts(prompt_gen, storage, ep_id, existing_prompts, day_num, day_content, model, aspect_ratio, temperature, replace: bool = False):
    """Generate, shape, and persist the prompt payload for one day."""
    new_prompts = prompt_gen.generate_scene_prompts(
        scene_text=day_content,
        day_number=day_num,
        model=model,
        aspect_ratio=aspect_ratio,
        temperature=temperature,
        system_prompt=st.session_state["visual_sys_prompt"],
    )
    save_day_prompt_sets(storage, ep_id, existing_prompts, day_num, aspect_ratio, new_prompts, replace=replace)
