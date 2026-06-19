"""Tab 2: Story Viewer & Editor."""

import streamlit as st
from src.utils.story_generator import StoryGenerator
from src.utils.storage import EpisodeStorage


def render_viewer_tab(
    story_gen: StoryGenerator,
    storage: EpisodeStorage
):
    """Render the story viewer/editor tab."""
    
    st.markdown("## Story Viewer & Editor")
    st.markdown('<div class="blood-accent">Review the hunt. Refine the prose. Reshape the narrative.</div>', unsafe_allow_html=True)
    
    # Episode selector
    episodes = storage.list_episodes()
    
    if not episodes:
        st.info("No episodes saved yet. Generate one in the Creator tab.")
        return
    
    ep_options = {f"{ep['title']} ({ep['created_at'][:10]})": ep['id'] for ep in episodes}
    selected_label = st.selectbox("Select Episode", list(ep_options.keys()), key="viewer_select")
    selected_id = ep_options[selected_label]
    
    # Load episode
    episode = storage.load_episode(selected_id)
    
    if not episode:
        st.error("Failed to load episode.")
        return
    
    metadata = episode["metadata"]
    story = episode["story"]
    
    # Stats
    stats = story_gen.get_stats(story)
    
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    with stat_col1:
        st.metric("Days", stats["num_days"])
    with stat_col2:
        st.metric("Words", f"{stats['word_count']:,}")
    with stat_col3:
        st.metric("Reading Time", f"{stats['reading_time_minutes']} min")
    with stat_col4:
        st.metric("Jedi Target", metadata.get("jedi_name", "Unknown"))
    
    st.markdown("---")
    
    # Metadata display
    with st.expander("Episode Metadata", expanded=False):
        meta_col1, meta_col2 = st.columns(2)
        with meta_col1:
            st.markdown(f"**Title:** {metadata.get('title', 'N/A')}")
            st.markdown(f"**Jedi:** {metadata.get('jedi_name', 'N/A')}")
            st.markdown(f"**Species:** {metadata.get('jedi_species', 'N/A')}")
            st.markdown(f"**Rank:** {metadata.get('jedi_rank', 'N/A')}")
        with meta_col2:
            st.markdown(f"**Setting:** {metadata.get('setting', 'N/A')}")
            st.markdown(f"**Tone:** {', '.join(metadata.get('tone_focus', []))}")
            st.markdown(f"**Model:** {metadata.get('model', 'N/A')}")
    
    st.markdown("---")
    
    # Editor mode toggle
    edit_mode = st.toggle("Edit Mode", value=False, key="viewer_edit_toggle")
    
    if edit_mode:
        st.markdown("### Edit Story")
        edited_story = st.text_area(
            "Story Markdown",
            value=story,
            height=600,
            key="viewer_story_editor"
        )
        
        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("Save Changes", type="primary"):
                # Strip the metadata header (first 8 lines or so) and save raw story
                # Find where the story actually starts
                lines = edited_story.split("\n")
                story_start = 0
                for i, line in enumerate(lines):
                    if line.strip() == "---":
                        story_start = i + 1
                        break
                raw_story = "\n".join(lines[story_start:]).strip()
                
                storage.update_episode(
                    episode_id=selected_id,
                    story=raw_story,
                    metadata={"updated_at": None}
                )
                st.success("Episode updated.")
                st.rerun()
        with col_cancel:
            if st.button("Cancel"):
                st.rerun()
    else:
        # Display days
        st.markdown("### Story Content")
        days = story_gen.parse_days(story)
        
        for day in days:
            with st.expander(f"DAY {day['number']}: {day['title']}", expanded=True):
                st.markdown(day['content'])
    
    st.markdown("---")
    
    # Delete option
    with st.expander("Danger Zone", expanded=False):
        st.warning("Deleting an episode is permanent.")
        if st.button("Delete Episode", type="secondary"):
            if storage.delete_episode(selected_id):
                st.success("Episode deleted.")
                st.rerun()
            else:
                st.error("Failed to delete episode.")