"""Olive & Stone theme - inspired by techmore.github.io.

Uses exact oklch-derived olive palette with proper green-yellow saturation.
Olive hue ~116-117 (yellow-green), with visible chroma/saturation.
"""

CUSTOM_CSS = """
<style>
    /* Olive & Stone palette - converted from oklch (hue 116-117, yellow-green) */
    :root {
        --olive-50: #f5f5f4;
        --olive-100: #dde1d0;
        --olive-200: #c4c9b0;
        --olive-300: #a7ae8b;
        --olive-400: #8a9269;
        --olive-500: #6e754b;
        --olive-600: #575d3d;
        --olive-700: #464a34;
        --olive-800: #3b3e2d;
        --olive-900: #1f2117;
        --olive-950: #1c1917;
        
        --stone-50: #fbfaf8;
        --stone-100: #f5f5f4;
        --stone-200: #e7e5e4;
        --stone-300: #d6d3d1;
        --stone-400: #a8a29e;
        --stone-500: #78716c;
        --stone-600: #57534e;
        --stone-700: #44403c;
        --stone-800: #292524;
        --stone-900: #1c1917;
    }
    
    /* Main app background - light olive tint */
    .stApp {
        background: #ecebd9;
        color: var(--stone-700);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    /* Main content area - slightly lighter olive */
    .main .block-container {
        background: #ecebd9;
        padding-top: 2rem;
    }
    
    /* Sidebar - olive-100 */
    [data-testid="stSidebar"] {
        background: var(--olive-100);
        border-right: 1px solid var(--olive-300);
    }
    
    [data-testid="stSidebar"] * {
        color: var(--stone-700) !important;
    }
    
    /* Headers - olive-800 with strong contrast */
    h1, h2, h3, h4, h5, h6 {
        color: var(--olive-800) !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        font-weight: 600 !important;
    }
    
    h1 {
        font-size: 1.8em !important;
        border-bottom: 2px solid var(--olive-700);
        padding-bottom: 0.3em;
        margin-bottom: 0.5em;
    }
    
    h2 {
        font-size: 1.4em !important;
        margin-top: 1.5em;
        color: var(--olive-800) !important;
    }
    
    h3 {
        font-size: 1.2em !important;
        margin-top: 1.2em;
        color: var(--olive-700) !important;
    }
    
    /* Body text - stone-700 */
    body, p, li, div {
        color: var(--stone-700) !important;
        line-height: 1.6;
    }
    
    /* Code blocks - olive-100 bg */
    code, pre {
        background: var(--olive-100) !important;
        color: var(--olive-900) !important;
        border: 1px solid var(--olive-400);
        border-radius: 3px;
        font-family: 'Monaco', 'Courier New', monospace !important;
        font-size: 0.9em;
    }
    
    /* Buttons - olive primary (dark), olive-100 secondary */
    .stButton > button {
        background: var(--olive-100) !important;
        color: var(--olive-800) !important;
        border: 1px solid var(--olive-500) !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        padding: 0.5em 1em !important;
        transition: all 0.2s ease;
    }
    
    .stButton > button:hover {
        background: var(--olive-200) !important;
        border-color: var(--olive-600) !important;
    }
    
    .stButton > button[kind="primary"] {
        background: var(--olive-700) !important;
        color: var(--olive-50) !important;
        border: 1px solid var(--olive-800) !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        background: var(--olive-800) !important;
    }
    
    /* Input fields - white bg, olive border */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > div {
        background: #ffffff !important;
        color: var(--stone-800) !important;
        border: 1px solid var(--olive-400) !important;
        border-radius: 4px !important;
    }
    
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus,
    .stNumberInput > div > div > input:focus {
        border-color: var(--olive-600) !important;
        box-shadow: 0 0 0 1px var(--olive-600);
    }
    
    /* Sliders - olive */
    .stSlider > div > div > div {
        background: var(--olive-200) !important;
    }
    
    .stSlider > div > div > div > div {
        background: var(--olive-700) !important;
    }
    
    /* Tabs - clean horizontal */
    .stTabs [data-baseweb="tab-list"] {
        background: transparent;
        border-bottom: 1px solid var(--olive-400);
        gap: 0;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        color: var(--stone-600) !important;
        font-weight: 500 !important;
        padding: 0.8em 1.5em !important;
        border-radius: 6px 6px 0 0 !important;
        border-bottom: 2px solid transparent !important;
    }
    
    .stTabs [aria-selected="true"] {
        background: var(--olive-200) !important;
        color: var(--olive-900) !important;
        border-bottom: 2px solid var(--olive-700) !important;
        font-weight: 600 !important;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: var(--olive-100) !important;
        color: var(--olive-800) !important;
    }
    
    /* Expanders - olive-100 */
    .streamlit-expanderHeader {
        background: var(--olive-100) !important;
        color: var(--olive-800) !important;
        border: 1px solid var(--olive-400) !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
    }
    
    .streamlit-expanderHeader:hover {
        background: var(--olive-200) !important;
        border-color: var(--olive-500) !important;
    }
    
    /* Metrics - olive */
    [data-testid="stMetricValue"] {
        color: var(--olive-800) !important;
        font-size: 1.6em !important;
        font-weight: 600 !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: var(--stone-600) !important;
        font-size: 0.85em !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    /* Info/Warning/Error boxes */
    .stAlert {
        background: var(--olive-100) !important;
        border: 1px solid var(--olive-400) !important;
        border-left: 3px solid var(--olive-700) !important;
        color: var(--stone-800) !important;
    }
    
    /* Progress bar - olive */
    .stProgress > div > div > div > div {
        background: var(--olive-700) !important;
    }
    
    /* Divider - olive-300 */
    hr {
        border: none;
        height: 1px;
        background: var(--olive-300);
        margin: 1.5em 0;
    }
    
    /* Links - olive-700 */
    a {
        color: var(--olive-700) !important;
        text-decoration: underline;
    }
    
    a:hover {
        color: var(--olive-900) !important;
    }
    
    /* Scrollbar - stone */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--olive-50);
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--olive-400);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: var(--olive-600);
    }
    
    /* Multiselect tags - olive */
    .stMultiSelect > div > div {
        background: #ffffff !important;
        border: 1px solid var(--olive-400) !important;
    }
    
    .stMultiSelect [data-baseweb="tag"] {
        background: var(--olive-200) !important;
        color: var(--olive-900) !important;
        border: 1px solid var(--olive-500) !important;
    }
    
    /* Day headers in stories */
    .day-header {
        font-size: 1.3em !important;
        font-weight: 600 !important;
        color: var(--olive-800) !important;
        border-bottom: 1px solid var(--olive-400);
        padding-bottom: 0.3em;
        margin-top: 1.5em;
        margin-bottom: 0.8em;
    }
    
    /* Star Wars accent (subtle olive) */
    .blood-accent {
        border-left: 3px solid var(--olive-700);
        padding-left: 1em;
        margin: 1em 0;
        color: var(--stone-700);
    }
    
    /* Card-like containers - olive-100 bg */
    .sw-card {
        background: var(--olive-100);
        border: 1px solid var(--olive-400);
        border-radius: 6px;
        padding: 1em;
        margin: 0.5em 0;
    }
    
    /* Stage indicator */
    .stage {
        display: inline-block;
        padding: 0.2em 0.6em;
        background: var(--olive-700);
        color: var(--olive-50);
        border-radius: 4px;
        font-size: 0.85em;
        font-weight: 500;
    }
    
    .stage-active {
        background: var(--olive-800);
    }
    
    .stage-pending {
        background: var(--olive-300);
        color: var(--stone-700);
    }
    
    /* Quick start banner - strong olive */
    .quick-start {
        background: var(--olive-200);
        border: 1px solid var(--olive-500);
        border-radius: 6px;
        padding: 1em;
        margin: 0.5em 0;
    }
    
    /* Suggestion card - lighter olive */
    .suggestion-card {
        background: var(--olive-100);
        border: 1px solid var(--olive-400);
        border-radius: 6px;
        padding: 0.8em;
        margin: 0.4em 0;
    }
</style>
"""
