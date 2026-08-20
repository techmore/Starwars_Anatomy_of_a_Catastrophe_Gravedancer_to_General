"""Story tab: episode concept → story generation → day-by-day view.

Ports the working render_story_stage() logic from app.py and adds:
  - per-day regeneration via StoryGenerator.regenerate_day() (Phase 4)
  - edit mode toggle for the full story text (Phase 4)
"""

import re
import streamlit as st

from src.utils.concepts import (
    get_used_jedi_names, build_concept_context_prompt, build_concept_extraction_prompt,
    build_missing_fields_repair_prompt,
    try_parse_full_episode_concept,
    _strip_context_reasoning,
    VALID_TONES,
)
from src.utils.logging_utils import get_logger, start_new_run_log, write_debug_artifact
from src.components.pipeline_timeline import render_pipeline_timeline, PipelineTracker, _fmt_duration as _fmt_total
from src.components.ui import preformatted_html
from src.utils.streaming_ui import build_stream_runtime, finalize_stream_state, render_cached_outline_banner, render_stream_update, reset_stream_panels
from src.utils.session_state import (
    build_episode_payload, build_jedi_details,
    hydrate_story_inputs,
    reset_story_flow,
    render_episode_prompt_archive_summary,
    GENERATION_PROFILES,
)
from src.utils.prompt_schema import DAILY_TARGET_TOKENS, validate_concept_dict, validate_outline_structure
from src.utils.story_validator import validate_story
from src.components.story_warnings import render_warnings


LOGGER = get_logger(__name__)

def _find_missing_concept_fields(concept: dict) -> list[str]:
    """Return a list of required field names that are empty or invalid."""
    err_to_field = {
        "title is required": "title",
        "setting is required": "setting",
        "jedi_name is required": "jedi_name",
        "jedi_species is required": "jedi_species",
        "jedi_rank is required": "jedi_rank",
        "jedi_saber is required": "jedi_saber",
        "jedi_personality is required": "jedi_personality",
        "jedi_target is required": "jedi_target",
        "tone must be a non-empty list": "tone",
    }
    return [err_to_field[err] for err in validate_concept_dict(concept) if err in err_to_field]


def render_story_stage(context):
    """Stage 1: Story generation."""
    mlx = context.mlx
    model = context.mlx_model
    temperature = context.temperature
    storage = context.storage
    story_gen = context.story_gen

    st.markdown("## Story workspace")
    st.markdown("Generate the narrative first. Art and video come after.")
    profile = GENERATION_PROFILES.get(
        st.session_state.get("generation_profile", "standard"),
        GENERATION_PROFILES["standard"],
    )
    st.markdown(
        f"""
        <div class="sw-run-summary">
          <div><span class="sw-eyebrow">ACTIVE RUN PROFILE</span><strong>{profile['label']}</strong></div>
          <div class="sw-run-copy">{profile['description']} <span>{profile['estimate']}.</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_workflow_stepper()
    st.markdown("---")

    checkpoints = storage.list_checkpoints()
    if checkpoints and not st.session_state.get("current_episode_id"):
        latest = checkpoints[0]
        drafts = latest.get("day_drafts", {})
        checkpoint_model = latest.get("metadata", {}).get("model", "")
        active_model = st.session_state.get("mlx_model", "")
        st.warning(
            f"A recoverable draft is available: **{latest.get('title', 'Untitled')}** "
            f"({len(drafts)} completed day(s))."
        )
        if checkpoint_model and active_model and checkpoint_model != active_model:
            st.caption(
                f"Checkpoint model: `{checkpoint_model}` · Current model: `{active_model}`. "
                "Resume will continue with the current model."
            )
        if st.button("▶ Load recoverable draft", key="load_story_checkpoint"):
            loaded = storage.load_checkpoint(latest.get("path", ""))
            if loaded:
                st.session_state["story_title"] = loaded.get("title", "")
                metadata = loaded.get("metadata", {})
                st.session_state["story_days"] = metadata.get("num_days", len(loaded.get("day_drafts", {})) or 1)
                st.session_state["story_setting"] = metadata.get("setting", "")
                st.session_state["jedi_name"] = metadata.get("target_jedi_name") or metadata.get("jedi_name", "")
                st.session_state["jedi_species"] = metadata.get("jedi_species", "")
                st.session_state["jedi_rank"] = metadata.get("jedi_rank", "")
                st.session_state["jedi_saber"] = metadata.get("jedi_lightsaber_color", "")
                st.session_state["jedi_personality"] = metadata.get("jedi_personality", "")
                st.session_state["jedi_target"] = metadata.get("jedi_why_targeted", "")
                st.session_state["story_tone"] = list(metadata.get("tone_focus", []) or [])
                st.session_state["story_additional"] = metadata.get("additional_instructions", "")
                st.session_state["story_outline"] = loaded.get("outline", "")
                st.session_state["story_day_drafts"] = {
                    int(day): text for day, text in loaded.get("day_drafts", {}).items()
                }
                st.session_state["story_draft_only_mode"] = True
                st.session_state["show_manual_form_state"] = True
                st.success("Checkpoint loaded. Review the inputs, then resume generation.")
                st.rerun()

    st.markdown("---")

    # Current episode banner
    if st.session_state.get("current_episode_id"):
        ep_id = st.session_state["current_episode_id"]
        ep = storage.load_episode(ep_id)
        if ep:
            st.markdown(f"**Current episode:** {ep['metadata'].get('title', 'Untitled')}")
            prompt_summary = render_episode_prompt_archive_summary(st, ep)
            st.caption(f"Saved prompt sets: {prompt_summary['prompt_sets']}")
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
        _run_concept_then_generate(mlx, model, storage)

    # === Manual form ===
    if show_manual:
        _render_manual_form()

    st.markdown("---")

    # === Generation step (auto-triggered) ===
    auto_gen = st.session_state.pop("auto_generate", False)
    if auto_gen:
        _run_generation(mlx, model, temperature, storage, story_gen)

    # === Current story display ===
    story = st.session_state.get("current_story", "")
    if story and not auto_gen:
        _render_current_story(story, storage, story_gen, model, temperature)


def _run_concept_then_generate(mlx, model, storage):
    """Phase 1: generate a rich creative concept, then extract structured fields."""
    if not st.session_state.get("log_run_path"):
        st.session_state["log_run_path"] = str(start_new_run_log("story-concept"))
    with st.status("🎲 Generating episode concept...", expanded=True) as status_box:
        try:
            used_names = get_used_jedi_names(storage.list_episodes())
            LOGGER.info("Starting concept generation for model=%s used_names=%d", model, len(used_names))

            timeline_widget = st.empty()
            progress = st.empty()
            context_preview = st.empty()
            extraction_preview = st.empty()
            tracker = PipelineTracker()

            tracker.start("concept")
            render_pipeline_timeline("concept", tracker=tracker, widget=timeline_widget)
            progress.info("Writing the episode context...")
            context_prompt = build_concept_context_prompt(used_names)
            context_chunks = []
            context_response = ""
            for chunk in mlx.generate_stream(
                model=model,
                prompt=context_prompt,
                system="You are a creative fiction writer. Output ONLY the requested prose. Do NOT include reasoning, thinking, analysis, planning, or meta-commentary. /no_think",
                temperature=0.7,
                max_tokens=2048,
            ):
                context_chunks.append(chunk)
                context_response = "".join(context_chunks)
                progress.info(f"Concept context... {len(context_response):,} chars")
                context_preview.markdown(preformatted_html(context_response), unsafe_allow_html=True)
            context_preview.markdown(preformatted_html(context_response), unsafe_allow_html=True)
            tracker.complete("concept")
            LOGGER.info("Concept context completed model=%s chars=%d elapsed=%s", model, len(context_response), tracker.format_duration("concept"))

            tracker.start("extraction")
            render_pipeline_timeline("extraction", completed_stages=["concept"], tracker=tracker, widget=timeline_widget)
            progress.info("Extracting structured fields from the context...")
            # Strip plain-text reasoning (Qwen's "Thinking in Qwen: 1. **Analyze...**")
            clean_context = _strip_context_reasoning(context_response)
            LOGGER.info(
                "Context filtered model=%s raw_chars=%d clean_chars=%d",
                model, len(context_response), len(clean_context),
            )

            extraction_prompt = build_concept_extraction_prompt(clean_context)
            extraction_chunks = []
            extraction_response = ""
            for chunk in mlx.generate_stream(
                model=model,
                prompt=extraction_prompt,
                system="You are a data extraction system. Output ONLY valid JSON. Do NOT include reasoning, thinking, analysis, or meta-commentary. /no_think",
                temperature=0.2,
                max_tokens=2048,
            ):
                extraction_chunks.append(chunk)
                extraction_response = "".join(extraction_chunks)
                progress.info(f"Extracting fields... {len(extraction_response):,} chars")
                extraction_preview.markdown(preformatted_html(extraction_response), unsafe_allow_html=True)
            extraction_preview.markdown(preformatted_html(extraction_response), unsafe_allow_html=True)
            tracker.complete("extraction")
            LOGGER.info("Concept extraction completed model=%s chars=%d elapsed=%s", model, len(extraction_response), tracker.format_duration("extraction"))

            concept, errors = try_parse_full_episode_concept(
                extraction_response, fallback_text=clean_context,
            )

            # ------------------------------------------------------------------
            # Repair loop: when some fields are missing, do a targeted third
            # pass that asks the LLM to generate only the missing fields, then
            # re-parse and merge.
            # ------------------------------------------------------------------
            max_repair_attempts = 2
            completed_stages = ["concept", "extraction"]
            repair_started = False
            for attempt in range(max_repair_attempts):
                missing = _find_missing_concept_fields(concept)
                if not missing:
                    break

                if not repair_started:
                    tracker.start("repair")
                    repair_started = True
                render_pipeline_timeline("repair", completed_stages=completed_stages, tracker=tracker, widget=timeline_widget)
                LOGGER.info(
                    "Repair attempt %s/%s missing=%s model=%s",
                    attempt + 1, max_repair_attempts, missing, model,
                )
                progress.info(f"Repairing missing fields: {', '.join(missing)} (attempt {attempt + 1})...")

                repair_prompt = build_missing_fields_repair_prompt(
                    clean_context, concept, missing, used_names=used_names,
                )
                repair_chunks = []
                repair_response = ""
                for chunk in mlx.generate_stream(
                    model=model,
                    prompt=repair_prompt,
                    system="You are a data extraction system. Output ONLY valid JSON. Do NOT include reasoning, thinking, analysis, or meta-commentary. /no_think",
                    temperature=0.2,
                    max_tokens=1024,
                ):
                    repair_chunks.append(chunk)
                    repair_response = "".join(repair_chunks)
                    progress.info(f"Repairing... {len(repair_response):,} chars")
                LOGGER.info(
                    "Repair response model=%s chars=%d attempt=%s",
                    model, len(repair_response), attempt + 1,
                )

                # Parse the repair response — it should contain only the
                # missing fields as a JSON object.
                repair_concept, _ = try_parse_full_episode_concept(
                    repair_response, fallback_text=clean_context,
                )

                # Merge: overwrite only fields that were missing AND got
                # a non-empty value from the repair pass.
                for key in missing:
                    val = repair_concept.get(key)
                    if key == "tone":
                        if isinstance(val, list) and val:
                            concept["tone"] = val
                    elif val:
                        concept[key] = val

            # ------------------------------------------------------------------
            # If still failing after repair, write debug artifacts and stop.
            # ------------------------------------------------------------------
            missing = _find_missing_concept_fields(concept)
            if missing:
                if repair_started:
                    tracker.complete("repair")
                render_pipeline_timeline("", completed_stages=completed_stages, error_stage="repair", tracker=tracker, widget=timeline_widget)
                context_artifact = write_debug_artifact("concept-context-response.txt", context_response)
                extraction_artifact = write_debug_artifact("concept-extraction-response.txt", extraction_response)
                LOGGER.error(
                    "Concept parse failed after %s repair attempts model=%s "
                    "missing=%s context_len=%d extraction_len=%d "
                    "context_artifact=%s extraction_artifact=%s",
                    max_repair_attempts, model, missing,
                    len(context_response), len(extraction_response),
                    context_artifact, extraction_artifact,
                )
                status_box.update(label="❌ Failed to parse concept", state="error")
                with st.expander("Context response", expanded=False):
                    st.markdown(preformatted_html(context_response), unsafe_allow_html=True)
                with st.expander("Extraction response", expanded=False):
                    st.markdown(preformatted_html(extraction_response), unsafe_allow_html=True)
                st.stop()

            if repair_started:
                tracker.complete("repair")
                completed_stages.append("repair")
            LOGGER.info(
                "Concept parsed title=%s days=%s jedi=%s setting=%s concept_elapsed=%s extraction_elapsed=%s repair_elapsed=%s",
                concept.get("title", ""),
                concept.get("days", ""),
                concept.get("jedi_name", ""),
                concept.get("setting", ""),
                tracker.format_duration("concept"),
                tracker.format_duration("extraction"),
                tracker.format_duration("repair") or "skipped",
            )
            st.write("Concept captured. Generating full story...")
            hydrate_story_inputs(st, concept)
            st.session_state["auto_generate"] = True

            status_box.update(label="✅ Concept ready — generating story...", state="running")
            st.rerun()
        except Exception as e:
            LOGGER.exception("Concept generation failed for model=%s", model)
            status_box.update(label="❌ Failed", state="error")
            st.error(f"Failed during concept generation: {e}")
            st.stop()


def _render_manual_form():
    st.markdown("### Manual Episode Builder")
    profile_keys = list(GENERATION_PROFILES)
    current_profile = st.session_state.get("generation_profile", "standard")
    profile_index = profile_keys.index(current_profile) if current_profile in profile_keys else 1
    selected_profile = st.selectbox(
        "Generation profile",
        options=profile_keys,
        index=profile_index,
        format_func=lambda key: GENERATION_PROFILES[key]["label"],
        key="generation_profile_selector",
        help="Choose Smoke test before a long-form run to verify the model and save path.",
    )
    st.session_state["generation_profile"] = selected_profile
    selected_config = GENERATION_PROFILES[selected_profile]
    previous_profile = st.session_state.get("_generation_profile_rendered")
    if previous_profile != selected_profile:
        st.session_state["story_days"] = selected_config["days"]
        st.session_state["_generation_profile_rendered"] = selected_profile
    st.caption(
        f"{selected_config['description']} Expected runtime: {selected_config['estimate']}. "
        "Completed stages are retained in the current session."
    )
    col1, col2 = st.columns([2, 1])
    with col1:
        st.text_input(
            "Episode title",
            placeholder="e.g., The Hunting of Jedi Vex'arii",
            key="story_title",
        )
    with col2:
        default_days = selected_config["days"]
        min_days = 1 if selected_profile == "smoke" else 3
        st.slider(
            "Days (long-form targets ~45,000 output tokens per day)",
            min_value=min_days,
            max_value=8,
            value=max(min_days, min(default_days, 8)),
            key="story_days",
        )

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

    st.text_area("📝 Additional notes (optional)", key="story_additional", placeholder="Any specific sections, chapters, or creative direction...", height=80)

    if st.button("📖 Generate Story", type="primary", use_container_width=True, key="manual_generate"):
        st.session_state["auto_generate"] = True
        st.rerun()


def _render_workflow_stepper() -> None:
    """Orient users in the production pipeline without changing tab behavior."""
    has_story = bool(st.session_state.get("current_story", "").strip())
    has_outline = bool(st.session_state.get("story_outline", "").strip())
    has_episode = bool(st.session_state.get("current_episode_id"))
    steps = [
        ("01", "Concept", not has_outline and not has_story),
        ("02", "Outline", has_outline and not has_story),
        ("03", "Draft", has_story and not has_episode),
        ("04", "Review", has_episode),
        ("05", "Visuals", False),
    ]
    active_seen = False
    items = []
    for number, label, active in steps:
        cls = "active" if active and not active_seen else "done" if active_seen else "pending"
        if active:
            active_seen = True
        items.append(f'<div class="sw-step {cls}"><span>{number}</span><b>{label}</b></div>')
    st.markdown(f'<nav class="sw-stepper" aria-label="Episode production stages">{"".join(items)}</nav>', unsafe_allow_html=True)


def _run_generation(mlx, model, temperature, storage, story_gen):
    if not st.session_state.get("log_run_path"):
        st.session_state["log_run_path"] = str(start_new_run_log("story-generate"))
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

    LOGGER.info(
        "Starting story generation model=%s title=%s days=%s setting=%s temp=%.2f",
        model,
        title,
        num_days,
        setting,
        temperature,
    )
    st.markdown("### 📖 Generating your episode...")
    with st.status(f"📡 Streaming from {model}...", expanded=True) as gen_status:
        try:
            timeline_widget = st.empty()
            story_container = st.empty()
            runtime = build_stream_runtime()
            widgets = runtime["widgets"]
            progress_state = runtime["progress_state"]
            progress_state["target_tokens"] = DAILY_TARGET_TOKENS * max(1, num_days)
            reset_stream_panels(widgets, progress_state)
            tracker = PipelineTracker()

            # Concept stages are done if we're here (random path) or skipped (manual).
            _completed = ["concept", "extraction", "repair"]

            def _push_progress(stage: str, message: str, text: str = "") -> None:
                render_stream_update(stage, message, text, widgets, progress_state)

            def _checkpoint_day(day_number: int, day_text: str) -> None:
                """Retain completed days so a failed run can be resumed in-session."""
                drafts = dict(st.session_state.get("story_day_drafts", {}))
                drafts[day_number] = day_text
                st.session_state["story_day_drafts"] = drafts
                checkpoint_path = storage.save_checkpoint(
                    title=title,
                    metadata=payload["metadata"],
                    day_drafts=drafts,
                    outline=st.session_state.get("story_outline", ""),
                )
                _push_progress("checkpoint", f"Checkpoint saved after Day {day_number}.")
                LOGGER.info("Story checkpoint saved path=%s day=%s", checkpoint_path, day_number)

            outline = st.session_state.get("story_outline", "").strip()
            if outline:
                cached_errors = validate_outline_structure(outline, expected_days=num_days)
                if cached_errors:
                    LOGGER.warning("Discarding invalid cached outline errors=%s", cached_errors)
                    outline = ""
                    st.session_state["story_outline"] = ""
                    st.session_state["story_outline_days"] = []
                    st.session_state["story_outline_approved"] = False
            if outline:
                render_cached_outline_banner(widgets, outline)
                _completed.append("outline")
                st.session_state["story_outline_approved"] = True
            if not outline:
                tracker.start("outline")
                render_pipeline_timeline("outline", completed_stages=_completed, tracker=tracker, widget=timeline_widget)
                gen_status.write("Building outline...")
                outline = story_gen.generate_episode_outline(
                    model=model,
                    title=title,
                    num_days=num_days,
                    jedi_details=jedi_details,
                    setting=setting,
                    tone_focus=tone_focus,
                    additional_instructions=additional,
                    temperature=max(0.2, temperature - 0.2),
                    system_prompt=st.session_state["story_sys_prompt"],
                    progress_callback=_push_progress,
                )
                # Save outline as debug artifact for inspection.
                write_debug_artifact("outline-response.txt", outline)
                LOGGER.info("Outline artifact written chars=%d", len(outline))
                outline_errors = validate_outline_structure(outline, expected_days=num_days)
                if outline_errors:
                    LOGGER.warning("Outline validation issues: %s", outline_errors)
                st.session_state["story_outline"] = outline
                st.session_state["story_outline_days"] = []
                st.session_state["story_outline_approved"] = True
                _push_progress("outline", f"Outline generated ({len(outline):,} chars)")
                tracker.complete("outline")
                LOGGER.info("Outline completed elapsed=%s chars=%d", tracker.format_duration("outline"), len(outline))
            outline_days = story_gen.parse_outline_days(outline)
            st.session_state["story_outline_days"] = outline_days
            LOGGER.info("Outline parsed days=%d expected_days=%d", len(outline_days), num_days)
            _completed.append("outline")
            tracker.start("story")
            render_pipeline_timeline("story", completed_stages=_completed, tracker=tracker, widget=timeline_widget)
            _push_progress("outline", "Outline approved. Expanding prose.")
            gen_status.write("Expanding the episode...")

            current_day_drafts = dict(st.session_state.get("story_day_drafts", {}))
            full_response = story_gen.generate_episode_story_multi_pass(
                model=model,
                title=title,
                num_days=num_days,
                jedi_details=jedi_details,
                setting=setting,
                tone_focus=tone_focus,
                additional_instructions=additional,
                temperature=temperature,
                system_prompt=st.session_state["story_sys_prompt"],
                outline=st.session_state.get("story_outline", ""),
                day_drafts=_build_day_draft_map(
                    st.session_state.get("story_outline_days", []),
                    st.session_state.get("story_section_drafts", {}),
                    current_day_drafts,
                ),
                draft_only=st.session_state.get("story_draft_only_mode", False),
                progress_callback=_push_progress,
                checkpoint_callback=_checkpoint_day,
            )
            finalize_stream_state(widgets, progress_state, character_count=len(full_response))
            story_container.markdown(full_response)
            quality_report = validate_story(full_response, expected_days=num_days)
            if quality_report["warnings"]:
                LOGGER.warning("Story quality warnings title=%s warnings=%s", title, quality_report["warnings"])
                render_warnings(quality_report)
            gen_status.update(label=f"✅ Generated {len(full_response):,} characters", state="complete")

            tracker.complete("story")
            _completed.append("story")

            # --- Critique pass ---
            tracker.start("save")
            render_pipeline_timeline("save", completed_stages=_completed, tracker=tracker, widget=timeline_widget)

            # Save the full story response as a debug artifact.
            write_debug_artifact("story-full-response.txt", full_response)
            LOGGER.info("Story artifact written chars=%d story_elapsed=%s", len(full_response), tracker.format_duration("story"))

            metadata = payload["metadata"]
            st.session_state["current_story"] = full_response
            st.session_state["current_metadata"] = metadata

            LOGGER.info("Saving episode title=%s chars=%d", title, len(full_response))
            episode_id = storage.save_episode(title=title, story=full_response, metadata=metadata)
            st.session_state["current_episode_id"] = episode_id
            storage.delete_checkpoint(title)

            tracker.complete("save")
            _completed.append("save")
            render_pipeline_timeline("", completed_stages=_completed, tracker=tracker, widget=timeline_widget)

            total_time = sum(t for t in tracker.timings.values())
            LOGGER.info(
                "Saved episode id=%s title=%s model=%s total_elapsed=%s outline=%s story=%s save=%s",
                episode_id, title, model, _fmt_total(total_time),
                tracker.format_duration("outline") or "skipped",
                tracker.format_duration("story"),
                tracker.format_duration("save"),
            )
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
            LOGGER.exception("Story generation failed for title=%s days=%s", title, num_days)
            render_pipeline_timeline("", completed_stages=_completed, error_stage="story", tracker=tracker, widget=timeline_widget)
            st.error(f"❌ Generation failed: {e}")
            completed_days = len(st.session_state.get("story_day_drafts", {}))
            if completed_days:
                st.info(
                    f"A checkpoint is available for {completed_days} completed day(s). "
                    "Resume will reuse those drafts as continuity context."
                )
                if st.button("▶ Resume from checkpoint", type="primary", key="resume_story_checkpoint"):
                    st.session_state["story_draft_only_mode"] = True
                    st.session_state["auto_generate"] = True
                    st.rerun()
            else:
                st.info("No completed-day checkpoint is available. Retry will rebuild the outline from the current inputs.")
                if st.button("↻ Retry generation", type="primary", key="retry_story_generation"):
                    st.session_state["story_outline"] = ""
                    st.session_state["story_outline_days"] = []
                    st.session_state["story_outline_approved"] = False
                    st.session_state["story_draft_only_mode"] = False
                    st.session_state["auto_generate"] = True
                    st.rerun()
            with st.expander("Technical details", expanded=False):
                st.code(str(e), language="text")
        finally:
            st.session_state.pop("log_run_path", None)


def _detect_current_day(story_text: str) -> str:
    matches = re.findall(r"## DAY (\d+):", story_text, re.IGNORECASE)
    return matches[-1] if matches else ""


def _render_outline_gate():
    """Display the editable outline when it has been generated but not yet approved."""
    st.markdown("### Outline ready for review")
    st.info("Approve the outline to begin prose expansion.")


def _rebuild_outline_from_days(days):
    return "\n\n".join(
        _build_day_outline(
            day.get("number"), day.get("title", f"Day {day.get('number')}"),
            day.get("purpose", ""), day.get("sections", []),
            day.get("ending_hook", ""),
        )
        for day in days
    )


def _build_day_outline(day_num, title, purpose, sections, ending_hook):
    lines = [f"## DAY {day_num}: {title}"]
    if purpose:
        lines.append(f"- Purpose: {purpose}")
    for idx, section in enumerate(sections, start=1):
        section_text = (section or "").strip()
        if section_text:
            lines.append(f"- Chapter {idx}: {section_text}")
    if ending_hook:
        lines.append(f"- Ending hook: {ending_hook}")
    return "\n".join(lines)


def _generate_section_preview(
    story_gen,
    model,
    title,
    num_days,
    outline,
    day_number,
    section_index,
    section_count,
    section_outline,
    day_outline,
    jedi_details,
    setting,
    tone_focus,
    additional_instructions,
    prior_text,
    temperature,
    system_prompt,
):
    return story_gen.mlx.generate(
        model=model,
        prompt=story_gen.build_section_expansion_prompt(
            title=title,
            num_days=num_days,
            outline=outline,
            day_number=day_number,
            section_index=section_index,
            section_count=section_count,
            section_outline=section_outline,
            prior_text=prior_text,
            day_outline=day_outline,
            jedi_details=jedi_details,
            setting=setting,
            tone_focus=tone_focus,
            additional_instructions=additional_instructions,
        ),
        system=system_prompt,
        temperature=temperature,
        max_tokens=6000,
    )





def _build_day_draft_map(days, section_drafts, day_drafts=None):
    draft_map = {}
    for day in days:
        sections = []
        day_num = day.get("number")
        for idx, section in enumerate(day.get("sections", []), start=1):
            key = f"{day_num}_{idx}"
            section_text = section_drafts.get(key)
            if not section_text:
                section_text = section["text"] if isinstance(section, dict) else section
            sections.append(section_text or "")
        day_draft_key = f"{day_num}"
        draft_map[day_num] = (day_drafts or {}).get(
            day_draft_key,
            _build_day_outline(
                day_num,
                day.get("title", f"Day {day_num}"),
                day.get("purpose", ""),
                sections,
                day.get("ending_hook", ""),
            ),
        )
    return draft_map


def _split_day_draft_into_sections(day_draft: str, section_count: int) -> list[str]:
    """Split an assembled day draft into section-sized chunks."""
    if not day_draft.strip():
        return [""] * max(1, section_count)

    lines = [line.strip() for line in day_draft.splitlines()]
    body_lines = []
    for line in lines:
        if not line:
            body_lines.append("")
            continue
        if line.startswith("## DAY "):
            continue
        if line.startswith("- Purpose:") or line.startswith("- Ending hook:"):
            continue
        if line.startswith("- Section "):
            body_lines.append(line.split(": ", 1)[1] if ": " in line else line)
            continue
        body_lines.append(line)

    raw_paragraphs = "\n".join(body_lines).split("\n\n")
    paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]
    if not paragraphs:
        paragraphs = [" ".join(body_lines).strip()] if body_lines else [day_draft.strip()]

    sections = [""] * max(1, section_count)
    if len(paragraphs) >= len(sections):
        for idx in range(len(sections)):
            sections[idx] = paragraphs[idx]
    else:
        for idx, paragraph in enumerate(paragraphs):
            sections[idx] = paragraph
        for idx in range(len(paragraphs), len(sections)):
            sections[idx] = paragraphs[-1]
    return sections


def _render_current_story(story, storage, story_gen, model, temperature):
    """Day-by-day view with quality warnings, regenerate-day, and edit mode."""
    st.markdown("---")
    st.markdown(f"## 📖 {st.session_state.get('story_title', 'Episode')}")

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

    edit_mode = st.toggle("✏️ Edit mode", value=False, key="story_edit_mode")
    ep_id = st.session_state.get("current_episode_id")

    if edit_mode and ep_id:
        _render_edit_mode(story, storage, ep_id)
        return

    # Day-by-day view with per-day regeneration (Phase 4).
    days = story_gen.parse_days(story)
    for day in days:
        dwc = f"({day['word_count']:,}) " if day.get('word_count') else ""
        with st.expander(f"{dwc}Day {day['number']}: {day['title']}", expanded=False):
            st.markdown(day["content"])
            # Regenerate just this day using the existing (previously dead) method.
            if ep_id:
                if st.button(f"🔄 Regenerate Day {day['number']}", key=f"regen_day_{day['number']}"):
                    with st.spinner(f"Regenerating Day {day['number']}..."):
                        try:
                            new_story = story_gen.regenerate_day(
                                model=model,
                                day_number=day["number"],
                                full_story=story,
                                title=st.session_state.get("story_title", ""),
                                num_days=st.session_state.get("story_days", 5),
                                jedi_details={
                                    "name": st.session_state.get("jedi_name", ""),
                                    "species": st.session_state.get("jedi_species", ""),
                                    "rank": st.session_state.get("jedi_rank", ""),
                                    "lightsaber_color": st.session_state.get("jedi_saber", ""),
                                    "personality": st.session_state.get("jedi_personality", ""),
                                    "why_targeted": st.session_state.get("jedi_target", ""),
                                },
                                setting=st.session_state.get("story_setting", ""),
                                tone_focus=st.session_state.get("story_tone", []),
                                additional_instructions="",
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
    a1, a2 = st.columns(2)
    with a1:
        if st.button("📚 Library", use_container_width=True, key="story_to_lib"):
            st.info("Switch to the **Library** tab for review, visuals, and export.")
    with a2:
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


def _render_critique_report(critique: dict):
    """Render the AI critique report with per-day scores and overall feedback."""
    st.markdown("### 📋 AI Critique")
    days = critique.get("days", [])
    overall = critique.get("overall", {})

    # Score row
    score_cols = st.columns(len(days) + 1)
    for idx, day in enumerate(days):
        score = day.get("score")
        with score_cols[idx]:
            st.metric(f"Day {day['number']}", f"{score}/100" if score is not None else "—")
    with score_cols[-1]:
        overall_score = overall.get("score")
        st.metric("Overall", f"{overall_score}/100" if overall_score is not None else "—")

    # Per-day feedback
    with st.expander("Day-by-day feedback", expanded=False):
        for day in days:
            st.markdown(f"**Day {day['number']}** — Score: {day.get('score', '—')}/100")
            if day.get("what_worked"):
                st.markdown(f"✅ {day['what_worked']}")
            if day.get("what_could_be_improved"):
                st.markdown(f"💡 {day['what_could_be_improved']}")
            st.markdown("---")

    # Overall feedback
    with st.expander("Overall episode feedback", expanded=True):
        for label, key in [
            ("Narrative Arc", "narrative_arc"),
            ("Pacing", "pacing"),
            ("Thematic Coherence", "thematic_coherence"),
            ("Character Consistency", "character_consistency"),
            ("Recommendations", "recommendations"),
        ]:
            text = overall.get(key, "")
            if text:
                st.markdown(f"**{label}:** {text}")
