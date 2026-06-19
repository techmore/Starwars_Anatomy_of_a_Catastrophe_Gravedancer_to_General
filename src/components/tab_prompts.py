"""Tab 3: Scene Prompts & Visual Pipeline for Draw Things + Flux.2 Klein 4b + Wan 2.2."""

import streamlit as st
import json
from typing import List, Dict, Any
from src.utils.prompt_generator import PromptGenerator
from src.utils.story_generator import StoryGenerator
from src.utils.storage import EpisodeStorage


def render_prompts_tab(
    context,
    visual_system_prompt: str
):
    """Render the scene prompts/visual pipeline tab."""
    prompt_gen: PromptGenerator = context.prompt_gen
    story_gen: StoryGenerator = context.story_gen
    storage: EpisodeStorage = context.storage
    model: str = context.model
    temperature: float = context.temperature
    
    st.markdown("## Scene Prompts & Visual Pipeline")
    st.markdown('<div class="blood-accent">Extract key scenes. Generate Draw Things + Flux.2 Klein 4b image prompts. Generate Wan 2.2 High Noise 6-bit SVDQuant video prompts.</div>', unsafe_allow_html=True)
    
    # Load episode
    episodes = storage.list_episodes()
    
    if not episodes:
        st.info("No episodes available. Generate one in the Creator tab.")
        return
    
    ep_options = {f"{ep['title']} ({ep['created_at'][:10]})": ep['id'] for ep in episodes}
    selected_label = st.selectbox("Select Episode", list(ep_options.keys()), key="prompts_select")
    selected_id = ep_options[selected_label]
    
    episode = storage.load_episode(selected_id)
    if not episode:
        st.error("Failed to load episode.")
        return
    
    story = episode["story"]
    metadata = episode["metadata"]
    
    st.markdown("---")
    
    # Settings
    settings_col1, settings_col2, settings_col3 = st.columns(3)
    with settings_col1:
        aspect_ratio = st.selectbox(
            "Aspect Ratio",
            ["16:9", "21:9", "4:3", "3:2", "1:1", "9:16", "2:3"],
            index=0,
            key="prompts_aspect"
        )
    with settings_col2:
        max_scenes = st.number_input(
            "Max Scenes per Day",
            min_value=1,
            max_value=4,
            value=2,
            key="prompts_max_scenes"
        )
    with settings_col3:
        use_existing = st.checkbox(
            "Use Existing Prompts (if saved)",
            value=False,
            key="prompts_use_existing"
        )
    
    st.markdown("---")
    
    # Auto-extract scenes
    if st.button("Extract Key Scenes", type="primary"):
        with st.spinner("Analyzing story for visual potential..."):
            scenes = prompt_gen.extract_scenes(story, max_scenes_per_day=max_scenes)
            st.session_state["extracted_scenes"] = scenes
            st.success(f"Extracted {len(scenes)} key scenes.")
    
    scenes = st.session_state.get("extracted_scenes", [])
    
    if not scenes:
        st.info("Click 'Extract Key Scenes' to begin.")
        return
    
    # Manual selection
    st.markdown("### Selected Scenes")
    selected_scenes = []
    
    for i, scene in enumerate(scenes):
        with st.expander(
            f"Day {scene['day']} - Scene {i+1} (Visual Score: {scene['visual_score']})",
            expanded=False
        ):
            st.markdown(f"```\n{scene['text']}\n```")
            if st.checkbox(f"Include this scene", value=True, key=f"scene_select_{i}"):
                selected_scenes.append(scene)
    
    st.markdown("---")
    
    if not selected_scenes:
        st.warning("Select at least one scene to generate prompts.")
        return
    
    st.markdown(f"**{len(selected_scenes)} scene(s) selected for prompt generation.**")
    
    # Generate prompts
    col_gen, col_batch = st.columns(2)
    with col_gen:
        generate_clicked = st.button("Generate All Prompts", type="primary")
    with col_batch:
        if st.button("Generate Batch JSON"):
            generate_clicked = True
            st.session_state["batch_json"] = True
    
    if generate_clicked:
        with st.spinner(f"Generating prompts for {len(selected_scenes)} scenes..."):
            try:
                results = prompt_gen.generate_batch_prompts(
                    scenes=selected_scenes,
                    model=model,
                    aspect_ratio=aspect_ratio,
                    temperature=temperature,
                    system_prompt=visual_system_prompt
                )
                st.session_state["generated_prompts"] = results
                
                # Save to episode
                storage.update_episode(
                    episode_id=selected_id,
                    prompts={
                        "scenes": results,
                        "aspect_ratio": aspect_ratio
                    }
                )
                st.success("Prompts generated and saved.")
            except Exception as e:
                st.error(f"Generation failed: {e}")
                return
    
    results = st.session_state.get("generated_prompts", [])
    
    if not results:
        return
    
    # Batch JSON export
    if st.session_state.get("batch_json"):
        st.markdown("### Batch JSON Export")
        st.json(results)
        st.download_button(
            "Download Prompts JSON",
            data=json.dumps(results, indent=2),
            file_name=f"{selected_id}_prompts.json",
            mime="application/json"
        )
        st.session_state["batch_json"] = False
    
    st.markdown("---")
    st.markdown("### Generated Prompts")
    
    for i, result in enumerate(results):
        if "error" in result:
            st.error(f"Scene {i+1} failed: {result['error']}")
            continue
        
        with st.expander(f"Day {result['day']} - Scene {i+1} Prompts", expanded=False):
            # Scene text
            st.markdown("**Scene Text:**")
            st.markdown(f"```\n{result.get('scene_text', '')}\n```")
            
            # Image prompts
            st.markdown("### Draw Things + Flux.2 Klein 4b Image Prompts")
            
            img_tabs = st.tabs(["Wide", "Medium", "Close-up", "Dramatic", "Alternate"])
            
            with img_tabs[0]:
                st.markdown("**Wide / Establishing Shot**")
                st.code(result.get("wide", ""), language="text")
            with img_tabs[1]:
                st.markdown("**Medium / Action Shot**")
                st.code(result.get("medium", ""), language="text")
            with img_tabs[2]:
                st.markdown("**Close-up / Detail Shot**")
                st.code(result.get("closeup", ""), language="text")
            with img_tabs[3]:
                st.markdown("**Dramatic / Low Angle Shot**")
                st.code(result.get("dramatic", ""), language="text")
            with img_tabs[4]:
                st.markdown("**Alternate Style**")
                st.code(result.get("alternate", ""), language="text")
            
            st.markdown("**Negative Prompt (Draw Things):**")
            st.code(result.get("negative_prompt", ""), language="text")
            
            if result.get("drawthings_settings"):
                st.markdown("**Draw Things Settings (Flux.2 Klein 4b):**")
                st.code(result.get("drawthings_settings", ""), language="text")
            
            st.markdown("---")
            
            # Video prompts
            st.markdown("### Wan 2.2 High Noise 6-bit SVDQuant Video Prompt")
            
            if result.get("video_keyframe"):
                st.markdown("**Keyframe:**")
                st.code(result.get("video_keyframe", ""), language="text")
            
            if result.get("video_motion"):
                st.markdown("**Motion Description:**")
                st.code(result.get("video_motion", ""), language="text")
            
            if result.get("video_camera"):
                st.markdown("**Camera:**")
                st.code(result.get("video_camera", ""), language="text")
            
            if result.get("video_wan_prompt"):
                st.markdown("**Wan 2.2 Prompt:**")
                st.code(result.get("video_wan_prompt", ""), language="text")
            
            if result.get("video_settings"):
                st.markdown("**Draw Things Wan 2.2 Settings:**")
                st.code(result.get("video_settings", ""), language="text")
            
            # Raw response
            with st.expander("Raw LLM Response"):
                st.text(result.get("raw_response", ""))
    
    # Draw Things workflow notes
    st.markdown("---")
    with st.expander("Draw Things + Flux.2 Klein 4b + Wan 2.2 Workflow Notes", expanded=False):
        st.markdown("""
### Draw Things Setup

**Model 1: Flux.2 Klein 4b (Image Generation)**
1. Open Draw Things app
2. Load model: `flux.2-klein-4b` (fp8 or bf16 variant)
3. Set aspect ratio (16:9 = 1344x768 recommended for cinematic)
4. Steps: 20-30
5. CFG Scale: 2.0-3.0 (Flux prefers low CFG)
6. Sampler: Euler a
7. Paste your prompt and generate
8. Save keyframe for Wan 2.2 I2V

**Model 2: Wan 2.2 High Noise 6-bit SVDQuant (Image-to-Video)**
1. Load Wan 2.2 High Noise 6-bit SVDQuant I2V model in Draw Things
2. Use the keyframe image from Flux.2 Klein 4b as input
3. Paste the Wan 2.2 motion prompt
4. Set resolution: 480x832 (portrait) or 832x480 (landscape)
5. FPS: 24
6. Steps: 25
7. CFG: 7.0
8. Motion Bucket: 127 (adjust 1-255 for more/less motion)
9. Generate 3-5 second clip
10. Save and combine clips in your video editor

### Tips
- Use the **Wide/Establishing** prompt for opening shots
- Use the **Medium/Action** prompt for combat scenes (best for Wan 2.2 keyframes)
- Use the **Close-up** prompt for emotional beats
- Generate multiple variations and select the best
- Fix the seed for consistency across clip variations
- Export frames at 24fps for smooth playback
        """)
    
    # Export options
    st.markdown("---")
    st.markdown("### Export")
    
    export_col1, export_col2 = st.columns(2)
    
    with export_col1:
        # Text export
        text_export = ""
        for i, result in enumerate(results):
            if "error" in result:
                continue
            text_export += f"\n{'='*60}\n"
            text_export += f"DAY {result['day']} - SCENE {i+1}\n"
            text_export += f"{'='*60}\n\n"
            text_export += f"SCENE TEXT:\n{result.get('scene_text', '')}\n\n"
            text_export += f"WIDE/ESTABLISHING:\n{result.get('wide', '')}\n\n"
            text_export += f"MEDIUM/ACTION:\n{result.get('medium', '')}\n\n"
            text_export += f"CLOSE-UP/DETAIL:\n{result.get('closeup', '')}\n\n"
            text_export += f"DRAMATIC/LOW ANGLE:\n{result.get('dramatic', '')}\n\n"
            text_export += f"ALTERNATE STYLE:\n{result.get('alternate', '')}\n\n"
            text_export += f"NEGATIVE PROMPT:\n{result.get('negative_prompt', '')}\n\n"
            text_export += f"--- WAN 2.2 VIDEO ---\n\n"
            text_export += f"KEYFRAME:\n{result.get('video_keyframe', '')}\n\n"
            text_export += f"MOTION:\n{result.get('video_motion', '')}\n\n"
            text_export += f"CAMERA:\n{result.get('video_camera', '')}\n\n"
            text_export += f"WAN PROMPT:\n{result.get('video_wan_prompt', '')}\n\n"
        
        st.download_button(
            "Download Prompts (.txt)",
            data=text_export,
            file_name=f"{selected_id}_prompts.txt",
            mime="text/plain"
        )
    
    with export_col2:
        st.download_button(
            "Download Prompts (JSON)",
            data=json.dumps(results, indent=2),
            file_name=f"{selected_id}_prompts.json",
            mime="application/json"
        )
