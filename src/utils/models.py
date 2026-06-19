"""Curated model recommendations for MLX.

Each model has metadata about what it's best for, memory requirements, and quality tier.
The app uses this to recommend models in the UI when MLX models are detected.
"""

# Model metadata: name -> {display, quality, strengths, ram_gb, family}
# Names use prefix-matching to match any tag (e.g., "llama3.1" matches "llama3.1:8b")
MODEL_CATALOG = {
    # Top tier - best for long-form creative writing
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
    "mlx-community/Qwen3.6-27B-4bit",
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

# Default model — prefer the lighter 4-bit MLX build when available
DEFAULT_MODEL = "mlx-community/Qwen3.6-27B-4bit"


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
# DEFAULT — lighter Apple Silicon optimized (MLX/Metal)
python -m mlx_lm.generate --model mlx-community/Qwen3.6-27B-4bit --prompt "Sanity check"  # ~14-16GB — lighter 4-bit MLX build for M-series Macs

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
