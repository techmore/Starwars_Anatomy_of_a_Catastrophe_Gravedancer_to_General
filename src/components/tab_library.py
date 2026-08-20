"""Tab 4: Episode Library & Export."""

import streamlit as st
import json
from pathlib import Path
from src.utils.storage import EpisodeStorage
from src.utils.session_state import (
    build_episode_full_json_export,
    get_episode_target_jedi_name,
    get_episode_prompt_sets,
    get_episode_day_prompt_sets,
    render_episode_prompt_archive_summary,
    summarize_episode_collection,
    load_episode_into_session,
)


def render_library_tab(context):
    """Render the episode library/export tab."""
    storage: EpisodeStorage = context.storage
    prompt_gen = context.prompt_gen
    dt_client = context.dt_client
    story_gen = context.story_gen
    model = context.mlx_model
    temperature = context.temperature
    
    st.markdown("## Archive workspace")
    st.markdown('<div class="blood-accent">Your archive of hunts. Export. Share. Continue the legacy.</div>', unsafe_allow_html=True)
    
    episodes = storage.list_episodes()
    collection_summary = summarize_episode_collection(episodes)
    
    if not episodes:
        st.info("No episodes saved yet. Generate one in the Story tab.")
        return
    
    # Stats
    stat_col1, stat_col2, stat_col3 = st.columns(3)
    with stat_col1:
        st.metric("Total Episodes", collection_summary["total_episodes"])
    with stat_col2:
        st.metric("Total Days", collection_summary["total_days"])
    with stat_col3:
        st.metric("Unique Jedi", collection_summary["unique_jedi"])

    prompt_col1, prompt_col2 = st.columns(2)
    with prompt_col1:
        st.metric("Saved Prompt Sets", collection_summary["total_prompt_sets"])
    with prompt_col2:
        st.metric("Episodes With Prompts", collection_summary["episodes_with_prompts"])

    coverage_col1, coverage_col2 = st.columns(2)
    with coverage_col1:
        st.metric("Prompt Days Covered", collection_summary["total_prompt_days"])
    with coverage_col2:
        st.metric("Fully Covered Episodes", collection_summary["covered_episodes"])
    
    st.markdown("---")
    
    # Filter
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        search = st.text_input("Search by title or Jedi", key="lib_search")
    with filter_col2:
        sort_by = st.selectbox(
            "Sort by",
            ["Newest first", "Oldest first", "Title A-Z", "Title Z-A"],
            key="lib_sort"
        )
    
    # Filter and sort
    filtered = episodes
    if search:
        search_lower = search.lower()
        filtered = [
            ep for ep in filtered
            if search_lower in ep.get("title", "").lower()
            or search_lower in get_episode_target_jedi_name(ep).lower()
        ]
    
    if sort_by == "Newest first":
        filtered = sorted(filtered, key=lambda x: x.get("created_at", ""), reverse=True)
    elif sort_by == "Oldest first":
        filtered = sorted(filtered, key=lambda x: x.get("created_at", ""))
    elif sort_by == "Title A-Z":
        filtered = sorted(filtered, key=lambda x: x.get("title", "").lower())
    elif sort_by == "Title Z-A":
        filtered = sorted(filtered, key=lambda x: x.get("title", "").lower(), reverse=True)
    
    st.markdown(f"**Showing {len(filtered)} episode(s)**")
    st.markdown("---")
    
    # Episode grid
    cols_per_row = 2
    for i in range(0, len(filtered), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            if i + j < len(filtered):
                ep = filtered[i + j]
                with col:
                    with st.container():
                        st.markdown(f"### {ep.get('title', 'Untitled')}")
                        st.markdown(f"**Target Jedi:** {get_episode_target_jedi_name(ep)}")
                        st.markdown(f"**Setting:** {ep.get('setting', 'Unknown')}")
                        st.markdown(f"**Days:** {ep.get('num_days', 'N/A')}")
                        st.markdown(f"**Prompt Sets:** {ep.get('prompt_sets', 0)}")
                        st.markdown(f"**Prompt Days:** {ep.get('prompt_days', 0)}")
                        st.markdown(f"*Created: {ep.get('created_at', '')[:10]}*")
                        
                        btn_col1, btn_col2, btn_col3 = st.columns(3)
                        with btn_col1:
                            if st.button("Load", key=f"lib_load_{ep['id']}"):
                                loaded = storage.load_episode(ep["id"])
                                if loaded and load_episode_into_session(st, loaded):
                                    st.session_state["library_selected"] = ep["id"]
                                    st.success(f"Loaded: {ep['title']}")
                                    st.rerun()
                                else:
                                    st.error(f"Could not load: {ep['title']}")
                        with btn_col2:
                            if st.button("Export", key=f"lib_export_{ep['id']}"):
                                st.session_state["library_export"] = ep['id']
                        with btn_col3:
                            if st.button("Delete", key=f"lib_delete_{ep['id']}"):
                                st.session_state["library_confirm_delete"] = ep['id']
                        
                        st.markdown("---")
    
    # Handle actions
    if "library_confirm_delete" in st.session_state:
        ep_id = st.session_state["library_confirm_delete"]
        ep_title = next((ep["title"] for ep in episodes if ep["id"] == ep_id), "Unknown")
        st.warning(f"⚠️ Confirm deletion of: **{ep_title}**")
        conf_col1, conf_col2 = st.columns(2)
        with conf_col1:
            if st.button("Yes, Delete Permanently", type="primary"):
                if storage.delete_episode(ep_id):
                    st.success("Episode deleted.")
                    del st.session_state["library_confirm_delete"]
                    st.rerun()
        with conf_col2:
            if st.button("Cancel"):
                del st.session_state["library_confirm_delete"]
                st.rerun()
    
    if "library_export" in st.session_state:
        ep_id = st.session_state["library_export"]
        episode = storage.export_episode_bundle(ep_id)
        
        if episode:
            st.markdown("---")
            st.markdown(f"### Export: {episode['metadata'].get('title', 'Untitled')}")
            prompt_summary = render_episode_prompt_archive_summary(st, episode)
            st.caption(f"Saved prompt sets: {prompt_summary['prompt_sets']}")

            exp_col1, exp_col2, exp_col3 = st.columns(3)

            with exp_col1:
                st.download_button(
                    "Download Story (.md)",
                    data=episode["story"],
                    file_name=f"{ep_id}_story.md",
                    mime="text/markdown",
                    key=f"dl_md_{ep_id}"
                )

            with exp_col2:
                json_data = build_episode_full_json_export(episode)
                st.download_button(
                    "Download Full JSON",
                    data=json.dumps(json_data, indent=2),
                    file_name=f"{ep_id}_full.json",
                    mime="application/json",
                    key=f"dl_json_{ep_id}"
                )

            with exp_col3:
                if episode.get("prompts"):
                    st.download_button(
                        "Download Prompts (.json)",
                        data=json.dumps(episode["prompts"], indent=2),
                        file_name=f"{ep_id}_prompts.json",
                        mime="application/json",
                        key=f"dl_prompts_{ep_id}"
                    )
                else:
                    st.info("No prompts saved.")

            st.markdown("### Archive")
            archive_bytes = storage.build_episode_archive_bytes(ep_id)
            if archive_bytes:
                st.download_button(
                    "Download Archive (.zip)",
                    data=archive_bytes,
                    file_name=f"{ep_id}_bundle.zip",
                    mime="application/zip",
                    key=f"dl_zip_{ep_id}",
                )
            else:
                st.info("Archive unavailable.")

            if st.button("Close Export Panel"):
                del st.session_state["library_export"]
                st.rerun()

    st.markdown("---")
    st.markdown("### Visual Pipeline, Post-Review")
    st.caption("Generate image prompts after the story is saved, then batch the whole episode through Draw Things so you can review and keep the best candidates afterward.")

    selected_episode = None
    if "library_export" in st.session_state:
        selected_episode = storage.load_episode(st.session_state["library_export"])
    elif filtered:
        selected_episode = storage.load_episode(filtered[0]["id"])

    if selected_episode:
        _render_library_visual_workflow(
            storage=storage,
            prompt_gen=prompt_gen,
            dt_client=dt_client,
            story_gen=story_gen,
            model=model,
            temperature=temperature,
            episode=selected_episode,
        )
    
    # Folder structure info
    st.markdown("---")
    with st.expander("Recommended Folder Structure for GitHub Repo", expanded=False):
        st.markdown("""
```
gravedancer-to-general/
├── episodes/
│   ├── episode-20260119-120000-the-hunting-of-vex/
│   │   ├── metadata.json
│   │   ├── story.md
│   │   └── prompts.json
│   ├── episode-20260126-120000-ash-and-bone/
│   │   ├── metadata.json
│   │   ├── story.md
│   │   └── prompts.json
│   └── ...
├── images/
│   ├── episode-001/
│   │   ├── day-01-scene-01-wide.png
│   │   ├── day-01-scene-01-medium.png
│   │   ├── day-01-scene-01-closeup.png
│   │   └── ...
│   └── ...
├── prompts/
│   ├── episode-001-prompts.txt
│   ├── episode-001-prompts.json
│   └── ...
├── videos/
│   ├── episode-001/
│   │   ├── day-01-scene-01.mp4
│   │   ├── day-01-scene-02.mp4
│   │   └── ...
│   └── ...
├── README.md
└── requirements.txt
```

**Workflow:**
1. Generate episode in **Creator** tab
2. Generate visual prompts in **Prompts** tab
3. Run prompts through **DrawThings** with **Flux.2 Klein 4b**
4. Save keyframe images to `images/episode-XXX/`
5. Run keyframes through **Wan 2.2 High Noise 6-bit SVDQuant** in DrawThings
6. Save videos to `videos/episode-XXX/`
7. Commit everything to your GitHub repo
        """)


def _render_library_visual_workflow(storage, prompt_gen, dt_client, story_gen, model, temperature, episode):
    """Post-review visual workflow for prompt generation and candidate selection."""
    ep_id = episode["metadata"].get("id")
    story = episode.get("story", "")
    days = story_gen.parse_days(story)
    if not days:
        st.info("No day structure found for this episode.")
        return

    dt_ok = dt_client.check_connection()
    if not dt_ok:
        st.warning("Draw Things is offline. Prompt generation can still run, but image rendering will be skipped.")

    max_scenes = st.slider("Scene candidates per day", min_value=1, max_value=4, value=2, key=f"lib_viz_max_{ep_id}")
    aspect_ratio = st.selectbox("Aspect ratio", ["16:9", "21:9", "4:3", "3:2", "1:1"], index=0, key=f"lib_viz_ar_{ep_id}")
    temperature_prompt = st.slider("Prompt temperature", min_value=0.1, max_value=1.0, value=float(temperature), step=0.1, key=f"lib_viz_temp_{ep_id}")
    image_variants = st.slider("Image generations per prompt", min_value=1, max_value=5, value=3, key=f"lib_viz_imgs_{ep_id}")

    existing_prompt_sets = get_episode_prompt_sets(episode)
    if st.button("Run Visual Pipeline For Episode", key=f"lib_viz_run_{ep_id}", type="primary"):
        merged = list(existing_prompt_sets)
        episode_results = []
        for day in days:
            day_scenes = prompt_gen.extract_scenes(
                day["content"],
                max_scenes_per_day=max_scenes,
                day_number=day["number"],
            )
            if not day_scenes:
                continue
            dwc = f"({day['word_count']:,}) " if day.get('word_count') else ""
            st.markdown(f"#### {dwc}Day {day['number']}: {day['title']}")
            results = prompt_gen.generate_batch_prompts(
                scenes=day_scenes,
                model=model,
                aspect_ratio=aspect_ratio,
                temperature=temperature_prompt,
                system_prompt=st.session_state["visual_sys_prompt"],
            )
            episode_results.extend(results)
            for result in results:
                if "error" in result:
                    st.error(result["error"])
                    continue
                merged.append({
                    "day": day["number"],
                    "prompt_type": "Flux.2 Klein 4b - DrawThings",
                    "aspect_ratio": aspect_ratio,
                    "wide": result.get("wide", ""),
                    "medium": result.get("medium", ""),
                    "closeup": result.get("closeup", ""),
                    "dramatic": result.get("dramatic", ""),
                    "alternate": result.get("alternate", ""),
                    "negative_prompt": result.get("negative_prompt", ""),
                    "raw_response": result.get("raw_response", ""),
                })

                if dt_ok:
                    chosen_prompt = result.get("medium") or result.get("wide") or result.get("dramatic") or result.get("closeup") or result.get("alternate") or ""
                    if chosen_prompt:
                        for variant in range(1, image_variants + 1):
                            try:
                                img = dt_client.generate_image(
                                    prompt=chosen_prompt,
                                    negative_prompt=result.get("negative_prompt", ""),
                                    seed=-1 if variant == 1 else variant,
                                )
                                rel = storage.save_image(
                                    ep_id,
                                    day=day["number"],
                                    shot=f"scene-{len(episode_results):02d}-candidate",
                                    image_bytes=img,
                                    variant=variant,
                                )
                                st.image(img, caption=f"Saved {Path(rel).name}", use_container_width=True)
                            except Exception as e:
                                st.error(f"Render failed for day {day['number']} candidate {variant}: {e}")
        # The Library owns only the legacy scene prompts. Preserve banner and
        # chapter prompts created in the Viewer.
        prompt_payload = dict((storage.load_episode(ep_id) or {}).get("prompts") or {})
        prompt_payload.update({"scenes": merged, "aspect_ratio": aspect_ratio})
        storage.update_episode(episode_id=ep_id, prompts=prompt_payload)
        st.success("Visual pipeline completed for the episode.")
