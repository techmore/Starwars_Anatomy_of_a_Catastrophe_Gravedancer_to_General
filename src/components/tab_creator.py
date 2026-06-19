"""Tab 1: Episode Creator / Story Generator."""

import streamlit as st
from src.utils.story_generator import StoryGenerator
from src.utils.storage import EpisodeStorage


def render_creator_tab(
    story_gen: StoryGenerator,
    storage: EpisodeStorage,
    model: str,
    temperature: float,
    ollama_url: str,
    system_prompt: str
):
    """Render the episode creator tab."""
    
    st.markdown("## Forge a New Episode")
    st.markdown('<div class="blood-accent">Channel the Gravedancer. Shape the hunt. Define the Jedi\'s doom — or their escape.</div>', unsafe_allow_html=True)
    
    # Auto-suggest title based on inputs (optional enhancement)
    col1, col2 = st.columns([2, 1])
    
    with col1:
        title = st.text_input(
            "Episode Title",
            value=st.session_state.get("ep_title", ""),
            placeholder="e.g., The Hunting of Jedi Vex'arii",
            key="ep_title_input"
        )
    
    with col2:
        num_days = st.slider(
            "Number of Days",
            min_value=3,
            max_value=8,
            value=st.session_state.get("ep_days", 5),
            key="ep_days_slider"
        )
    
    st.markdown("---")
    st.markdown("### Jedi Target")
    
    jedi_col1, jedi_col2 = st.columns(2)
    
    with jedi_col1:
        jedi_name = st.text_input("Name", placeholder="e.g., Vex'arii", key="jedi_name")
        jedi_species = st.text_input("Species", placeholder="e.g., Miraluka, Twi'lek, Zabrak, custom", key="jedi_species")
        jedi_rank = st.text_input("Rank", placeholder="e.g., Jedi Knight, Jedi Master, Padawan", key="jedi_rank")
    
    with jedi_col2:
        jedi_saber = st.text_input("Lightsaber Color", placeholder="e.g., Viridian, amber, white, dual-bladed", key="jedi_saber")
        jedi_personality = st.text_area(
            "Personality / Ability",
            placeholder="e.g., Stoic philosopher, master of Form IV, hunted Separatists before Order 66",
            height=100,
            key="jedi_personality"
        )
        jedi_target = st.text_area(
            "Why Targeted",
            placeholder="e.g., Killed Kaleesh refugees, blocked Separatist supply line, refused Sith bribes",
            height=80,
            key="jedi_target"
        )
    
    st.markdown("---")
    st.markdown("### Setting & Tone")
    
    setting_col1, setting_col2 = st.columns([1, 1])
    
    with setting_col1:
        setting = st.text_input(
            "Setting / Planet",
            value=st.session_state.get("ep_setting", ""),
            placeholder="e.g., Ruins of Jabiim, Kalee bone deserts, Outer Rim mining colony",
            key="ep_setting_input"
        )
    
    with setting_col2:
        tone_focus = st.multiselect(
            "Tone / Focus",
            options=[
                "More battles and skirmishes",
                "Psychological horror",
                "Action-heavy combat",
                "Transformation focus (Qymaen → Grievous)",
                "Gravedancer origin elements",
                "Droid engagement focus",
                "Jedi POV chapters",
                "Traps and ambushes",
                "Honor and ritual",
                "Mystical / Force elements",
                "Political intrigue",
                "Survival horror",
                "Narrow escapes",
                "Ongoing pursuit (no kill)"
            ],
            default=st.session_state.get("ep_tone", []),
            key="ep_tone_multiselect"
        )
    
    additional = st.text_area(
        "Additional Instructions",
        value=st.session_state.get("ep_additional", ""),
        placeholder="Any specific beats, plot points, or creative direction...",
        height=100,
        key="ep_additional_input"
    )
    
    st.markdown("---")
    
    # Generate button
    col_gen1, col_gen2, col_gen3 = st.columns([1, 2, 1])
    with col_gen2:
        generate_clicked = st.button("GENERATE STORY", type="primary", use_container_width=True)
    
    if generate_clicked:
        if not title:
            st.error("Episode title is required.")
            return
        
        if not setting:
            st.warning("Consider specifying a setting for richer atmosphere.")
        
        # Build inputs
        jedi_details = {
            "name": jedi_name,
            "species": jedi_species,
            "rank": jedi_rank,
            "lightsaber_color": jedi_saber,
            "personality": jedi_personality,
            "why_targeted": jedi_target
        }
        
        # Progress
        progress_bar = st.progress(0)
        status = st.empty()
        
        try:
            status.markdown("**⏳ Summoning the Kaleesh spirits... Ollama is generating your episode.**")
            progress_bar.progress(20)
            
            # Generate with streaming
            full_response = ""
            response_container = st.empty()
            
            for chunk in story_gen.generate_story_stream(
                model=model,
                title=title,
                num_days=num_days,
                jedi_details=jedi_details,
                setting=setting,
                tone_focus=tone_focus,
                additional_instructions=additional,
                temperature=temperature,
                system_prompt=system_prompt
            ):
                full_response += chunk
                response_container.markdown(full_response + "▌")
                progress_bar.progress(min(90, 20 + len(full_response) // 50))
            
            response_container.markdown(full_response)
            progress_bar.progress(100)
            status.markdown("**✓ Episode forged. The Gravedancer awaits your review.**")
            
            # Save to session state
            st.session_state["current_story"] = full_response
            st.session_state["current_metadata"] = {
                "title": title,
                "num_days": num_days,
                "jedi_name": jedi_name,
                "jedi_species": jedi_species,
                "jedi_rank": jedi_rank,
                "jedi_lightsaber_color": jedi_saber,
                "jedi_personality": jedi_personality,
                "jedi_why_targeted": jedi_target,
                "setting": setting,
                "tone_focus": tone_focus,
                "additional_instructions": additional,
                "model": model,
                "temperature": temperature
            }
            
            # Display with day sections
            st.markdown("---")
            st.markdown("## Generated Episode")
            
            days = story_gen.parse_days(full_response)
            for day in days:
                with st.expander(f"DAY {day['number']}: {day['title']}", expanded=False):
                    st.markdown(day['content'])
            
            # Save button
            if st.button("Save Episode to Library", type="primary"):
                episode_id = storage.save_episode(
                    title=title,
                    story=full_response,
                    metadata=st.session_state["current_metadata"]
                )
                st.success(f"Episode saved: `{episode_id}`")
                st.rerun()
        
        except Exception as e:
            st.error(f"Generation failed: {e}")
            progress_bar.empty()
            status.empty()
