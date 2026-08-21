"""Structured creative randomization tables for story seed generation.

Picks are combined into a coherent concept seed that is then expanded by
the LLM.  True randomness avoids the repetitive patterns pure-LLM generation
falls into.
"""

import random
from typing import Any

# ── Jedi ──────────────────────────────────────────────────────────────────

JEDI_SPECIES = [
    "Togruta", "Miraluka", "Chiss", "Pantoran", "Kalleran",
    "Zabrak (Iridonian)", "Zabrak (Dathomirian)", "Nautolan", "Cerean",
    "Kel Dor", "Rodian", "Twi'lek (Lethan)", "Twi'lek (Rutian)",
    "Duros", "Bith", "Sullustan", "Ithorian", "Mon Calamari",
    "Kiffar", "Falleen", "Anx", "Ortolan", "Gotal",
    "Nikto", "Weequay", "Kubaz", "Umbaran", "Muun",
    "Mirdalan", "Arkanian", "Sephi", "Zeltron", "Theelin",
]

JEDI_RANKS = [
    "Jedi Youngling (prodigy)", "Jedi Padawan", "Jedi Knight",
    "Jedi Knight (veteran)", "Jedi Master", "Jedi Master (Council member)",
    "Jedi Battlemaster", "Jedi Sentinel", "Jedi Consular",
    "Jedi Watchman", "Jedi Wayseeker", "Jedi Loremaster",
]

SABER_COLORS = [
    "Viridian", "Amber", "Silver-white", "Cyan", "Bronze",
    "Orange-yellow", "Magenta", "Pearl white", "Crimson",
    "Electric blue", "Mint green", "Solar gold", "Indigo",
    "Violet", "Scarlet", "Obsidian black", "Celestial blue",
]

JEDI_PERSONALITY_TRAITS = [
    "stoic philosopher haunted by visions of the future",
    "fervent believer in the living Force, rejects Jedi dogma",
    "cynical veteran who has seen too many apprentices die",
    "ascetic hermit who communicates through Force-projected avatars",
    "zealous hunter of Sith artifacts, paranoid and meticulous",
    "pacifist healer who has never raised a saber in anger",
    "arrogant prodigy who believes the rules do not apply to them",
    "grief-stricken widow using the Order as a distraction from loss",
    "mystic dreamer who reads the future in the flight patterns of birds",
    "brutal pragmatist who views the saber as a tool, not a symbol",
    "warm mentor who treats every battle as a teaching moment",
    "cold logician who calculates battle outcomes before they begin",
    "guilt-ridden former slave who became a Jedi to prevent enslavement",
    "whimsical trickster who hides deep wisdom behind humor",
    "zealot who believes the Jedi Order has lost its way and must be rebuilt",
    "silent watcher who studies opponents for weeks before engaging",
    "passionate artist who sees the Force in color and sound",
    "ancient master who has outlived three generations of students",
]

JEDI_WHY_TARGETED = [
    "guarding a Separatist supply route Qymaen must destroy",
    "protecting a Kaleeh war criminal the clan wants executed",
    "sitting on a Force nexus the Banking Clan wants exploited",
    "training local resistance fighters against Separatist occupation",
    "hunting the same bounty as Qymaen — a race to the kill",
    "investigating the Geonosian cybernetic facility that augments Qymaen",
    "blocking access to a starship graveyard Qymaen needs for parts",
    "mediating a clan dispute that Qymaen's faction wants to escalate",
    "holding a Holocron that contains Kaleeh ancestral knowledge",
    "discovered the location of Ronderu lij Kummar's remains",
    "witnessed Qymaen's first cybernetic augmentation and could identify him",
    "leading a Republic survey team mapping Kaleeh sacred sites",
    "planted listening devices in the Temple of the Ancestors",
    "kidnapped a Kaleeh elder for interrogation about Separatist movements",
    "has information about a Huk resurgence that could threaten the armistice",
]

# ── Settings & Atmosphere ─────────────────────────────────────────────────

PLANET_TYPES = [
    "Jungle moon with ruins of an ancient civilization",
    "Desert world with glass-sand seas from orbital bombardment",
    "Ocean planet with floating cities and deep-sea trench temples",
    "Volcanic mining colony on the edge of the Outer Rim",
    "Asteroid field with a smuggler's den hollowed from a dead moon",
    "Gas giant upper atmosphere with floating refineries",
    "Tundra world with the frozen remains of a Clone Wars battle",
    "Urban ecumenopolis of towering spires and undercity slums",
    "Swamp planet with bioluminescent flora and submerged temples",
    "Canyon world carved by ancient rivers, now dry and windswept",
    "Crystal cave network beneath a barren planetary surface",
    "Ship graveyard on a tidally locked planet — dark side eternal night",
    "Ring habitat surrounding a dying star",
    "Necropolis world — a planet of mausoleums and bone cathedrals",
    "Savanah world with nomadic tribes and ancient standing stones",
    "Radioactive wasteland from a centuries-old nuclear war",
    "Artificial world built around a captive star",
]

ATMOSPHERIC_CONDITIONS = [
    "acid rain that sizzles on exposed metal",
    "perpetual twilight under a dying red sun",
    "electromagnetic storms that disrupt sensors and communication",
    "ash fall from constant volcanic activity",
    "fog so thick visibility is measured in meters",
    "razor-sharp silica dust carried by hundred-klick winds",
    "bioluminescent spore clouds that glow at night",
    "frozen nitrogen blizzards that flash-freeze exposed tissue",
    "oppressive humidity that coats everything in condensation",
    "pitch darkness broken only by lightning strikes",
    "sonic winds that scream through canyon networks",
    "micro-meteorite showers that ping off armor like rain",
    "magnetic anomalies that cause hallucinations in sensitive species",
    "atmosphere thin enough that stars are visible at noon",
]

LOCATION_DETAILS = [
    "a half-collapsed temple overgrown with phosphorescent vines",
    "the control room of a crashed Separatist dreadnought",
    "a cantina built into the ribcage of a dead space slug",
    "the throne room of a forgotten queen, preserved in carbonite",
    "a medbay where Geonosian cyber-surgeons work on living subjects",
    "the observation deck of a space elevator under siege",
    "a market square where droids trade in salvaged war memories",
    "the bridge of a Republic cruiser scuttled in a swamp",
    "a torture chamber repurposed as a meditation sanctum",
    "the heart of a plasma storm where a ship has been stranded for years",
    "a library of holographic records, slowly degrading",
    "a cathedral built from the hulls of destroyed starfighters",
    "the execution pit of a Huk war camp, still littered with bones",
    "an operating theater where Jedi survivors are studied",
]

# ── Story Arcs ────────────────────────────────────────────────────────────

STORY_ARC_TEMPLATES = [
    {
        "arc": "Ambush and Counter-Ambush",
        "conflict": "Qymaen walks into a Jedi trap, must reverse the hunter-hunted dynamic",
        "resolution": [ "outsmarts the Jedi through superior tactics", "turns the Jedi's own trap against them", "escapes with critical intelligence", "kills the Jedi but loses his extraction team" ],
        "transformation": "realizes the Separatists are using him as expendable muscle",
    },
    {
        "arc": "The Reluctant Alliance",
        "conflict": "Qymaen and the Jedi must cooperate against a common enemy (Huk remnant / pirates)",
        "resolution": [ "the Jedi sacrifices themselves so Qymaen can escape", "they part ways with mutual respect", "Qymaen betrays the Jedi at the last moment", "the Jedi tries to arrest Qymaen after the threat is neutralized" ],
        "transformation": "sees the Jedi as individuals, not just targets",
    },
    {
        "arc": "The Test of Faith",
        "conflict": "Qymaen's Kaleeh beliefs are challenged by Jedi philosophy in a spiritual confrontation",
        "resolution": [ "Qymaen reaffirms his ancestral faith, stronger than before", "he adopts a modified understanding of the Force", "the Jedi's sacrifice proves the ancestors were right all along", "Qymaen is left questioning everything he was taught" ],
        "transformation": "deepens his spiritual identity rather than abandoning it",
    },
    {
        "arc": "The Ghosts of the Past",
        "conflict": "A figure from Qymaen's pre-cybernetic life reappears, forcing him to confront who he was",
        "resolution": [ "he makes peace with the past and moves forward", "he destroys the memory and doubles down on the Gravedancer identity", "the figure dies, and Qymaen finally mourns them properly", "he learns the past cannot be reclaimed, only honored" ],
        "transformation": "integrates his past self with his present identity",
    },
    {
        "arc": "The Forge of War",
        "conflict": "A massive set-piece battle where the Jedi is one element among many on a chaotic battlefield",
        "resolution": [ "Qymaen kills the Jedi in the chaos, cold and efficient", "the Jedi escapes in the confusion", "they fight to a draw, both claiming tactical victories", "Qymaen saves the Jedi from a Separatist bombardment" ],
        "transformation": "sees the waste of war more clearly, but also his own skill",
    },
    {
        "arc": "The Descent",
        "conflict": "Qymaen must make an increasingly brutal choice to achieve his objective",
        "resolution": [ "he crosses the line and feels nothing — the worst outcome", "he refuses and finds another way, proving he still has limits", "he crosses the line and it haunts him", "the choice is made for him by circumstance" ],
        "transformation": "discovers whether he still has moral boundaries",
    },
    {
        "arc": "The Riddle of the Sith",
        "conflict": "A Sith artifact or Force anomaly in the setting complicates the hunt",
        "resolution": [ "the Jedi destroys the artifact at cost to themselves", "Qymaen claims the artifact for the Separatists", "the artifact is destroyed, and both walk away empty-handed", "the artifact corrupts the Jedi, and Qymaen must kill a fallen opponent" ],
        "transformation": "sees the Force as a tool of corruption, not just enlightenment",
    },
    {
        "arc": "The Siege",
        "conflict": "Qymaen lays siege to a fortified position the Jedi is defending",
        "resolution": [ "the fortress falls, the Jedi dies", "the siege is broken by Republic reinforcements", "Qymaen breaches the walls but the Jedi escapes through secret tunnels", "a negotiated ceasefire ends the siege inconclusively" ],
        "transformation": "learns patience and the cost of attrition warfare",
    },
    {
        "arc": "The Mirror",
        "conflict": "The Jedi mirrors Qymaen's own past — a warrior struggling with conscience",
        "resolution": [ "Qymaen kills them and sees his own future", "he spares them, breaking his pattern", "the Jedi is killed by someone else, robbing Qymaen of closure", "they recognize each other as kin in suffering, and part ways" ],
        "transformation": "confronts what he is becoming by seeing it in someone else",
    },
]

# ── Episode Title Fragments ───────────────────────────────────────────────

TITLE_PREFIXES = [
    "The", "A", "This", "An", "That", "The Last", "The First",
    "The Song of", "The Weight of", "The Shape of", "The Echo of",
    "The Price of", "The Art of", "The End of", "The Heart of",
]

TITLE_ADJECTIVES = [
    "Broken", "Burning", "Silent", "Falling", "Drowning", "Rising",
    "Forgotten", "Shattered", "Ashen", "Crimson", "Bone-white",
    "Iron", "Hollow", "Glass", "Obsidian", "Bleeding",
]

TITLE_NOUNS = [
    "Throne", "Mask", "Grave", "Fire", "Storm", "Blade",
    "Thorn", "Chain", "Crown", "Mirror", "Shadow", "Bone",
    "Salt", "Ash", "Dust", "Star", "Oath", "Debt",
    "Knot", "Door", "Bridge", "Wall", "Nail", "Root",
]

TITLE_SUFFIXES = [
    "of Solitude", "of Faith", "of War", "of Ash", "of Bone",
    "of Thunder", "of Salt", "of Mercy", "of Honour", "of Madness",
    "of the Fallen", "of the Forgotten", "of the Dead",
    "in the Dark", "in the Sand", "in the Rain",
    "at Dawn", "at Dusk", "at the Gate",
]

EPISODE_TITLE_TEMPLATES = [
    "{prefix} {adj} {noun}",
    "{prefix} {noun} of {suffix_word}",
    "{adj} {noun}",
    "{prefix} {noun}",
    "{prefix} {adj} {suffix}",
]

# ── Selectors ──────────────────────────────────────────────────────────────


def _pick_unique(exclude: list[str], pool: list[str], rng: random.Random) -> str:
    """Pick a value from *pool* not in *exclude*; if all are excluded, pick any."""
    candidates = [v for v in pool if v not in exclude]
    return rng.choice(candidates) if candidates else rng.choice(pool)


def generate_creative_seed(
    used_jedi_names: list[str] | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a structured creative seed from the randomization tables.

    Returns a dict that can be fed directly into the LLM expansion
    pipeline (concept → outline → story).
    """
    rng = random.Random(seed)

    # ── Title ──────────────────────────────────────────────────────────
    template = rng.choice(EPISODE_TITLE_TEMPLATES)
    prefix = rng.choice(TITLE_PREFIXES)
    adj = rng.choice(TITLE_ADJECTIVES)
    noun = rng.choice(TITLE_NOUNS)
    suffix_entry = rng.choice(TITLE_SUFFIXES)
    # strip "of" prefix from suffix if it starts with "of" for template expansion
    suffix_word = suffix_entry.removeprefix("of ").removeprefix("in ").removeprefix("at ")

    title_kwargs = {
        "prefix": prefix,
        "adj": adj,
        "noun": noun,
        "suffix": suffix_entry,
        "suffix_word": suffix_word,
    }

    # ── Jedi ───────────────────────────────────────────────────────────
    used = list(used_jedi_names or [])
    species = _pick_unique([], JEDI_SPECIES, rng)
    rank = rng.choice(JEDI_RANKS)
    saber = rng.choice(SABER_COLORS)
    personality = rng.choice(JEDI_PERSONALITY_TRAITS)
    why_targeted = rng.choice(JEDI_WHY_TARGETED)

    # Build a jedi name from fragments that fit the species, rerolling past
    # any name in the exclusion list (bounded; falls back to the last pick).
    jedi_first_pool = [
        "Solen", "Kaelen", "Vex'", "Thal", "Miren", "Jorak",
        "Lyra", "Venn", "Soral", "Kivan", "Rell", "Tavik",
        "Zara", "Nyx", "Oren", "Fael", "Dorn", "Ithiel",
    ]
    jedi_last_pool = [
        "Vex", "Korr", "Marr", "Venn", "Thal", "Rell",
        "Soral", "Nyxar", "Kivan", "Torr", "Fael", "Dorn",
    ]
    jedi_name = f"{rng.choice(jedi_first_pool)} {rng.choice(jedi_last_pool)}"
    for _ in range(10):
        if jedi_name not in used:
            break
        jedi_name = f"{rng.choice(jedi_first_pool)} {rng.choice(jedi_last_pool)}"

    # ── Setting ────────────────────────────────────────────────────────
    planet = rng.choice(PLANET_TYPES)
    atmosphere = rng.choice(ATMOSPHERIC_CONDITIONS)
    location = rng.choice(LOCATION_DETAILS)

    # ── Arc ────────────────────────────────────────────────────────────
    arc_template = rng.choice(STORY_ARC_TEMPLATES)
    resolution = rng.choice(arc_template["resolution"])

    # ── Tones (pick 2-4) ──────────────────────────────────────────────
    from src.utils.concepts import VALID_TONES
    tone_count = rng.randint(2, 4)
    tones = rng.sample(VALID_TONES, min(tone_count, len(VALID_TONES)))

    # ── Days ───────────────────────────────────────────────────────────
    num_days = rng.choice([4, 5, 5, 6])

    # ── Assemble ───────────────────────────────────────────────────────
    return {
        "seed": seed,
        "title": template.format(**title_kwargs),
        "num_days": num_days,
        "setting": f"{planet}. {atmosphere.capitalize()}. The primary action takes place at {location}.",
        "jedi_name": jedi_name,
        "jedi_species": species,
        "jedi_rank": rank,
        "jedi_lightsaber_color": saber,
        "jedi_personality": personality,
        "jedi_why_targeted": why_targeted,
        "tone_focus": tones,
        "story_arc": arc_template["arc"],
        "story_conflict": arc_template["conflict"],
        "story_resolution": resolution,
        "transformation_arc": arc_template["transformation"],
    }
