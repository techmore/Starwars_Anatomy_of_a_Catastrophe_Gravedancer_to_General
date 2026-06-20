"""Tab 4: Episode Library & Export."""

import streamlit as st
import json
from src.utils.storage import EpisodeStorage
from src.utils.session_state import (
    build_episode_full_json_export,
    get_episode_target_jedi_name,
    render_episode_prompt_archive_summary,
    summarize_episode_collection,
)


def render_library_tab(context):
    """Render the episode library/export tab."""
    storage: EpisodeStorage = context.storage
    
    st.markdown("## Episode Library & Export")
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
                                st.session_state["library_selected"] = ep['id']
                                st.success(f"Loaded: {ep['title']}")
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
                # Markdown export
                st.download_button(
                    "Download Story (.md)",
                    data=episode["story"],
                    file_name=f"{ep_id}_story.md",
                    mime="text/markdown",
                    key=f"dl_md_{ep_id}"
                )
            
            with exp_col2:
                # JSON export
                json_data = build_episode_full_json_export(episode)
                st.download_button(
                    "Download Full JSON",
                    data=json.dumps(json_data, indent=2),
                    file_name=f"{ep_id}_full.json",
                    mime="application/json",
                    key=f"dl_json_{ep_id}"
                )
            
            with exp_col3:
                # Prompts export
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
