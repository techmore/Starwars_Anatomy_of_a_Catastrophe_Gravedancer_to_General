"""Curated model recommendations for MLX.

Each model has metadata about what it's best for, memory requirements, and quality tier.
The app uses this to recommend models in the UI when MLX models are detected.
"""

from pathlib import Path

# Model metadata: name -> {display, quality, strengths, ram_gb, family}
# Names use prefix-matching to match any tag (e.g., "llama3.1" matches "llama3.1:8b")
MODEL_CATALOG = {
    # Recommended production stack for the M1 Pro / 32 GB target.
    "mlx-community/Qwen3.8-27B-OptiQ-4bit": {
        "display": "Qwen 3.8 27B OptiQ 4-bit MLX — PRIMARY STORY MODEL",
        "quality": "best",
        "tier": 0,
        "strengths": ["Highest-quality local prose", "Long-form structure", "Strong revision and continuity work"],
        "ram_gb": "~15-17 plus context/KV cache",
        "family": "qwen",
        "story_pull": True,
        "platform": "mac",
    },
    "mlx-community/gemma-4-e4b-it-OptiQ-4bit": {
        "display": "Gemma 4 E4B IT OptiQ 4-bit MLX — FAST STORY MODEL",
        "quality": "best",
        "tier": 1,
        "strengths": ["Fast Apple Silicon inference", "Good instruction following", "Compact quality model"],
        "ram_gb": "~8-11 plus context/KV cache",
        "family": "gemma",
        "story_pull": True,
        "platform": "mac",
    },
    "mlx-community/gemma-4-e2b-it-4bit": {
        "display": "Gemma 4 E2B IT 4-bit MLX — UTILITY MODEL",
        "quality": "good",
        "tier": 2,
        "strengths": ["Very fast", "Low memory pressure", "Metadata and validation passes"],
        "ram_gb": "~3-5 plus context/KV cache",
        "family": "gemma",
        "story_pull": True,
        "platform": "mac",
    },
    "mlx-community/Qwen3.5-4B-MLX-4bit": {
        "display": "Qwen 3.5 4B MLX 4-bit — FAST UTILITY MODEL",
        "quality": "good",
        "tier": 2,
        "strengths": ["Fast iteration", "Structured transformations", "Low memory pressure"],
        "ram_gb": "~3-5 plus context/KV cache",
        "family": "qwen",
        "story_pull": True,
        "platform": "mac",
    },
    # Top tier - best for long-form creative writing
    "prism-ml/Bonsai-27B-mlx-1bit": {
        "display": "Bonsai 27B 1-bit MLX (memory-efficient creative workflow)",
        "quality": "good",
        "tier": 0,
        "strengths": ["27B-class model in a compact MLX package", "Long-form story work", "Low unified-memory pressure"],
        "ram_gb": "~6-8 at practical story contexts",
        "family": "bonsai",
        "story_pull": True,
        "platform": "mac",
    },
    "qwen3.6:27b-mlx": {
        "display": "Qwen 3.6 27B MLX (Apple Silicon optimized) — DEFAULT",
        "quality": "best",
        "tier": 0,  # Top priority for Mac users
        "strengths": ["MLX/Metal accelerated", "Long-form prose", "Following complex structure"],
        "ram_gb": "~18-20",
        "family": "qwen",
        "story_pull": True,
        "platform": "mac"
    },
    "mlx-community/gemma-4-e2b-it-qat-OptiQ-4bit": {
        "display": "Gemma 4 E2B OptiQ 4-bit MLX (Apple Silicon) — DEFAULT",
        "quality": "best",
        "tier": 0,
        "strengths": ["Fast on Apple Silicon", "Clean instruction following", "Compact ~4.3GB footprint"],
        "ram_gb": "~4-5",
        "family": "gemma",
        "story_pull": True,
        "platform": "mac"
    },
    "mlx-community/Qwen3-32B-4bit": {
        "display": "Qwen 3 32B 4-bit MLX (Apple Silicon optimized)",
        "quality": "best",
        "tier": 0,
        "strengths": ["MLX/Metal accelerated", "Excellent creative writing", "Long-form prose"],
        "ram_gb": "~18-20",
        "family": "qwen",
        "story_pull": True,
        "platform": "mac"
    },
    "mlx-community/Qwen3.6-27B-OptiQ-4bit": {
        "display": "Qwen 3.6 27B OptiQ 4-bit MLX (Apple Silicon optimized)",
        "quality": "best",
        "tier": 0,
        "strengths": ["MLX/Metal accelerated", "Lower memory footprint", "Long-form prose"],
        "ram_gb": "~14-16",
        "family": "qwen",
        "story_pull": True,
        "platform": "mac"
    },
    "mlx-community/Qwen3.6-27B-4bit": {
        "display": "Qwen 3.6 27B 4-bit MLX (lighter Apple Silicon option)",
        "quality": "best",
        "tier": 0,
        "strengths": ["MLX/Metal accelerated", "Lower memory footprint", "Long-form prose"],
        "ram_gb": "~14-16",
        "family": "qwen",
        "story_pull": True,
        "platform": "mac"
    },
    "mlx-community/Qwen3-8B-4bit": {
        "display": "Qwen 3 8B 4-bit MLX (fast iteration)",
        "quality": "good",
        "tier": 1,
        "strengths": ["Very fast", "Low memory footprint", "Great for iteration"],
        "ram_gb": "~4-6",
        "family": "qwen",
        "story_pull": True,
        "platform": "mac"
    },
    "mlx-community/gemma-4-12B-it-OptiQ-4bit": {
        "display": "Gemma 4 12B OptiQ 4-bit MLX",
        "quality": "good",
        "tier": 1,
        "strengths": ["Strong instruction following", "Clean JSON output", "Less reasoning overhead"],
        "ram_gb": "~8-10",
        "family": "gemma",
        "story_pull": True,
        "platform": "mac"
    },
    "qwen3.6": {
        "display": "Qwen 3.6 27B (excellent prose, long context)",
        "quality": "best",
        "tier": 1,
        "strengths": ["Long-form prose", "Following complex structure", "Atmospheric writing"],
        "ram_gb": "~18-20",
        "family": "qwen",
        "story_pull": True
    },
    "qwen2.5": {
        "display": "Qwen 2.5 (excellent prose, long context)",
        "quality": "best",
        "tier": 1,
        "strengths": ["Long-form prose", "Following complex structure", "Multilingual"],
        "ram_gb": "~16-20",
        "family": "qwen",
        "story_pull": True
    },
    "llama3.1:70b": {
        "display": "Llama 3.1 70B (strongest, needs lots of RAM)",
        "quality": "best",
        "tier": 1,
        "strengths": ["Best-in-class prose", "Long context", "Complex narrative"],
        "ram_gb": "~40+",
        "family": "llama",
        "story_pull": True
    },
    "llama3.1": {
        "display": "Llama 3.1 8B (solid, fast)",
        "quality": "good",
        "tier": 2,
        "strengths": ["Fast", "Reliable", "Good structure following"],
        "ram_gb": "~8",
        "family": "llama",
        "story_pull": True
    },
    "gemma2:27b": {
        "display": "Gemma 2 27B (Google, strong instruction-following)",
        "quality": "best",
        "tier": 1,
        "strengths": ["Instruction following", "Atmospheric prose", "Structured output"],
        "ram_gb": "~20",
        "family": "gemma",
        "story_pull": True
    },
    "gemma2": {
        "display": "Gemma 2 9B (fast, good quality)",
        "quality": "good",
        "tier": 2,
        "strengths": ["Fast", "Reliable prose", "Good instruction following"],
        "ram_gb": "~10",
        "family": "gemma",
        "story_pull": True
    },
    "command-r": {
        "display": "Command-R (Cohere, creative writing tuned)",
        "quality": "best",
        "tier": 1,
        "strengths": ["Creative writing", "RAG-aware", "Long context"],
        "ram_gb": "~20",
        "family": "cohere",
        "story_pull": True
    },
    "mistral": {
        "display": "Mistral 7B (fast, decent)",
        "quality": "ok",
        "tier": 3,
        "strengths": ["Very fast", "Lightweight"],
        "ram_gb": "~8",
        "family": "mistral",
        "story_pull": False
    },
    "mixtral": {
        "display": "Mixtral 8x7B (MoE, strong creative)",
        "quality": "good",
        "tier": 2,
        "strengths": ["Creative prose", "Mixture of experts", "Solid structure"],
        "ram_gb": "~26",
        "family": "mistral",
        "story_pull": True
    },
    "deepseek": {
        "display": "DeepSeek (code + writing, mixed)",
        "quality": "ok",
        "tier": 3,
        "strengths": ["Code", "Technical writing"],
        "ram_gb": "~8-20",
        "family": "deepseek",
        "story_pull": False
    }
}

# Recommended models for the "best for stories" default
# Picked for: long-form creative prose, instruction following, stable generation
# MLX variants come first — they're optimized for Apple Silicon Macs
STORY_RECOMMENDED = [
    "mlx-community/Qwen3.8-27B-OptiQ-4bit",
    "mlx-community/gemma-4-e4b-it-OptiQ-4bit",
    "mlx-community/gemma-4-e2b-it-4bit",
    "mlx-community/Qwen3.5-4B-MLX-4bit",
    "prism-ml/Bonsai-27B-mlx-1bit",
    "mlx-community/gemma-4-e2b-it-qat-OptiQ-4bit",
    "mlx-community/Qwen3-32B-4bit",
    "mlx-community/Qwen3.6-27B-OptiQ-4bit",
    "mlx-community/Qwen3.6-27B-4bit",
    "mlx-community/gemma-4-12B-it-OptiQ-4bit",
    "mlx-community/Qwen3-8B-4bit",
    "qwen3.6:27b-mlx",
    "qwen3.6",
    "qwen2.5",
    "llama3.1:70b",
    "command-r",
    "gemma2:27b",
    "llama3.1",
    "gemma2",
    "mixtral"
]

# Default model — Qwen 3.8 27B OptiQ is the primary local story workflow for
# the target M1 Pro (32 GB unified memory). Bonsai remains available through
# its isolated runtime; Gemma is the lightweight fallback in the sidebar.
DEFAULT_MODEL = "mlx-community/Qwen3.8-27B-OptiQ-4bit"

# Practical guidance for this project's target hardware. These are operational
# recommendations, not hard admission checks: users may still select a custom
# local model when they understand its memory requirements.
M1_PRO_32GB_GUIDANCE = {
    "mlx-community/Qwen3.8-27B-OptiQ-4bit": {
        "label": "Primary story model",
        "detail": "Use for outline synthesis, long-form prose, continuity revision, and final editorial passes. Keep one model loaded and bound context deliberately.",
        "concurrency": "Run MLX alone; close Draw Things during long generations",
    },
    "mlx-community/gemma-4-e4b-it-OptiQ-4bit": {
        "label": "Fast story model",
        "detail": "Use for routine drafting, chapter prompts, metadata, and quick revisions with substantially lower memory pressure.",
        "concurrency": "Suitable for normal local workflow",
    },
    "prism-ml/Bonsai-27B-mlx-1bit": {
        "label": "Recommended 27B-class workflow",
        "detail": "A compact 1-bit MLX build that leaves substantially more unified-memory headroom than conventional 27B 4-bit models. Keep story context deliberately bounded.",
        "concurrency": "Suitable for normal prompt work; pause large Draw Things renders for long story passes",
    },
    "mlx-community/gemma-4-e2b-it-qat-OptiQ-4bit": {
        "label": "Recommended daily driver",
        "detail": "Compact enough to keep Streamlit and Draw Things available for normal prompt and story work.",
        "concurrency": "Safe for normal local workflow",
    },
    "mlx-community/Qwen3-8B-4bit": {
        "label": "Balanced alternative",
        "detail": "More headroom than the large models while remaining practical for repeated multi-pass drafts.",
        "concurrency": "Safe for normal local workflow",
    },
    "mlx-community/gemma-4-12B-it-OptiQ-4bit": {
        "label": "Quality-focused alternative",
        "detail": "Use for story passes when you want more quality without the 27B/32B memory pressure.",
        "concurrency": "Avoid large Draw Things renders during generation",
    },
    "mlx-community/Qwen3.6-27B-OptiQ-4bit": {
        "label": "High-quality, single-workload mode",
        "detail": "Suitable for focused story generation, but close Draw Things and avoid switching models mid-run.",
        "concurrency": "Run MLX alone; keep generation batches small",
    },
    "mlx-community/Qwen3.6-27B-4bit": {
        "label": "High-quality, single-workload mode",
        "detail": "Suitable for focused story generation, but close Draw Things and avoid switching models mid-run.",
        "concurrency": "Run MLX alone; keep generation batches small",
    },
    "mlx-community/Qwen3-32B-4bit": {
        "label": "Near the 32 GB limit",
        "detail": "Use only for short, deliberate story passes with Draw Things closed; unified-memory pressure can make long generations unstable.",
        "concurrency": "Do not run alongside Draw Things",
    },
}

MODEL_ALIASES = {
    "qwen3.6:27b-mlx": "mlx-community/Qwen3.6-27B-4bit",
}


def normalize_model_name(model_name: str) -> str:
    """Map UI-friendly aliases to a valid MLX repo id or local path."""
    return MODEL_ALIASES.get(model_name, model_name)


def get_m1_pro_32gb_guidance(model_name: str) -> dict:
    """Return operational guidance for the target M1 Pro with 32 GB RAM."""
    normalized = normalize_model_name(model_name)
    return M1_PRO_32GB_GUIDANCE.get(
        normalized,
        {
            "label": "Custom model",
            "detail": "Confirm its on-disk and runtime memory needs before a long generation run.",
            "concurrency": "Load one text model at a time",
        },
    )


def get_model_info(installed_name: str) -> dict:
    """Get info about an installed model, matching by prefix."""
    # Try exact match first
    if installed_name in MODEL_CATALOG:
        return MODEL_CATALOG[installed_name]
    
    # Try prefix match (e.g., "qwen2.5:7b" matches "qwen2.5")
    for catalog_name, info in MODEL_CATALOG.items():
        if installed_name.startswith(catalog_name):
            return info
    
    # Unknown model
    return {
        "display": installed_name,
        "quality": "unknown",
        "tier": 99,
        "strengths": [],
        "ram_gb": "?",
        "family": "unknown",
        "story_pull": False
    }


def sort_models_for_ui(installed_models: list) -> list:
    """Sort installed models: best-for-stories first, then by tier, then by STORY_RECOMMENDED priority."""
    def sort_key(name):
        info = get_model_info(name)
        # Compute recommended priority (lower = better). Unknown models get high number.
        rec_priority = 99
        for i, rec in enumerate(STORY_RECOMMENDED):
            if name.startswith(rec):
                rec_priority = i
                break
        return (
            not info.get("story_pull", False),  # story-friendly first
            info.get("tier", 99),                # lower tier = better
            rec_priority,                         # lower recommendation index = better
            name                                  # alphabetical tiebreaker
        )
    return sorted(installed_models, key=sort_key)


def get_recommended_default(installed_models: list) -> str:
    """Pick the best default model from what's installed."""
    if not installed_models:
        return DEFAULT_MODEL
    
    # Look for installed models in STORY_RECOMMENDED order
    for recommended in STORY_RECOMMENDED:
        for installed in installed_models:
            if installed.startswith(recommended):
                return installed
    
    # Fall back to first installed
    return installed_models[0]


def format_model_label(installed_name: str) -> str:
    """Format a model name for display in the UI."""
    info = get_model_info(installed_name)
    quality_badge = {
        "best": "★",
        "good": "●",
        "ok": "○",
        "unknown": "?"
    }.get(info.get("quality", "unknown"), "?")
    
    strengths = ", ".join(info.get("strengths", [])[:2])
    if strengths:
        return f"{quality_badge} {info['display']} — {strengths}"
    return f"{quality_badge} {info['display']}"


def get_install_commands() -> str:
    """Generate setup commands for recommended models."""
    return """\
# Prerequisites for Gemma 4 (gemma4_unified model type needs mlx-lm from git + optiq)
pip install -U mlx-optiq "mlx-lm @ git+https://github.com/ml-explore/mlx-lm.git"

# PRIMARY — Qwen 3.8 27B OptiQ 4-bit MLX (highest-quality local story model)
python -m mlx_lm.chat --model mlx-community/Qwen3.8-27B-OptiQ-4bit  # ~15-20GB on disk

# FAST STORY — Gemma 4 E4B IT OptiQ 4-bit MLX
python -m mlx_lm.chat --model mlx-community/gemma-4-e4b-it-OptiQ-4bit  # ~7.5GB on disk

# UTILITY — Gemma 4 E2B IT 4-bit MLX
python -m mlx_lm.chat --model mlx-community/gemma-4-e2b-it-4bit  # ~3-5GB on disk

# Higher-quality option for Macs with sufficient unified memory
python -m mlx_lm.chat --model mlx-community/Qwen3-32B-4bit  # ~18-20GB, excellent creative prose

# Alternatives — lighter / faster iteration
python -m mlx_lm.generate --model mlx-community/Qwen3.6-27B-4bit --prompt "Sanity check"  # ~14-16GB — lighter 4-bit MLX build for M-series Macs
python -m mlx_lm.chat --model mlx-community/Qwen3-8B-4bit  # ~5-6GB, fast iteration on M-series Macs

# Alternative MLX build
python -m mlx_lm.generate --model qwen3.6:27b-mlx --prompt "Sanity check"      # ~18-20GB — MLX-accelerated for M-series Macs

# Top tier (cross-platform)
python -m mlx_lm.generate --model qwen3.6:27b --prompt "Sanity check"          # ~18-20GB — excellent prose + structure
python -m mlx_lm.generate --model qwen2.5:32b --prompt "Sanity check"          # ~20GB, excellent prose
python -m mlx_lm.generate --model llama3.1:70b --prompt "Sanity check"         # ~40GB, best in class
python -m mlx_lm.generate --model gemma2:27b --prompt "Sanity check"           # ~16GB, Google, strong
python -m mlx_lm.generate --model command-r --prompt "Sanity check"            # ~20GB, Cohere, creative-tuned

# Mid tier (faster, lighter)
python -m mlx_lm.generate --model llama3.1 --prompt "Sanity check"             # ~4.7GB, solid default
python -m mlx_lm.generate --model gemma2 --prompt "Sanity check"               # ~5.4GB, fast
python -m mlx_lm.generate --model mixtral --prompt "Sanity check"              # ~26GB, MoE
"""


MLX_CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"


def list_local_mlx_models() -> list:
    """Scan the HuggingFace cache for downloaded MLX models.

    Returns a list of (display_label, repo_id) tuples sorted with
    best-for-stories first.
    """
    models: list[tuple[str, str]] = []
    if not MLX_CACHE_DIR.is_dir():
        return []
    for entry in sorted(MLX_CACHE_DIR.iterdir()):
        name = entry.name
        # Cache dirs follow the pattern: models--org--repo-name
        if not name.startswith("models--"):
            continue
        # Convert directory name back to HF repo ID
        parts = name.split("--")
        if len(parts) >= 3:
            repo_id = f"{parts[1]}/{'--'.join(parts[2:])}"
        else:
            repo_id = name
        # A repo reference alone only proves that metadata was fetched.  Require
        # a completed weight file too, so interrupted downloads cannot appear
        # as selectable "Ready" models in the UI.
        refs_dir = entry / "refs"
        if not refs_dir.is_dir():
            continue
        snapshot_names = [
            ref.read_text(encoding="utf-8").strip()
            for ref in refs_dir.iterdir()
            if ref.is_file() and ref.read_text(encoding="utf-8").strip()
        ]
        snapshots_dir = entry / "snapshots"
        if not any(
            any(path.is_file() and not path.name.endswith(".incomplete") for path in (snapshots_dir / snapshot).glob("*.safetensors"))
            for snapshot in snapshot_names
        ):
            continue
        label = format_model_label(repo_id)
        models.append((label, repo_id))
    sorted_models = sort_models_for_ui([m[1] for m in models])
    label_map = {m[1]: m[0] for m in models}
    return [(label_map.get(m, m), m) for m in sorted_models]
