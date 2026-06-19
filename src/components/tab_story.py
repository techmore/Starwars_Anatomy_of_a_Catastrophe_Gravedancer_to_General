"""Story tab: episode concept → story generation → day-by-day view.

Ports the working render_story_stage() logic from app.py and adds:
  - story quality validation warnings (Phase 4)
  - per-day regeneration via StoryGenerator.regenerate_day() (Phase 4)
  - edit mode toggle for the full story text (Phase 4)
"""

import re
import streamlit as st

from src.utils.concepts import (
    get_used_jedi_names, build_full_episode_concept_prompt, parse_full_episode_concept,
    VALID_TONES,
)
from src.utils.session_state import (
    build_episode_payload,
    clear_current_episode,
    clear_story_inputs,
    hydrate_story_inputs,
    reset_story_flow,
)
from src.utils.story_validator import validate_story, render_warnings


def render_story_stage(context):
    """Stage 1: Story generation."""
    ollama = context.ollama
    model = context.model
    temperature = context.temperature
    storage = context.storage
    story_gen = context.story_gen

    st.markdown("# 📖 Story")
    st.markdown("Generate the episode narrative first. Art and video come after.")
    st.markdown("---")

    # Current episode banner
    if st.session_state.get("current_episode_id"):
        ep_id = st.session_state["current_episode_id"]
        ep = storage.load_episode(ep_id)
        if ep:
            st.markdown(f"**Current episode:** {ep['metadata'].get('title', 'Untitled')}")
            if st.button("← New Episode"):
                reset_story_flow(st)
                st.rerun()
            st.markdown("---")

    # === Workflow choice ===
    st.markdown("### Choose your workflow")
    col_primary, col_secondary = st.columns([3, 1])

    with col_primary:
        randomize_clicked = st.button(
            "🎲 Generate Random Episode",
            type="primary",
            use_container_width=True,
            key="randomize_generate",
            help="LLM picks all parameters and generates the full story in one click",
        )
    with col_secondary:
        manual_clicked = st.button(
            "✏️ Build Manually",
            use_container_width=True,
            key="show_manual_form",
            help="Open the manual form to fill in your own parameters",
        )

    if manual_clicked:
        st.session_state["show_manual_form_state"] = not st.session_state["show_manual_form_state"]
    show_manual = st.session_state["show_manual_form_state"]

    used_count = len(get_used_jedi_names(storage.list_episodes()))
    if used_count > 0:
        st.caption(f"📚 {used_count} Jedi already hunted — random generation will avoid repeats")
    else:
        st.caption("📚 No saved episodes yet — start your archive with a random episode")

    st.markdown("---")

    # === Randomize flow ===
    if randomize_clicked:
        _run_concept_then_generate(ollama, model, storage)

    # === Manual form ===
    if show_manual:
        _render_manual_form()

    st.markdown("---")

    # === Generation step (auto-triggered) ===
    auto_gen = st.session_state.pop("auto_generate", False)
    if auto_gen:
        _run_generation(ollama, model, temperature, storage, story_gen)

    # === Current story display ===
    story = st.session_state.get("current_story", "")
    if story and not auto_gen:
        _render_current_story(story, storage, story_gen, model, temperature)


def _run_concept_then_generate(ollama, model, storage):
    """Phase 1 of the one-click flow: generate concept, then hand off to generation."""
    with st.status("🎲 Generating episode concept...", expanded=True) as status_box:
        try:
            used_names = get_used_jedi_names(storage.list_episodes())
            concept_prompt = build_full_episode_concept_prompt(used_names)

            progress = st.empty()
            concept_preview = st.empty()
            progress.info("Streaming the concept draft...")
            concept_response = ""
            for chunk in ollama.generate_stream(
                model=model,
                prompt=concept_prompt,
                temperature=0.9,
                max_tokens=800,
            ):
                concept_response += chunk
                progress.info(f"Streaming concept draft... {len(concept_response):,} chars")
                concept_preview.markdown(f"```text\n{concept_response}\n```")
            concept_preview.markdown(f"```text\n{concept_response}\n```")
            concept = parse_full_episode_concept(concept_response)

            if not concept.get("title") or not concept.get("jedi_name"):
                status_box.update(label="❌ Failed to parse concept", state="error")
                with st.expander("Raw response", expanded=False):
                    st.text(concept_response)
                st.stop()

            st.write("Concept captured. Generating full story...")
            hydrate_story_inputs(st, concept)
            st.session_state["auto_generate"] = True

            status_box.update(label="✅ Concept ready — generating story...", state="running")
            st.rerun()
        except Exception as e:
            status_box.update(label="❌ Failed", state="error")
            st.error(f"Failed: {e}")
            st.stop()


def _render_manual_form():
    st.markdown("### Manual Episode Builder")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.text_input(
            "Episode title",
            placeholder="e.g., The Hunting of Jedi Vex'arii",
            key="story_title",
        )
    with col2:
        st.slider("Days (5 recommended for ~7,500 word novella)", min_value=3, max_value=8, value=5, key="story_days")

    with st.expander("🎯 Jedi Target", expanded=True):
        jc1, jc2 = st.columns(2)
        with jc1:
            st.text_input("Name", key="jedi_name", placeholder="e.g., Vex'arii")
            st.text_input("Species", key="jedi_species", placeholder="e.g., Miraluka, Twi'lek")
            st.text_input("Rank", key="jedi_rank", placeholder="e.g., Jedi Knight")
        with jc2:
            st.text_input("Lightsaber color", key="jedi_saber", placeholder="e.g., Viridian, amber")
            st.text_input("Personality/ability", key="jedi_personality", placeholder="e.g., Stoic philosopher, Form IV master")
            st.text_input("Why targeted", key="jedi_target", placeholder="e.g., Blocked Separatist supply line")

    col3, col4 = st.columns(2)
    with col3:
        st.text_input("🌍 Setting / Planet", key="story_setting", placeholder="e.g., Ruins of Jabiim, Kalee bone deserts")
    with col4:
        st.multiselect("🎭 Tone / Focus", options=VALID_TONES, key="story_tone")

    st.text_area("📝 Additional notes (optional)", key="story_additional", placeholder="Any specific beats or creative direction...", height=80)

    if st.button("📖 Generate Story", type="primary", use_container_width=True, key="manual_generate"):
        st.session_state["auto_generate"] = True
        st.rerun()


def _run_generation(ollama, model, temperature, storage, story_gen):
    payload = build_episode_payload(st, model, temperature)
    context = payload["story_context"]
    title = context["title"]
    num_days = context["num_days"]
    setting = context["setting"]
    jedi_details = payload["jedi_details"]
    tone_focus = context["tone_focus"]
    additional = context["additional_instructions"]

    if not title:
        st.error("Title is required. Use 'Build Manually' to set one.")
        return

    st.markdown("### 📖 Generating your episode...")
    with st.status(f"📡 Streaming from {model}...", expanded=True) as gen_status:
        try:
            full_response = ""
            story_container = st.empty()
            progress = st.empty()
            day_hint = st.empty()
            gen_status.write("Starting stream...")

            for chunk in story_gen.generate_story_stream(
                model=model,
                title=title,
                num_days=num_days,
                jedi_details=jedi_details,
                setting=setting,
                tone_focus=tone_focus,
                additional_instructions=additional,
                temperature=temperature,
                system_prompt=st.session_state["story_sys_prompt"],
            ):
                full_response += chunk
                gen_status.write(f"📝 {len(full_response):,} chars streamed...")
                current_day = _detect_current_day(full_response)
                if current_day:
                    day_hint.info(f"Current section: Day {current_day}")
                progress.info(f"Story streaming in progress... {len(full_response):,} chars")
                story_container.markdown(f"{full_response}\n\n*▌ generating...*")

            story_container.markdown(full_response)
            day_hint.success("Story stream complete.")
            gen_status.update(label=f"✅ Generated {len(full_response):,} characters", state="complete")

            metadata = payload["metadata"]
            st.session_state["current_story"] = full_response
            st.session_state["current_metadata"] = metadata

            episode_id = storage.save_episode(title=title, story=full_response, metadata=metadata)
            st.session_state["current_episode_id"] = episode_id

            st.success(f"✅ Episode saved: **{title}**")
            st.markdown("### Next steps")
            n1, n2, n3 = st.columns(3)
            with n1:
                if st.button("🎨 Generate Art Prompts", use_container_width=True):
                    st.info("Switch to the **Art** tab to generate image prompts for each day.")
            with n2:
                if st.button("📚 View in Library", use_container_width=True):
                    st.info("Switch to the **Library** tab to browse all episodes.")
            with n3:
                if st.button("🔄 Generate Another", use_container_width=True):
                    st.session_state["current_story"] = ""
                    st.session_state["current_episode_id"] = None
                    st.rerun()
        except Exception as e:
            st.error(f"❌ Generation failed: {e}")


def _detect_current_day(story_text: str) -> str:
    matches = re.findall(r"## DAY (\d+):", story_text, re.IGNORECASE)
    return matches[-1] if matches else ""


def _render_current_story(story, storage, story_gen, model, temperature):
    """Day-by-day view with quality warnings, regenerate-day, and edit mode."""
    st.markdown("---")
    st.markdown(f"## 📖 {st.session_state.get('story_title', 'Episode')}")

    # Quality validation (Phase 4) — informs but doesn't block.
    expected_days = st.session_state.get("current_metadata", {}).get("num_days")
    report = validate_story(story, expected_days=expected_days)
    render_warnings(report)

    # Stats row
    stats = story_gen.get_stats(story)
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Days", stats["num_days"])
    with m2:
        st.metric("Words", f"{stats['word_count']:,}")
    with m3:
        st.metric("Reading", f"{stats['reading_time_minutes']} min")
    with m4:
        st.metric("Jedi", st.session_state.get("jedi_name", "Unknown"))

    st.markdown("---")

    # Edit mode toggle (Phase 4).
    edit_mode = st.toggle("✏️ Edit mode", value=False, key="story_edit_mode")
    ep_id = st.session_state.get("current_episode_id")

    if edit_mode and ep_id:
        _render_edit_mode(story, storage, ep_id)
        return

    # Day-by-day view with per-day regeneration (Phase 4).
    days = story_gen.parse_days(story)
    for day in days:
        with st.expander(f"Day {day['number']}: {day['title']}", expanded=False):
            st.markdown(day["content"])
            # Regenerate just this day using the existing (previously dead) method.
            if ep_id:
                if st.button(f"🔄 Regenerate Day {day['number']}", key=f"regen_day_{day['number']}"):
                    with st.spinner(f"Regenerating Day {day['number']}..."):
                        try:
                            new_story = story_gen.regenerate_day(
                                story=story,
                                day_number=day["number"],
                                model=model,
                                temperature=temperature + 0.1,
                                system_prompt=st.session_state["story_sys_prompt"],
                            )
                            st.session_state["current_story"] = new_story
                            storage.update_episode(episode_id=ep_id, story=new_story)
                            st.success(f"Day {day['number']} regenerated.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to regenerate day: {e}")

    st.markdown("---")
    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("🎨 Generate Art", use_container_width=True, key="story_to_art"):
            st.info("Switch to the **Art** tab to generate image prompts.")
    with a2:
        if st.button("📚 Library", use_container_width=True, key="story_to_lib"):
            st.info("Switch to the **Library** tab to export.")
    with a3:
        if st.button("🔄 New Episode", use_container_width=True, key="story_new"):
            reset_story_flow(st)
            st.rerun()


def _render_edit_mode(story, storage, ep_id):
    """Full-story text editor. Saves via update_episode (metadata-preserving)."""
    st.markdown("### ✏️ Edit story")
    st.caption("Edit the full story text below. Metadata is preserved.")

    edited = st.text_area(
        "Story markdown",
        value=story,
        height=500,
        key="story_edit_area",
        label_visibility="collapsed",
    )

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("💾 Save", type="primary", use_container_width=True):
            storage.update_episode(episode_id=ep_id, story=edited)
            st.session_state["current_story"] = edited
            st.success("Saved.")
            st.rerun()
    with c2:
        if st.button("Cancel"):
            st.session_state["story_edit_mode"] = False
            st.rerun()
