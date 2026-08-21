"""Tab 2: Story Viewer & Editor + Visual Review Stage."""


import streamlit as st

from src.components.ui import aspect_to_dims, copy_button
from src.utils.logging_utils import start_new_run_log
from src.utils.session_state import (
    episode_selector_label,
    get_episode_banner_prompt,
    get_episode_chapter_prompts,
    get_episode_target_jedi_name,
    save_banner_prompt,
    save_chapter_prompt,
)
from src.utils.storage import EpisodeStorage
from src.utils.story_generator import StoryGenerator


def render_viewer_tab(context):
    """Render the story viewer/editor tab with visual review stage."""
    story_gen: StoryGenerator = context.story_gen
    storage: EpisodeStorage = context.storage
    prompt_gen = context.prompt_gen
    dt_client = context.dt_client
    model = context.mlx_model
    temperature = context.temperature

    st.markdown("## Review workspace")
    st.markdown('<div class="blood-accent">Read the archive. Edit the prose. Generate visuals. Keep moving forward.</div>', unsafe_allow_html=True)

    episodes = storage.list_episodes()
    if not episodes:
        st.info("No episodes saved yet. Generate one in the Story tab.")
        return

    ep_options = {episode_selector_label(ep): ep['id'] for ep in episodes}
    preferred_id = st.session_state.pop("viewer_selected_id", None)
    preferred_index = next(
        (index for index, episode_id in enumerate(ep_options.values()) if episode_id == preferred_id),
        0,
    )
    if preferred_id in ep_options.values():
        st.session_state["viewer_select"] = list(ep_options.keys())[preferred_index]
    selected_label = st.selectbox(
        "Select Episode", list(ep_options.keys()), index=preferred_index, key="viewer_select"
    )
    selected_id = ep_options[selected_label]

    episode = storage.load_episode(selected_id)
    if not episode:
        st.error("Failed to load episode.")
        return

    metadata = episode["metadata"]
    story = episode["story"]
    stats = story_gen.get_stats(story)

    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    with stat_col1:
        st.metric("Days", stats["num_days"])
    with stat_col2:
        st.metric("Words", f"{stats['word_count']:,}")
    with stat_col3:
        st.metric("Reading Time", f"{stats['reading_time_minutes']} min")
    with stat_col4:
        st.metric("Target Jedi", get_episode_target_jedi_name(episode))

    st.markdown("---")

    with st.expander("Episode Metadata", expanded=False):
        meta_col1, meta_col2 = st.columns(2)
        with meta_col1:
            st.markdown(f"**Title:** {metadata.get('title', 'N/A')}")
            st.markdown(f"**Target Jedi:** {get_episode_target_jedi_name(episode)}")
            st.markdown(f"**Species:** {metadata.get('jedi_species', 'N/A')}")
            st.markdown(f"**Rank:** {metadata.get('jedi_rank', 'N/A')}")
        with meta_col2:
            st.markdown(f"**Setting:** {metadata.get('setting', 'N/A')}")
            st.markdown(f"**Tone:** {', '.join(metadata.get('tone_focus', []))}")
            st.markdown(f"**Model:** {metadata.get('model', 'N/A')}")
            st.markdown(f"**Generation profile:** {metadata.get('generation_profile', 'legacy / unknown')}")

    st.markdown("---")

    edit_mode = st.toggle("Edit Mode", value=False, key="viewer_edit_toggle")
    if edit_mode:
        _render_editor(st, storage, story, selected_id)
        return

    # --- Visual Review Stage ---
    show_visuals = st.toggle("Visual Review Stage", value=False, key="viewer_visual_toggle",
                             help="Generate image prompts and render keyframes for this episode")
    if not show_visuals:
        render_story_days(story_gen, story)
        _render_danger_zone(st, storage, selected_id)
        return

    st.markdown("---")
    st.markdown("### 🎨 Visual Review Stage")
    st.caption("Generate image prompts per chapter, render via Draw Things, or batch the whole episode.")

    aspect_ratio = st.selectbox(
        "Aspect ratio", ["16:9", "21:9", "4:3", "3:2", "1:1"], index=0,
        key="viewer_ar",
    )
    steps = st.slider("Steps", 10, 40, 25, key="viewer_steps")
    cfg = st.slider("CFG", 1.0, 8.0, 2.5, 0.1, key="viewer_cfg")
    dt_ok = dt_client.check_connection()
    if not dt_ok:
        st.warning("Draw Things offline — prompt generation still works, rendering skipped.")

    existing_banner = get_episode_banner_prompt(episode)
    existing_chapters = get_episode_chapter_prompts(episode)

    # --- Banner ---
    _render_banner_section(st, prompt_gen, storage, dt_client, metadata, episode,
                           selected_id, model, temperature, existing_banner,
                           dt_ok, aspect_ratio, steps, cfg)

    # --- Chapter prompts ---
    chapters = prompt_gen.extract_chapters(story)
    _render_chapter_prompts_section(st, prompt_gen, storage, dt_client, chapters,
                                    episode, selected_id, model, temperature,
                                    existing_chapters, dt_ok, aspect_ratio, steps, cfg)

    # --- Batch actions ---
    _render_batch_actions(st, prompt_gen, storage, dt_client, metadata, story, chapters,
                          selected_id, model, temperature, episode, dt_ok, aspect_ratio, steps, cfg)

    # --- Story Arc banners ---
    _render_story_arc_section(st, prompt_gen, storage, dt_client, episodes, selected_id,
                              model, temperature, dt_ok, aspect_ratio, steps, cfg)

    _render_danger_zone(st, storage, selected_id)


def render_story_days(story_gen, story, expanded=True):
    """Render an episode's day sections consistently across the app."""
    st.markdown("### Story Content")
    days = story_gen.parse_days(story)
    for day in days:
        dwc = f"({day['word_count']:,}) " if day.get('word_count') else ""
        with st.expander(f"{dwc}DAY {day['number']}: {day['title']}", expanded=expanded):
            st.markdown(day['content'])


def _render_editor(st, storage, story, selected_id):
    """Render the inline story editor."""
    st.markdown("### Edit Story")
    edited_story = st.text_area("Story Markdown", value=story, height=600, key="viewer_story_editor")
    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button("Save Changes", type="primary"):
            lines = edited_story.split("\n")
            story_start = 0
            for i, line in enumerate(lines):
                if line.strip() == "---":
                    story_start = i + 1
                    break
            raw_story = "\n".join(lines[story_start:]).strip()
            storage.update_episode(episode_id=selected_id, story=raw_story, metadata={"updated_at": None})
            st.success("Episode updated.")
            st.rerun()
    with col_cancel:
        if st.button("Cancel"):
            st.rerun()


def _render_danger_zone(st, storage, selected_id):
    st.markdown("---")
    with st.expander("Danger Zone", expanded=False):
        st.warning("Deleting an episode is permanent.")
        if st.button("Delete Episode", type="secondary"):
            if storage.delete_episode(selected_id):
                st.success("Episode deleted.")
                st.rerun()
            else:
                st.error("Failed to delete episode.")


def _render_banner_section(st, prompt_gen, storage, dt_client, metadata, episode,
                           selected_id, model, temperature, existing_banner,
                           dt_ok, aspect_ratio, steps, cfg):
    """Episode banner prompt + render."""
    st.markdown("#### 📋 Episode Banner")
    if existing_banner:
        st.markdown("**Banner prompt**")
        copy_button(existing_banner, label="Copy", key="viewer_copy_banner")
        st.code(existing_banner, language="text")
        if st.button("Regenerate Banner Prompt", key="viewer_regen_banner"):
            st.session_state["log_run_path"] = str(start_new_run_log("viewer-banner"))
            with st.spinner("Regenerating banner prompt..."):
                result = prompt_gen.generate_banner_prompt(metadata, model, temperature)
                save_banner_prompt(storage, selected_id, result["banner_prompt"], result.get("negative_prompt", ""))
            st.success("Banner prompt regenerated.")
            st.rerun()
        if dt_ok:
            if st.button("🖼 Render Banner via Draw Things", key="viewer_render_banner", type="primary"):
                _render_keyframe(dt_client, storage, selected_id, 0, existing_banner,
                                 episode.get("prompts", {}).get("banner", {}).get("negative_prompt", ""),
                                 aspect_ratio, steps, cfg, "banner")
    else:
        if st.button("Generate Banner Prompt", key="viewer_gen_banner"):
            st.session_state["log_run_path"] = str(start_new_run_log("viewer-banner"))
            with st.spinner("Generating banner prompt..."):
                result = prompt_gen.generate_banner_prompt(metadata, model, temperature)
                save_banner_prompt(storage, selected_id, result["banner_prompt"], result.get("negative_prompt", ""))
            st.success("Banner prompt saved.")
            st.rerun()


def _render_chapter_prompts_section(st, prompt_gen, storage, dt_client, chapters,
                                    episode, selected_id, model, temperature,
                                    existing_chapters, dt_ok, aspect_ratio, steps, cfg):
    """Per-chapter prompt generation and rendering."""
    st.markdown("#### 📖 Chapter Prompts")
    existing_by_key = {(cp.get("day"), cp.get("chapter")): cp for cp in existing_chapters}

    for ch in chapters:
        key = (ch["day"], ch["chapter_index"])
        existing = existing_by_key.get(key)
        label = f"Day {ch['day']} — Chapter {ch['chapter_index']}: {ch['chapter_title']}"
        with st.expander(label, expanded=False):
            st.markdown(f"```\n{ch['text'][:400]}...\n```")
            if existing:
                st.markdown("**Generated prompts**")
                for shot in ["wide", "medium", "closeup"]:
                    text = existing.get(shot, "")
                    if text:
                        copy_button(text, label=f"Copy {shot}", key=f"viewer_copy_{key}_{shot}")
                        st.code(text, language="text", line_limit=5)
                neg = existing.get("negative_prompt", "")
                if neg:
                    st.caption(f"Negative: {neg[:100]}...")

                if dt_ok:
                    chosen = existing.get("wide", "") or existing.get("medium", "") or existing.get("closeup", "")
                    if st.button(f"🖼 Render Day {ch['day']} Ch{ch['chapter_index']}",
                                 key=f"viewer_render_{key}", type="primary"):
                        _render_keyframe(dt_client, storage, selected_id, ch["day"], chosen,
                                         neg, aspect_ratio, steps, cfg,
                                         f"day{ch['day']}-ch{ch['chapter_index']}")
            else:
                if st.button("Generate Prompt", key=f"viewer_gen_{key}"):
                    st.session_state["log_run_path"] = str(start_new_run_log("viewer-chapter"))
                    with st.spinner(f"Generating prompt for {label}..."):
                        result = prompt_gen.generate_chapter_prompt(
                            chapter_text=ch["text"],
                            day_number=ch["day"],
                            chapter_index=ch["chapter_index"],
                            chapter_title=ch["chapter_title"],
                            model=model,
                            aspect_ratio=aspect_ratio,
                            temperature=temperature,
                            system_prompt=st.session_state["visual_sys_prompt"],
                        )
                        save_chapter_prompt(storage, selected_id, result)
                    st.success(f"Prompt saved for Day {ch['day']} Chapter {ch['chapter_index']}.")
                    st.rerun()


def _render_batch_actions(st, prompt_gen, storage, dt_client, metadata, story, chapters,
                          selected_id, model, temperature, episode, dt_ok, aspect_ratio, steps, cfg):
    """Batch generate all prompts + render all for the episode."""
    st.markdown("#### ⚡ Batch Actions")
    col_banner, col_chapters, col_render = st.columns(3)
    with col_banner:
        if st.button("Generate + Save Banner", key="viewer_batch_banner", use_container_width=True):
            _batch_generate_banner(st, prompt_gen, storage, metadata, selected_id, model, temperature)
    with col_chapters:
        if st.button("Generate All Chapter Prompts", key="viewer_batch_chapters", use_container_width=True):
            _batch_generate_chapters(st, prompt_gen, storage, chapters, selected_id, model, temperature, aspect_ratio)
    with col_render:
        has_banner = bool(get_episode_banner_prompt(episode))
        has_chapters = bool(get_episode_chapter_prompts(episode))
        can_render = dt_ok and (has_banner or has_chapters)
        if st.button("Render All via Draw Things", key="viewer_batch_render",
                     use_container_width=True, disabled=not can_render,
                     help=None if can_render else "Need Draw Things online + at least one prompt"):
            _batch_render_all(st, dt_client, storage, episode, selected_id, aspect_ratio, steps, cfg)


def _batch_generate_banner(st, prompt_gen, storage, metadata, selected_id, model, temperature):
    st.session_state["log_run_path"] = str(start_new_run_log("batch-banner"))
    with st.spinner("Generating banner prompt..."):
        result = prompt_gen.generate_banner_prompt(metadata, model, temperature)
        save_banner_prompt(storage, selected_id, result["banner_prompt"], result.get("negative_prompt", ""))
    st.success("Banner prompt saved.")
    st.rerun()


def _batch_generate_chapters(st, prompt_gen, storage, chapters, selected_id, model, temperature, aspect_ratio):
    st.session_state["log_run_path"] = str(start_new_run_log("batch-chapters"))
    progress_bar = st.progress(0, text="Generating chapter prompts...")
    for i, ch in enumerate(chapters):
        progress_bar.progress((i) / len(chapters), text=f"Day {ch['day']} Ch{ch['chapter_index']}...")
        result = prompt_gen.generate_chapter_prompt(
            chapter_text=ch["text"],
            day_number=ch["day"],
            chapter_index=ch["chapter_index"],
            chapter_title=ch["chapter_title"],
            model=model,
            aspect_ratio=aspect_ratio,
            temperature=temperature,
            system_prompt=st.session_state["visual_sys_prompt"],
        )
        save_chapter_prompt(storage, selected_id, result)
    progress_bar.progress(1.0, text="All done.")
    st.success(f"Generated prompts for {len(chapters)} chapters.")
    st.rerun()


def _batch_render_all(st, dt_client, storage, episode, selected_id, aspect_ratio, steps, cfg):
    st.session_state["log_run_path"] = str(start_new_run_log("batch-render"))
    prompts = episode.get("prompts") or {}
    banner = (prompts.get("banner") or {}).get("banner_prompt", "")
    chapters = prompts.get("chapters") or []
    total = (1 if banner else 0) + len(chapters)
    if total == 0:
        st.warning("No prompts to render.")
        return
    neg_base = (prompts.get("banner") or {}).get("negative_prompt", "")
    progress_bar = st.progress(0, text="Rendering...")
    done = 0
    if banner:
        progress_bar.progress(0, text="Rendering banner...")
        try:
            _render_keyframe_plain(dt_client, storage, selected_id, 0, banner, neg_base, aspect_ratio, steps, cfg, "banner")
        except Exception as e:
            st.error(f"Banner render failed: {e}")
        done += 1
        progress_bar.progress(done / total)
    for ch in chapters:
        prompt = ch.get("wide") or ch.get("medium") or ch.get("closeup") or ""
        neg = ch.get("negative_prompt", "")
        if prompt:
            try:
                tag = f"day{ch['day']}-ch{ch['chapter']}"
                _render_keyframe_plain(dt_client, storage, selected_id, ch["day"], prompt, neg, aspect_ratio, steps, cfg, tag)
            except Exception as e:
                st.error(f"Day {ch['day']} Ch{ch['chapter']} render failed: {e}")
        done += 1
        progress_bar.progress(done / total, text=f"Rendered {done}/{total}")
    st.success(f"Rendered {done} images.")
    st.rerun()


def _render_keyframe(dt_client, storage, ep_id, day_num, prompt, negative, aspect_ratio, steps, cfg, tag):
    """Call Draw Things txt2img and show the result."""
    w, h = aspect_to_dims(aspect_ratio)
    with st.spinner(f"Rendering {tag} via Flux.2 Klein 4b..."):
        try:
            png = dt_client.generate_image(
                prompt=prompt, negative_prompt=negative,
                width=w, height=h, steps=steps, cfg=cfg,
            )
            rel = storage.save_image(ep_id, day=day_num, shot=tag, image_bytes=png)
            st.success(f"Saved to `{rel}`")
            st.image(png, caption=f"{tag} ({w}x{h})", use_container_width=True)
        except Exception as e:
            st.error(f"Draw Things render failed: {e}")
            with st.expander("Troubleshooting"):
                st.markdown(
                    "- Confirm Draw Things is running with the API Server enabled.\n"
                    "- Confirm Flux.2 Klein 4b is the active model.\n"
                    "- Try lowering the resolution or step count."
                )


def _render_keyframe_plain(dt_client, storage, ep_id, day_num, prompt, negative, aspect_ratio, steps, cfg, tag):
    """Call Draw Things txt2img without UI wrappers (for batch use)."""
    w, h = aspect_to_dims(aspect_ratio)
    png = dt_client.generate_image(
        prompt=prompt, negative_prompt=negative,
        width=w, height=h, steps=steps, cfg=cfg,
    )
    storage.save_image(ep_id, day=day_num, shot=tag, image_bytes=png)


def _render_story_arc_section(st, prompt_gen, storage, dt_client, episodes, selected_id,
                               model, temperature, dt_ok, aspect_ratio, steps, cfg):
    """Generate banner prompts for related / upcoming episodes (story arc)."""
    st.markdown("---")
    st.markdown("#### 🌐 Story Arc Banners")
    st.caption("Generate banner images for the next episodes in the series to visualize the arc ahead.")

    current_idx = next((i for i, ep in enumerate(episodes) if ep["id"] == selected_id), None)
    if current_idx is None:
        return

    arc_episodes = []
    for offset in [1, 2, 3, 4]:
        idx = current_idx + offset
        if idx < len(episodes):
            arc_episodes.append(episodes[idx])
        elif idx == len(episodes):
            arc_episodes.append({"title": f"Episode {current_idx + offset + 1} (Planned)", "id": None})
        else:
            break

    if not arc_episodes:
        st.info("No future episodes in the archive. Generate more stories to build an arc.")
        return

    st.markdown(f"**Next {len(arc_episodes)} episodes in arc:**")
    arc_cols = st.columns(len(arc_episodes))
    for i, arc_ep in enumerate(arc_episodes):
        with arc_cols[i]:
            st.markdown(f"**{arc_ep['title'][:30]}**")
            if arc_ep.get("id"):
                ep_data = storage.load_episode(arc_ep["id"])
                if ep_data:
                    existing = get_episode_banner_prompt(ep_data)
                    meta = ep_data["metadata"]
                    if existing:
                        st.code(existing[:120] + ("..." if len(existing) > 120 else ""), language="text")
                        if dt_ok and st.button("🖼 Render", key=f"arc_render_{i}"):
                            neg = (ep_data.get("prompts") or {}).get("banner", {}).get("negative_prompt", "")
                            _render_keyframe(dt_client, storage, arc_ep["id"], i + 1, existing, neg,
                                             aspect_ratio, steps, cfg, f"arc-banner-{i + 1}")
                    else:
                        if st.button("Generate Banner", key=f"arc_gen_{i}"):
                            st.session_state["log_run_path"] = str(start_new_run_log("arc-banner"))
                            with st.spinner(f"Generating banner for {arc_ep['title']}..."):
                                result = prompt_gen.generate_banner_prompt(meta, model, temperature)
                                save_banner_prompt(storage, arc_ep["id"], result["banner_prompt"],
                                                   result.get("negative_prompt", ""))
                            st.success(f"Banner saved for {arc_ep['title']}.")
                            st.rerun()
            else:
                st.caption("Not yet generated.")
