"""Olive & Stone theme — ported verbatim from techmore.github.io.

Reference design tokens (from the live source):
  - Display font: Instrument Serif (italic) for headings
  - Body font: Inter
  - Palette: oklch() olive + stone scale (exact values below)
  - Warm, light, editorial aesthetic — NOT a dark theme.
"""

# Google Fonts <link> injected separately in app.py via st.markdown.
FONTS_LINK = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap" rel="stylesheet">"""

CUSTOM_CSS = """
<style>
    /* ===== Olive & Stone palette — verbatim oklch from techmore.github.io ===== */
    :root {
        --olive-50:  oklch(97.73% 0.0054 117.92);
        --olive-100: oklch(95.09% 0.0134 115.84);
        --olive-200: oklch(90.20% 0.0232 117.63);
        --olive-300: oklch(82.52% 0.0345 116.34);
        --olive-400: oklch(73.59% 0.0492 116.81);
        --olive-500: oklch(64.26% 0.0588 117.06);
        --olive-600: oklch(54.54% 0.0616 116.19);
        --olive-700: oklch(46.42% 0.0493 117.00);
        --olive-800: oklch(39.89% 0.0355 116.41);
        --olive-900: oklch(35.57% 0.0284 116.00);
        --olive-950: oklch(24.22% 0.0185 116.99);

        --stone-50:  oklch(98.48% 0.0013 106.42);
        --stone-100: oklch(96.99% 0.0013 106.42);
        --stone-200: oklch(92.32% 0.0026 48.72);
        --stone-300: oklch(86.87% 0.0043 56.37);
        --stone-400: oklch(71.61% 0.0091 56.26);
        --stone-500: oklch(55.34% 0.0116 58.07);
        --stone-600: oklch(44.44% 0.0096 73.64);
        --stone-700: oklch(37.41% 0.0087 67.56);
        --stone-800: oklch(26.85% 0.0063 34.30);
        --stone-900: oklch(21.61% 0.0061 56.04);

        /* Semantic aliases matching techmore's :root */
        --bg:          var(--olive-300);  /* oklch(82.52% 0.0345 116.34) */
        --surface:     var(--olive-200);  /* oklch(90.20% 0.0232 117.63) */
        --surface-2:   var(--olive-300);
        --border:      var(--olive-400);
        --text:        var(--stone-800);
        --text-light:  var(--stone-500);
        --accent:      var(--olive-700);
        --accent-fg:   var(--olive-50);
        --feature-bg:  var(--olive-950);  /* dark feature cards */

        --amber: oklch(52% 0.130 75);
        --red:   oklch(45% 0.160 25);
        --green: oklch(52% 0.090 145);

        --font-display: 'Instrument Serif', Georgia, serif;
        --font-body: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    /* ===== Base ===== */
    html, body, [class*="css"] {
        font-family: var(--font-body);
    }

    .stApp {
        background: var(--bg);
        color: var(--text);
        font-size: 15px;
        line-height: 1.6;
        -webkit-font-smoothing: antialiased;
    }

    /* Main content container — sit on the warm surface tone with breathing room */
    .stApp > header + div, .block-container {
        background: transparent;
        padding-top: 2rem;
    }

    /* ===== Headings — the signature Instrument Serif italic display ===== */
    h1, h2, h3, h4, h5, h6 {
        font-family: var(--font-display) !important;
        color: var(--olive-950) !important;
        line-height: 1.2 !important;
        font-weight: 400 !important;
        letter-spacing: 0 !important;
    }

    h1 {
        font-size: 2.2rem !important;
        font-style: italic;
        border-bottom: none;
        margin-top: 0.2em;
    }

    h2 {
        font-size: 1.6rem !important;
        font-style: italic;
        margin-top: 1.5em;
    }

    h3 {
        font-size: 1.3rem !important;
        color: var(--olive-900) !important;
    }

    /* Body text */
    body, p, li, span, div, label {
        color: var(--text);
    }

    /* ===== Sidebar — olive-50 frosted panel ===== */
    [data-testid="stSidebar"] {
        background: color-mix(in oklch, var(--olive-50) 90%, transparent) !important;
        backdrop-filter: blur(8px);
        border-right: 1px solid color-mix(in oklch, var(--olive-200) 60%, transparent) !important;
    }

    [data-testid="stSidebar"] * {
        color: var(--stone-700) !important;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: var(--olive-800) !important;
    }

    /* ===== Cards — the techmore two-flavor system ===== */
    /* Light card: bg surface, olive border, rounded-xl */
    .sw-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 0.75rem;
        padding: 1.25rem;
        margin: 0.5rem 0;
    }
    /* Feature card: dark olive-950, light text */
    .sw-card-feature {
        background: var(--feature-bg);
        color: var(--olive-50);
        border: 1px solid var(--olive-800);
        border-radius: 0.75rem;
        padding: 1.25rem;
        margin: 0.5rem 0;
    }
    .sw-card-feature, .sw-card-feature * {
        color: var(--olive-50) !important;
    }
    .sw-card-feature h2, .sw-card-feature h3 {
        color: var(--olive-50) !important;
    }

    /* Eyebrow label — mono, uppercase, tracking-widest (techmore "Audit"/"Switch" tags) */
    .sw-eyebrow {
        font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
        font-size: 0.7rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--olive-600);
        font-weight: 500;
    }
    .sw-card-feature .sw-eyebrow {
        color: var(--olive-400);
    }

    /* ===== Buttons — pill on olive ===== */
    .stButton > button {
        background: var(--olive-100) !important;
        color: var(--olive-900) !important;
        border: 1px solid var(--olive-400) !important;
        border-radius: 0.5rem !important;
        font-family: var(--font-body) !important;
        font-weight: 500 !important;
        padding: 0.45em 1em !important;
        transition: background-color 0.15s ease, border-color 0.15s ease;
    }
    .stButton > button:hover {
        background: var(--surface) !important;
        border-color: var(--olive-600) !important;
        color: var(--olive-950) !important;
    }
    .stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"] {
        background: var(--accent) !important;
        color: var(--accent-fg) !important;
        border: 1px solid var(--olive-800) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: var(--olive-800) !important;
        color: var(--accent-fg) !important;
    }

    /* Secondary "outline" button via a helper class on the label — used for GitHub-style borders */
    .sw-btn-outline {
        background: transparent !important;
        border: 1px solid var(--olive-300) !important;
        color: var(--stone-500) !important;
    }

    /* ===== Inputs — white field, olive border, soft focus ring ===== */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > div,
    .stMultiSelect > div > div {
        background: #ffffff !important;
        color: var(--stone-800) !important;
        border: 1px solid var(--olive-400) !important;
        border-radius: 0.375rem !important;
        font-family: var(--font-body) !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus,
    .stNumberInput > div > div > input:focus {
        border-color: var(--olive-500) !important;
        box-shadow: 0 0 0 2px color-mix(in oklch, var(--olive-500) 40%, transparent);
    }

    /* Code blocks — olive-50 surface, mono */
    code, pre {
        background: var(--olive-50) !important;
        color: var(--olive-950) !important;
        border: 1px solid var(--olive-300) !important;
        border-radius: 0.375rem !important;
        font-family: 'SF Mono', 'Monaco', 'Courier New', monospace !important;
        font-size: 0.875em;
    }
    pre code {
        border: none !important;
    }

    /* ===== Sliders ===== */
    .stSlider [data-baseweb="slider"] > div > div {
        background: var(--olive-200) !important;
    }
    .stSlider [data-baseweb="thumb"] {
        background-color: var(--accent) !important;
        border: 2px solid var(--olive-50) !important;
    }
    .stSlider [data-baseweb="track"] {
        background-color: var(--olive-400) !important;
    }

    /* ===== Tabs — clean underline, italic active label ===== */
    .stTabs [data-baseweb="tab-list"] {
        background: transparent;
        border-bottom: 1px solid var(--border);
        gap: 0;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        color: var(--stone-600) !important;
        font-family: var(--font-body) !important;
        font-weight: 500 !important;
        padding: 0.7em 1.3em !important;
        border-radius: 0 !important;
        border-bottom: 2px solid transparent !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: var(--olive-100) !important;
        color: var(--olive-800) !important;
    }
    .stTabs [aria-selected="true"] {
        background: transparent !important;
        color: var(--olive-950) !important;
        border-bottom: 2px solid var(--accent) !important;
        font-weight: 600 !important;
    }

    /* ===== Expanders — surface card ===== */
    [data-testid="stExpander"] {
        border: 1px solid var(--border) !important;
        border-radius: 0.75rem !important;
        background: var(--surface) !important;
        overflow: hidden;
    }
    .streamlit-expanderHeader, [data-baseweb="accordion"] [data-baseweb="accordion-header"] {
        background: var(--olive-100) !important;
        color: var(--olive-900) !important;
        font-family: var(--font-body) !important;
        font-weight: 500 !important;
    }
    .streamlit-expanderHeader:hover {
        background: var(--surface) !important;
    }

    /* ===== Metrics ===== */
    [data-testid="stMetricValue"] {
        color: var(--olive-950) !important;
        font-family: var(--font-display) !important;
        font-size: 1.6rem !important;
        font-style: italic;
    }
    [data-testid="stMetricLabel"] {
        color: var(--stone-600) !important;
        font-size: 0.75em !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-family: var(--font-body) !important;
    }

    /* ===== Alerts — left border accent ===== */
    .stAlert, [data-testid="stAlert"] {
        background: var(--olive-100) !important;
        border: 1px solid var(--border) !important;
        border-left: 3px solid var(--accent) !important;
        color: var(--stone-800) !important;
        border-radius: 0.5rem !important;
    }

    /* Progress bar */
    .stProgress > div > div > div > div {
        background: var(--accent) !important;
    }

    hr, [data-testid="stDivider"] {
        border: none !important;
        height: 1px !important;
        background: var(--border) !important;
        margin: 1.5em 0 !important;
    }

    a {
        color: var(--accent) !important;
        text-decoration: underline;
        text-underline-offset: 2px;
    }
    a:hover {
        color: var(--olive-900) !important;
    }

    /* ===== Selection + scrollbar (techmore custom) ===== */
    ::selection {
        background: var(--surface);
        color: var(--olive-800);
    }
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: var(--olive-100); }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--olive-500); }

    /* Multiselect chips */
    .stMultiSelect [data-baseweb="tag"] {
        background: var(--olive-200) !important;
        color: var(--olive-900) !important;
        border: 1px solid var(--olive-400) !important;
    }

    /* ===== Day headers in stories ===== */
    .day-header {
        font-family: var(--font-display);
        font-size: 1.4rem !important;
        font-style: italic;
        color: var(--olive-950) !important;
        border-bottom: 1px solid var(--border);
        padding-bottom: 0.3em;
        margin-top: 1.5em;
        margin-bottom: 0.8em;
    }

    /* Star Wars accent (olive, not red — matches the palette) */
    .blood-accent {
        border-left: 3px solid var(--accent);
        padding-left: 1em;
        margin: 1em 0;
        color: var(--text);
    }

    /* Stage indicator pills */
    .stage {
        display: inline-block;
        padding: 0.2em 0.65em;
        background: var(--accent);
        color: var(--accent-fg);
        border-radius: 0.375rem;
        font-size: 0.8em;
        font-weight: 500;
        font-family: var(--font-body);
    }
    .stage-active { background: var(--olive-800); }
    .stage-pending { background: var(--olive-400); color: var(--stone-700); }

    /* Quick start / hero banner */
    .quick-start {
        background: var(--surface);
        border: 1px solid var(--olive-500);
        border-radius: 0.75rem;
        padding: 1em 1.25em;
        margin: 0.5em 0;
    }
    .suggestion-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 0.75rem;
        padding: 0.9em;
        margin: 0.4em 0;
    }

    /* Connection badge */
    .conn-badge {
        display: inline-block;
        padding: 0.15em 0.6em;
        border-radius: 999px;
        font-size: 0.75em;
        font-weight: 600;
        font-family: var(--font-body);
    }
    .conn-ok { background: var(--green); color: var(--olive-50); }
    .conn-bad { background: var(--red); color: var(--olive-50); }

    /* Quality warning */
    .quality-warn {
        background: color-mix(in oklch, var(--amber) 12%, var(--olive-50));
        border: 1px solid color-mix(in oklch, var(--amber) 45%, var(--olive-200));
        border-left: 3px solid var(--amber);
        border-radius: 0.5rem;
        padding: 0.75em 1em;
        color: var(--stone-800);
        margin: 0.5em 0;
    }
</style>
"""
