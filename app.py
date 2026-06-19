"""Main Streamlit app: Gravedancer to General - Anatomy of a Catastrophe.

Clean, minimal design. Staged workflow: Story → Art → Video.
"""

import streamlit as st
from src.utils.ollama_client import get_ollama_client
from src.utils.storage import get_storage
from src.utils.story_generator import StoryGenerator
from src.utils.prompt_generator import PromptGenerator
from src.utils.models import (
    MODEL_CATALOG, STORY_RECOMMENDED, DEFAULT_MODEL,
    get_model_info, sort_models_for_ui, get_recommended_default,
    format_model_label, get_install_commands
)
from src.prompts.system_prompts import STORY_GENERATION_SYSTEM_PROMPT, VISUAL_PROMPT_SYSTEM_PROMPT
from src.components.theme import CUSTOM_CSS


# Page config
st.set_page_config(
    page_title="Gravedancer to General",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply theme
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables."""
    defaults = {
        "current_episode_id": None,
        "current_story": "",
        "current_metadata": {},
        "current_prompts": [],
        "ollama_url": "http://localhost:11434",
        "model": DEFAULT_MODEL,  # Will be replaced with a story-friendly model if available
        "temperature": 0.8,
        "storage_path": "episodes",
        "story_sys_prompt": STORY_GENERATION_SYSTEM_PROMPT,
        "visual_sys_prompt": VISUAL_PROMPT_SYSTEM_PROMPT,
        "show_manual_form_state": False,
        "auto_generate": False,
        "jedi_suggestions": []
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_sidebar():
    """Render the sidebar with configuration."""
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        
        # Ollama connection
        st.markdown("**Ollama**")
        ollama_url = st.text_input(
            "URL",
            value=st.session_state["ollama_url"],
            key="ollama_url_input",
            label_visibility="collapsed"
        )
        st.session_state["ollama_url"] = ollama_url
        
        ollama = get_ollama_client(ollama_url)
        
        if ollama.check_connection():
            st.markdown("✓ Connected")
            available_models = ollama.list_models()
            
            if available_models:
                # Sort: story-friendly first, then by quality
                sorted_models = sort_models_for_ui(available_models)
                
                # Build display labels with quality indicators
                display_labels = [format_model_label(m) for m in sorted_models]
                label_to_model = dict(zip(display_labels, sorted_models))
                
                # Find current selection in sorted list
                current = st.session_state.get("model", "")
                if current in sorted_models:
                    current_label = format_model_label(current)
                else:
                    # Pick a recommended default if current is missing
                    recommended = get_recommended_default(available_models)
                    current_label = format_model_label(recommended)
                    st.session_state["model"] = recommended
                
                try:
                    current_index = display_labels.index(current_label)
                except ValueError:
                    current_index = 0
                
                selected_label = st.selectbox(
                    "Model",
                    options=display_labels,
                    index=current_index,
                    key="model_select_display",
                    label_visibility="collapsed",
                    help="★ = best for long-form stories, ● = good, ○ = ok"
                )
                st.session_state["model"] = label_to_model[selected_label]
                model = st.session_state["model"]
                
                # Show model details
                info = get_model_info(model)
                with st.expander("Model info", expanded=False):
                    st.caption(f"**Quality:** {info.get('quality', '?').title()}")
                    st.caption(f"**RAM:** {info.get('ram_gb', '?')} GB")
                    st.caption(f"**Strengths:** {', '.join(info.get('strengths', ['unknown']))}")
            else:
                st.warning("No models installed.")
                with st.expander("Install a model", expanded=True):
                    st.code(get_install_commands(), language="bash")
        else:
            st.error("✗ Not reachable. Start with: `ollama serve`")
        
        st.markdown("---")
        
        # Temperature
        st.markdown("**Creativity**")
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=2.0,
            value=st.session_state["temperature"],
            step=0.1,
            key="temp_slider",
            label_visibility="collapsed"
        )
        st.session_state["temperature"] = temperature
        
        st.markdown("---")
        
        # Storage
        st.markdown("**Storage**")
        storage_path = st.text_input(
            "Episodes folder",
            value=st.session_state["storage_path"],
            key="storage_path_input",
            label_visibility="collapsed"
        )
        st.session_state["storage_path"] = storage_path
        
        st.markdown("---")
        
        # Episode library (compact)
        st.markdown("**Library**")
        storage = get_storage(storage_path)
        episodes = storage.list_episodes()
        
        if episodes:
            for ep in episodes[:5]:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"_{ep['title'][:25]}_")
                with col2:
                    if st.button("×", key=f"side_del_{ep['id']}"):
                        storage.delete_episode(ep['id'])
                        st.rerun()
        else:
            st.markdown("_No episodes yet_")
        
        st.markdown("---")
        
        # Advanced settings (collapsed)
        with st.expander("Advanced", expanded=False):
            st.markdown("**System Prompts**")
            story_sys = st.text_area(
                "Story prompt",
                value=st.session_state["story_sys_prompt"],
                height=200,
                key="story_sys_editor"
            )
            st.session_state["story_sys_prompt"] = story_sys
            
            visual_sys = st.text_area(
                "Visual prompt",
                value=st.session_state["visual_sys_prompt"],
                height=200,
                key="visual_sys_editor"
            )
            st.session_state["visual_sys_prompt"] = visual_sys
    
    return ollama_url, st.session_state["model"], st.session_state["temperature"]


def get_used_jedi_names(storage) -> list:
    """Get all Jedi names from saved episodes."""
    episodes = storage.list_episodes()
    names = []
    for ep in episodes:
        jedi_name = ep.get("jedi_name", "").strip()
        if jedi_name and jedi_name.lower() != "unknown":
            names.append(jedi_name)
    return names


def build_jedi_suggestion_prompt(used_names: list, setting: str = "", tone: list = None) -> str:
    """Build prompt for Jedi target suggestion."""
    exclusion = ""
    if used_names:
        exclusion = f"""

**ALREADY USED JEDI NAMES (DO NOT REPEAT OR CREATE SIMILAR VARIANTS):**
{', '.join(used_names)}

You must create completely original names that are distinct from all of the above. Do not reuse any name, nickname, species name, or obvious variation."""
    
    setting_context = ""
    if setting.strip():
        setting_context = f"""

**SETTING/PACING HINT:** {setting}"""
    
    tone_context = ""
    if tone:
        tone_context = f"""

**TONE/FOCUS HINT:** {', '.join(tone)}"""
    
    return f"""Generate 3 completely original Jedi character concepts for a "Gravedancer to General: Anatomy of a Catastrophe" episode. These are unknown Jedi being hunted by the early Grievous / Qymaen jai Sheelal in the pre-Clone Wars era.

Each Jedi must be:
- An original character (NOT from Star Wars canon, legends, or existing media)
- Diverse in species (avoid human-only, consider Miraluka, Twi'lek, Zabrak, Kel Dor, Nautolan, Cerean, Togruta, Weequay, Nikto, Devaronian, etc.)
- Have a unique lightsaber color (not just blue/green — consider amber, viridian, silver, yellow, orange, cyan, white, magenta)
- Have a distinctive fighting style and personality
- Have a clear reason for being targeted by the Gravedancer

**For each Jedi, provide:**
1. **Name:** [Original alien-sounding name]
2. **Species:** [Species]
3. **Rank:** [Jedi Knight / Master / Padawan / etc.]
4. **Lightsaber Color:** [Color]
5. **Personality/Ability:** [1-2 sentences on personality, fighting style, Force abilities]
6. **Why Targeted:** [1 sentence on why the Gravedancer is hunting them]{exclusion}{setting_context}{tone_context}

**OUTPUT FORMAT (strict):**

### JEDI 1
**Name:** [name]
**Species:** [species]
**Rank:** [rank]
**Lightsaber Color:** [color]
**Personality/Ability:** [personality]
**Why Targeted:** [reason]

### JEDI 2
**Name:** [name]
**Species:** [species]
**Rank:** [rank]
**Lightsaber Color:** [color]
**Personality/Ability:** [personality]
**Why Targeted:** [reason]

### JEDI 3
**Name:** [name]
**Species:** [species]
**Rank:** [rank]
**Lightsaber Color:** [color]
**Personality/Ability:** [personality]
**Why Targeted:** [reason]

Make the names sound distinctly alien, evocative, and memorable. Avoid Earth-language roots. Think Star Wars: Kel Dor, Zabrak, Miraluka naming conventions."""


def parse_jedi_suggestions(response: str) -> list:
    """Parse LLM response into list of Jedi suggestion dicts."""
    import re
    jedis = []
    
    # Split by "### JEDI N" markers
    pattern = r"###\s*JEDI\s+(\d+)(.*?)(?=###\s*JEDI\s+\d+|$)"
    matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
    
    for _, content in matches:
        jedi = {}
        # Parse fields
        field_patterns = {
            "name": r"\*\*Name:\*\*\s*(.*?)(?=\n\*\*|\n###|\Z)",
            "species": r"\*\*Species:\*\*\s*(.*?)(?=\n\*\*|\n###|\Z)",
            "rank": r"\*\*Rank:\*\*\s*(.*?)(?=\n\*\*|\n###|\Z)",
            "lightsaber_color": r"\*\*Lightsaber Color:\*\*\s*(.*?)(?=\n\*\*|\n###|\Z)",
            "personality": r"\*\*Personality/Ability:\*\*\s*(.*?)(?=\n\*\*|\n###|\Z)",
            "why_targeted": r"\*\*Why Targeted:\*\*\s*(.*?)(?=\n\*\*|\n###|\Z)"
        }
        
        for key, pattern_str in field_patterns.items():
            match = re.search(pattern_str, content, re.DOTALL)
            if match:
                jedi[key] = match.group(1).strip()
            else:
                jedi[key] = ""
        
        if jedi.get("name"):
            jedis.append(jedi)
    
    return jedis


def build_full_episode_concept_prompt(used_names: list) -> str:
    """Build prompt for generating a complete episode concept (all fields)."""
    # Default target: ~7,500 words per novella episode
    target_words = 7500
    exclusion = ""
    if used_names:
        exclusion = f"""

**ALREADY USED JEDI NAMES (DO NOT REPEAT OR CREATE SIMILAR VARIANTS):**
{', '.join(used_names)}

You must create a completely original name that is distinct from all of the above. Do not reuse any name, nickname, species name, or obvious variation."""
    
    return f"""Generate a complete original episode concept for "Gravedancer to General: Anatomy of a Catastrophe". Fill in every field below with creative, evocative, Star Wars-appropriate content.

This is a pre-Clone Wars era story. The protagonist is Qymaen jai Sheelal (the Gravedancer, evolving toward General Grievous) hunting an original Jedi. The story spans multiple days of pursuit, combat, traps, or psychological warfare.

**STORY LENGTH REQUIREMENT:** This is a self-contained novella. Target **~{target_words:,} words total** (range 6,500-9,000). The reader should be able to sit down for ~35-45 minutes and finish the complete story. Default to 5 days (~1,500 words/day) unless the concept calls for more or fewer.

**For the episode, provide:**

**Episode Title:** [Evocative, two-part Star Wars-style title, e.g., "The Hunting of Jedi Vex'arii", "Ash and Bone on Kalee", "The Gravedancer's Prey"]

**Number of Days:** [Default 5 unless the concept calls for more or fewer. 3 days = compact, intense. 5 days = standard novella pacing (recommended). 7 days = slower, more reflective. Pick what serves the concept best]

**Setting / Planet:** [Specific Star Wars location — Kalee, Jabiim, Florrum, Rattatak, Korriban, or another Outer Rim world. Be specific with terrain features that can sustain multi-day pursuit, ambush, and combat scenes]

**Jedi Name:** [Original alien-sounding name, distinct from Star Wars canon]{exclusion}

**Jedi Species:** [Non-human preferred — Miraluka, Twi'lek, Zabrak, Kel Dor, Nautolan, Cerean, Togruta, Weequay, Nikto, Devaronian, Chiss, Pantoran, etc.]

**Jedi Rank:** [Jedi Knight, Master, Padawan, or Consular]

**Lightsaber Color:** [Non-standard preferred — viridian, amber, silver, yellow, orange, cyan, white, magenta, or dual-bladed]

**Jedi Personality/Ability:** [1-2 sentences — distinctive personality trait, fighting style (Form I-VII or unorthodox), Force ability]

**Why Targeted:** [1 sentence — specific reason the Gravedancer hunts this Jedi. Could be strategic, revenge, or Sith-ordered]

**Tone / Focus (pick 2-4):** [From this list, pick 2-4 that fit: "More battles and skirmishes", "Psychological horror", "Action-heavy combat", "Transformation focus", "Gravedancer origin elements", "Droid engagement focus", "Jedi POV chapters", "Traps and ambushes", "Honor and ritual", "Mystical / Force elements", "Political intrigue", "Survival horror", "Narrow escapes", "Ongoing pursuit (no kill)"]

**OUTPUT FORMAT (strict, use these exact headers):**

TITLE: [title]
DAYS: [number]
SETTING: [setting]
JEDI_NAME: [name]
JEDI_SPECIES: [species]
JEDI_RANK: [rank]
JEDI_SABER: [color]
JEDI_PERSONALITY: [personality]
JEDI_WHY_TARGETED: [reason]
TONE: [comma-separated list of 2-4 tone options]

Be creative. Make the setting and Jedi feel distinct from previous episodes. Ensure the title is evocative and Star Wars-appropriate. Plan the multi-day structure: day 1 sets up, middle days escalate through multiple short scenes per day, final day climaxes."""


def parse_full_episode_concept(response: str) -> dict:
    """Parse LLM response into episode concept dict."""
    import re
    concept = {
        "title": "",
        "days": 5,
        "setting": "",
        "jedi_name": "",
        "jedi_species": "",
        "jedi_rank": "",
        "jedi_saber": "",
        "jedi_personality": "",
        "jedi_target": "",
        "tone": []
    }
    
    field_patterns = {
        "title": r"TITLE:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "days": r"DAYS:\s*(\d+)",
        "setting": r"SETTING:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_name": r"JEDI_NAME:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_species": r"JEDI_SPECIES:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_rank": r"JEDI_RANK:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_saber": r"JEDI_SABER:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_personality": r"JEDI_PERSONALITY:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_target": r"JEDI_WHY_TARGETED:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "tone": r"TONE:\s*(.*?)(?=\n[A-Z_]+:|\Z)"
    }
    
    for key, pattern in field_patterns.items():
        match = re.search(pattern, response, re.DOTALL)
        if match:
            value = match.group(1).strip()
            if key == "days":
                # Clamp to valid range
                try:
                    days = int(value)
                    concept["days"] = max(3, min(8, days))
                except ValueError:
                    concept["days"] = 5
            elif key == "tone":
                # Parse comma-separated tone options
                valid_tones = [
                    "More battles and skirmishes",
                    "Psychological horror",
                    "Action-heavy combat",
                    "Transformation focus",
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
                ]
                tones = [t.strip() for t in value.split(",")]
                concept["tone"] = [t for t in tones if t in valid_tones]
            else:
                concept[key] = value
    
    return concept


def render_story_stage(ollama, model, temperature, storage, story_gen):
    """Stage 1: Story generation."""
    
    st.markdown("# 📖 Story")
    st.markdown("Generate the episode narrative first. Art and video come after.")
    
    st.markdown("---")
    
    # Check if we have a current episode loaded
    if st.session_state.get("current_episode_id"):
        ep_id = st.session_state["current_episode_id"]
        ep = storage.load_episode(ep_id)
        if ep:
            st.markdown(f"**Current episode:** {ep['metadata'].get('title', 'Untitled')}")
            if st.button("← New Episode"):
                st.session_state["current_episode_id"] = None
                st.session_state["current_story"] = ""
                st.session_state["current_metadata"] = {}
                st.rerun()
            st.markdown("---")
    
    # === PRIMARY ACTION: One-click randomize & generate ===
    st.markdown("### Choose your workflow")
    
    col_primary, col_secondary = st.columns([3, 1])
    
    with col_primary:
        randomize_clicked = st.button(
            "🎲 Generate Random Episode",
            type="primary",
            use_container_width=True,
            key="randomize_generate",
            help="LLM picks all parameters and generates the full story in one click"
        )
    
    with col_secondary:
        manual_clicked = st.button(
            "✏️ Build Manually",
            use_container_width=True,
            key="show_manual_form",
            help="Open the manual form to fill in your own parameters"
        )
    
    # Track whether to show the manual form
    if manual_clicked:
        st.session_state["show_manual_form_state"] = not st.session_state["show_manual_form_state"]
    
    show_manual = st.session_state["show_manual_form_state"]
    
    # Status: how many Jedi are already in the library
    used_count = len(get_used_jedi_names(storage))
    if used_count > 0:
        st.caption(f"📚 {used_count} Jedi already hunted — random generation will avoid repeats")
    else:
        st.caption("📚 No saved episodes yet — start your archive with a random episode")
    
    st.markdown("---")
    
    # === RANDOMIZE & GENERATE FLOW ===
    if randomize_clicked:
        # Step 1: Generate concept
        with st.status("🎲 Generating episode concept...", expanded=True) as status_box:
            try:
                used_names = get_used_jedi_names(storage)
                concept_prompt = build_full_episode_concept_prompt(used_names)
                
                st.write("Picking title, setting, and Jedi target...")
                concept_response = ollama.generate(
                    model=model,
                    prompt=concept_prompt,
                    temperature=0.9,
                    max_tokens=800
                )
                
                concept = parse_full_episode_concept(concept_response)
                
                if not concept.get("title") or not concept.get("jedi_name"):
                    status_box.update(label="❌ Failed to parse concept", state="error")
                    with st.expander("Raw response", expanded=False):
                        st.text(concept_response)
                    st.stop()
                
                # Show the generated concept for review
                st.write(f"**Title:** {concept['title']}")
                st.write(f"**Days:** {concept['days']}")
                st.write(f"**Setting:** {concept['setting']}")
                st.write(f"**Jedi:** {concept['jedi_name']} ({concept['jedi_species']}, {concept['jedi_rank']})")
                st.write(f"**Saber:** {concept['jedi_saber']}")
                st.write(f"**Why hunted:** {concept['jedi_target']}")
                if concept.get('tone'):
                    st.write(f"**Tone:** {', '.join(concept['tone'])}")
                
                st.write("Generating full story...")
                
                # Populate session state for the generation step
                st.session_state["story_title"] = concept["title"]
                st.session_state["story_days"] = concept["days"]
                st.session_state["story_setting"] = concept["setting"]
                st.session_state["jedi_name"] = concept["jedi_name"]
                st.session_state["jedi_species"] = concept["jedi_species"]
                st.session_state["jedi_rank"] = concept["jedi_rank"]
                st.session_state["jedi_saber"] = concept["jedi_saber"]
                st.session_state["jedi_personality"] = concept["jedi_personality"]
                st.session_state["jedi_target"] = concept["jedi_target"]
                st.session_state["story_tone"] = concept["tone"]
                st.session_state["auto_generate"] = True
                
                status_box.update(label="✅ Concept ready — generating story...", state="running")
                st.rerun()
                
            except Exception as e:
                status_box.update(label="❌ Failed", state="error")
                st.error(f"Failed: {e}")
                st.stop()
    
    # === MANUAL FORM (only shown when user clicks "Build Manually") ===
    if show_manual:
        st.markdown("### Manual Episode Builder")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            title = st.text_input(
                "Episode title",
                placeholder="e.g., The Hunting of Jedi Vex'arii",
                key="story_title"
            )
        
        with col2:
            num_days = st.slider("Days (5 recommended for ~7,500 word novella)", min_value=3, max_value=8, value=5, key="story_days")
        
        # Jedi details
        with st.expander("🎯 Jedi Target", expanded=True):
            jc1, jc2 = st.columns(2)
            with jc1:
                jedi_name = st.text_input("Name", key="jedi_name", placeholder="e.g., Vex'arii")
                jedi_species = st.text_input("Species", key="jedi_species", placeholder="e.g., Miraluka, Twi'lek")
                jedi_rank = st.text_input("Rank", key="jedi_rank", placeholder="e.g., Jedi Knight")
            with jc2:
                jedi_saber = st.text_input("Lightsaber color", key="jedi_saber", placeholder="e.g., Viridian, amber")
                jedi_personality = st.text_input("Personality/ability", key="jedi_personality", placeholder="e.g., Stoic philosopher, Form IV master")
                jedi_target = st.text_input("Why targeted", key="jedi_target", placeholder="e.g., Blocked Separatist supply line")
        
        # Setting & tone
        col3, col4 = st.columns(2)
        
        with col3:
            setting = st.text_input(
                "🌍 Setting / Planet",
                key="story_setting",
                placeholder="e.g., Ruins of Jabiim, Kalee bone deserts"
            )
        
        with col4:
            tone_focus = st.multiselect(
                "🎭 Tone / Focus",
                options=[
                    "More battles and skirmishes",
                    "Psychological horror",
                    "Action-heavy combat",
                    "Transformation focus",
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
                key="story_tone"
            )
        
        additional = st.text_area(
            "📝 Additional notes (optional)",
            key="story_additional",
            placeholder="Any specific beats or creative direction...",
            height=80
        )
        
        if st.button("📖 Generate Story", type="primary", use_container_width=True, key="manual_generate"):
            st.session_state["auto_generate"] = True
            st.rerun()
    
    st.markdown("---")
    
    # === GENERATION STEP (auto-triggered or manual) ===
    auto_gen = st.session_state.pop("auto_generate", False)
    
    if auto_gen:
        # Pull current values
        title = st.session_state.get("story_title", "")
        num_days = st.session_state.get("story_days", 5)
        setting = st.session_state.get("story_setting", "")
        jedi_name = st.session_state.get("jedi_name", "")
        jedi_species = st.session_state.get("jedi_species", "")
        jedi_rank = st.session_state.get("jedi_rank", "")
        jedi_saber = st.session_state.get("jedi_saber", "")
        jedi_personality = st.session_state.get("jedi_personality", "")
        jedi_target = st.session_state.get("jedi_target", "")
        tone_focus = st.session_state.get("story_tone", [])
        additional = st.session_state.get("story_additional", "")
        
        if not title:
            st.error("Title is required. Use 'Build Manually' to set one.")
            return
        
        jedi_details = {
            "name": jedi_name,
            "species": jedi_species,
            "rank": jedi_rank,
            "lightsaber_color": jedi_saber,
            "personality": jedi_personality,
            "why_targeted": jedi_target
        }
        
        # Hide the buttons/form during generation to keep focus on output
        st.markdown("### 📖 Generating your episode...")
        
        # Use status box so the streaming text is visible alongside
        with st.status(f"📡 Streaming from {model}...", expanded=True) as gen_status:
            try:
                full_response = ""
                story_container = st.empty()
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
                    system_prompt=st.session_state["story_sys_prompt"]
                ):
                    full_response += chunk
                    # Show with cursor while streaming - update both the status and the container
                    gen_status.write(f"📝 {len(full_response):,} chars streamed...")
                    story_container.markdown(full_response + "  \n\n*▌ generating...*")
                
                # Final render without cursor
                story_container.markdown(full_response)
                gen_status.update(label=f"✅ Generated {len(full_response):,} characters", state="complete")
                
                # Save to session
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
                
                # Auto-save episode
                episode_id = storage.save_episode(
                    title=title,
                    story=full_response,
                    metadata=st.session_state["current_metadata"]
                )
                st.session_state["current_episode_id"] = episode_id
                
                st.success(f"✅ Episode saved: **{title}**")
                
                # Next steps
                st.markdown("### Next steps")
                next_col1, next_col2, next_col3 = st.columns(3)
                with next_col1:
                    if st.button("🎨 Generate Art Prompts", use_container_width=True):
                        st.info("Switch to the **Art** tab to generate image prompts for each day.")
                with next_col2:
                    if st.button("📚 View in Library", use_container_width=True):
                        st.info("Switch to the **Library** tab to browse all episodes.")
                with next_col3:
                    if st.button("🔄 Generate Another", use_container_width=True):
                        st.session_state["current_story"] = ""
                        st.session_state["current_episode_id"] = None
                        st.rerun()
                
            except Exception as e:
                st.error(f"❌ Generation failed: {e}")
    
    # Display current story (only when not currently generating)
    story = st.session_state.get("current_story", "")
    if story and not auto_gen:
        st.markdown("---")
        st.markdown(f"## 📖 {st.session_state.get('story_title', 'Episode')}")
        
        # Stats row
        stats = story_gen.get_stats(story)
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        with stat_col1:
            st.metric("Days", stats["num_days"])
        with stat_col2:
            st.metric("Words", f"{stats['word_count']:,}")
        with stat_col3:
            st.metric("Reading", f"{stats['reading_time_minutes']} min")
        with stat_col4:
            st.metric("Jedi", st.session_state.get("jedi_name", "Unknown"))
        
        st.markdown("---")
        
        # Day-by-day view
        days = story_gen.parse_days(story)
        for day in days:
            with st.expander(f"Day {day['number']}: {day['title']}", expanded=False):
                st.markdown(day['content'])
        
        # Action row below story
        st.markdown("---")
        action_col1, action_col2, action_col3 = st.columns(3)
        with action_col1:
            if st.button("🎨 Generate Art", use_container_width=True, key="story_to_art"):
                st.info("Switch to the **Art** tab to generate image prompts.")
        with action_col2:
            if st.button("📚 Library", use_container_width=True, key="story_to_lib"):
                st.info("Switch to the **Library** tab to export.")
        with action_col3:
            if st.button("🔄 New Episode", use_container_width=True, key="story_new"):
                st.session_state["current_story"] = ""
                st.session_state["current_episode_id"] = None
                # Clear form fields
                for key in ["story_title", "story_setting", "jedi_name", "jedi_species", 
                           "jedi_rank", "jedi_saber", "jedi_personality", "jedi_target",
                           "story_additional"]:
                    if key in st.session_state:
                        st.session_state[key] = ""
                st.session_state["story_tone"] = []
                st.rerun()


def render_art_stage(ollama, model, temperature, storage, prompt_gen, story_gen):
    """Stage 2: Art prompts for DrawThings + Flux.2 Klein 4b."""
    
    st.markdown("# 🎨 Art")
    st.markdown("Generate image prompts for each day. Optimized for DrawThings + Flux.2 Klein 4b.")
    
    st.markdown("---")
    
    # Check for current episode
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
    
    # Settings
    col1, col2 = st.columns([1, 3])
    with col1:
        aspect_ratio = st.selectbox(
            "Aspect ratio",
            ["16:9", "21:9", "4:3", "3:2", "1:1", "9:16", "2:3"],
            index=0,
            key="art_aspect"
        )
    
    st.markdown("---")
    
    # Parse days
    days = story_gen.parse_days(story)
    
    if not days:
        st.warning("No days found in story.")
        return
    
    st.markdown("## Generate Art for Each Day")
    
    # Load existing prompts if any
    existing_prompts = episode.get("prompts", {}).get("scenes", []) if episode.get("prompts") else []
    
    for day in days:
        day_num = day['number']
        day_title = day['title']
        day_content = day['content']
        
        with st.expander(f"Day {day_num}: {day_title}", expanded=False):
            st.markdown(f"```\n{day_content[:300]}...\n```")
            
            # Check if prompts exist
            day_prompts = [p for p in existing_prompts if p.get("day") == day_num]
            
            if day_prompts:
                st.markdown(f"**✓ {len(day_prompts)} prompt(s) already generated**")
                
                # Show existing
                for i, prompt_set in enumerate(day_prompts):
                    st.markdown(f"**{prompt_set.get('prompt_type', f'Prompt {i+1}')}**")
                    st.code(prompt_set.get("prompt", ""), language="text")
                
                if st.button(f"Regenerate Day {day_num}", key=f"regen_art_{day_num}"):
                    with st.spinner(f"Generating art for Day {day_num}..."):
                        try:
                            new_prompts = prompt_gen.generate_scene_prompts(
                                scene_text=day_content,
                                day_number=day_num,
                                model=model,
                                aspect_ratio=aspect_ratio,
                                temperature=temperature,
                                system_prompt=st.session_state["visual_sys_prompt"]
                            )
                            
                            # Update storage
                            updated_prompts = [p for p in existing_prompts if p.get("day") != day_num]
                            updated_prompts.append({
                                "day": day_num,
                                "prompt_type": "Flux.2 Klein 4b - DrawThings",
                                "aspect_ratio": aspect_ratio,
                                "wide": new_prompts.get("wide", ""),
                                "medium": new_prompts.get("medium", ""),
                                "closeup": new_prompts.get("closeup", ""),
                                "dramatic": new_prompts.get("dramatic", ""),
                                "alternate": new_prompts.get("alternate", ""),
                                "negative_prompt": new_prompts.get("negative_prompt", ""),
                                "raw_response": new_prompts.get("raw_response", "")
                            })
                            
                            storage.update_episode(
                                episode_id=ep_id,
                                prompts={"scenes": updated_prompts, "aspect_ratio": aspect_ratio}
                            )
                            
                            st.success(f"Regenerated Day {day_num}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")
            else:
                if st.button(f"Generate Art - Day {day_num}", key=f"gen_art_{day_num}"):
                    with st.spinner(f"Generating art for Day {day_num}..."):
                        try:
                            new_prompts = prompt_gen.generate_scene_prompts(
                                scene_text=day_content,
                                day_number=day_num,
                                model=model,
                                aspect_ratio=aspect_ratio,
                                temperature=temperature,
                                system_prompt=st.session_state["visual_sys_prompt"]
                            )
                            
                            # Save
                            existing_prompts.append({
                                "day": day_num,
                                "prompt_type": "Flux.2 Klein 4b - DrawThings",
                                "aspect_ratio": aspect_ratio,
                                "wide": new_prompts.get("wide", ""),
                                "medium": new_prompts.get("medium", ""),
                                "closeup": new_prompts.get("closeup", ""),
                                "dramatic": new_prompts.get("dramatic", ""),
                                "alternate": new_prompts.get("alternate", ""),
                                "negative_prompt": new_prompts.get("negative_prompt", ""),
                                "raw_response": new_prompts.get("raw_response", "")
                            })
                            
                            storage.update_episode(
                                episode_id=ep_id,
                                prompts={"scenes": existing_prompts, "aspect_ratio": aspect_ratio}
                            )
                            
                            st.success(f"Generated Day {day_num}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")


def render_video_stage(ollama, model, temperature, storage, prompt_gen, story_gen):
    """Stage 3: Video prompts for DrawThings + Wan 2.2."""
    
    st.markdown("# 🎬 Video")
    st.markdown("Generate image-to-video prompts. Optimized for DrawThings + Wan 2.2 High Noise 6-bit SVDQuant.")
    
    st.markdown("---")
    
    # Check for current episode
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
    
    # Check if art prompts exist
    if not episode.get("prompts") or not episode["prompts"].get("scenes"):
        st.info("Generate art prompts first (Art tab). Video prompts build on the same scene analysis.")
        return
    
    art_prompts = episode["prompts"]["scenes"]
    
    st.markdown("## Generate Video for Each Day")
    
    # Parse days
    days = story_gen.parse_days(story)
    
    for day in days:
        day_num = day['number']
        day_title = day['title']
        day_content = day['content']
        
        # Find art prompt for this day
        day_art = [p for p in art_prompts if p.get("day") == day_num]
        day_video = [p for p in art_prompts if p.get("day") == day_num and "video_" in str(p)]
        
        with st.expander(f"Day {day_num}: {day_title}", expanded=False):
            if not day_art:
                st.warning("Generate art for this day first.")
                continue
            
            art = day_art[0]
            
            # Show keyframe (use medium/action prompt as keyframe base)
            st.markdown("**Keyframe (use with Flux.2 Klein 4b output):**")
            st.markdown(f"```\n{art.get('medium', art.get('wide', ''))}\n```")
            
            if day_video:
                st.markdown(f"**✓ Video prompt generated**")
                for v in day_video:
                    st.markdown("**Motion:**")
                    st.code(v.get("video_motion", ""), language="text")
                    st.markdown("**Camera:**")
                    st.code(v.get("video_camera", ""), language="text")
                    st.markdown("**Wan 2.2 Prompt:**")
                    st.code(v.get("video_wan_prompt", ""), language="text")
            else:
                if st.button(f"Generate Video - Day {day_num}", key=f"gen_vid_{day_num}"):
                    with st.spinner(f"Generating video prompt for Day {day_num}..."):
                        try:
                            # Use the medium prompt as keyframe base
                            keyframe_text = art.get("medium", art.get("wide", ""))
                            scene_context = f"Keyframe image: {keyframe_text}\n\nScene context: {day_content[:500]}"
                            
                            video_prompts = prompt_gen.generate_scene_prompts(
                                scene_text=scene_context,
                                day_number=day_num,
                                model=model,
                                aspect_ratio=episode["prompts"].get("aspect_ratio", "16:9"),
                                temperature=temperature,
                                system_prompt=st.session_state["visual_sys_prompt"]
                            )
                            
                            # Add video fields to existing art prompt
                            art["video_keyframe"] = video_prompts.get("video_keyframe", "")
                            art["video_motion"] = video_prompts.get("video_motion", "")
                            art["video_camera"] = video_prompts.get("video_camera", "")
                            art["video_wan_prompt"] = video_prompts.get("video_wan_prompt", "")
                            art["video_settings"] = video_prompts.get("video_settings", "")
                            
                            # Save
                            storage.update_episode(
                                episode_id=ep_id,
                                prompts={"scenes": art_prompts, "aspect_ratio": episode["prompts"].get("aspect_ratio", "16:9")}
                            )
                            
                            st.success(f"Generated video for Day {day_num}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")


def render_library_stage(storage, story_gen):
    """Stage 4: Library & export."""
    
    st.markdown("# 📚 Library")
    st.markdown("Browse and export episodes.")
    
    st.markdown("---")
    
    episodes = storage.list_episodes()
    
    if not episodes:
        st.info("No episodes yet.")
        return
    
    # Stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Episodes", len(episodes))
    with col2:
        st.metric("Total days", sum(ep.get("num_days", 0) for ep in episodes))
    with col3:
        st.metric("Unique Jedi", len(set(ep.get("jedi_name", "Unknown") for ep in episodes)))
    
    st.markdown("---")
    
    # Search
    search = st.text_input("Search", placeholder="Title or Jedi name...", key="lib_search")
    
    filtered = episodes
    if search:
        s = search.lower()
        filtered = [ep for ep in filtered if s in ep.get("title", "").lower() or s in ep.get("jedi_name", "").lower()]
    
    st.markdown(f"**{len(filtered)} episode(s)**")
    st.markdown("---")
    
    # Episode list
    for ep in filtered:
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
            
            with col1:
                st.markdown(f"**{ep.get('title', 'Untitled')}**")
                st.markdown(f"_{ep.get('jedi_name', 'Unknown')} • {ep.get('setting', 'Unknown')}_")
            
            with col2:
                st.markdown(f"Days: {ep.get('num_days', 'N/A')}")
                st.markdown(f"Created: {ep.get('created_at', '')[:10]}")
            
            with col3:
                if st.button("Load", key=f"lib_load_{ep['id']}"):
                    episode = storage.load_episode(ep['id'])
                    if episode:
                        st.session_state["current_episode_id"] = ep['id']
                        st.session_state["current_story"] = episode["story"]
                        st.session_state["current_metadata"] = episode["metadata"]
                        st.success(f"Loaded: {ep['title']}")
                        st.rerun()
            
            with col4:
                if st.button("×", key=f"lib_del_{ep['id']}"):
                    storage.delete_episode(ep['id'])
                    st.rerun()
            
            st.markdown("---")
    
    # Export current episode
    if st.session_state.get("current_episode_id"):
        st.markdown("## Export Current Episode")
        
        ep_id = st.session_state["current_episode_id"]
        episode = storage.load_episode(ep_id)
        
        if episode:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.download_button(
                    "Story (.md)",
                    data=episode["story"],
                    file_name=f"{ep_id}_story.md",
                    mime="text/markdown"
                )
            
            with col2:
                import json
                full_data = {
                    "metadata": episode["metadata"],
                    "story": episode["story"],
                    "prompts": episode.get("prompts")
                }
                st.download_button(
                    "Full (.json)",
                    data=json.dumps(full_data, indent=2),
                    file_name=f"{ep_id}_full.json",
                    mime="application/json"
                )
            
            with col3:
                if episode.get("prompts"):
                    st.download_button(
                        "Prompts (.json)",
                        data=json.dumps(episode["prompts"], indent=2),
                        file_name=f"{ep_id}_prompts.json",
                        mime="application/json"
                    )


def main():
    init_session_state()
    
    # Sidebar
    ollama_url, model, temperature = render_sidebar()
    
    # Header
    st.markdown("# Gravedancer to General")
    st.markdown("*Anatomy of a Catastrophe — A Star Wars fan series*")
    
    st.markdown("---")
    
    # Initialize clients
    ollama = get_ollama_client(ollama_url)
    storage = get_storage(st.session_state["storage_path"])
    story_gen = StoryGenerator(ollama)
    prompt_gen = PromptGenerator(ollama)
    
    # Tabs (simple, horizontal)
    tab1, tab2, tab3, tab4 = st.tabs([
        "📖 Story",
        "🎨 Art",
        "🎬 Video",
        "📚 Library"
    ])
    
    with tab1:
        render_story_stage(ollama, model, temperature, storage, story_gen)
    
    with tab2:
        render_art_stage(ollama, model, temperature, storage, prompt_gen, story_gen)
    
    with tab3:
        render_video_stage(ollama, model, temperature, storage, prompt_gen, story_gen)
    
    with tab4:
        render_library_stage(storage, story_gen)


if __name__ == "__main__":
    main()