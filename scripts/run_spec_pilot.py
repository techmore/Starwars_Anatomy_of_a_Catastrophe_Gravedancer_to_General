"""Run and persist a spec-compliant three-day pilot with the local MLX model.

This is intentionally a creator-run script: the seed is visible, the concept
is generated and treated as approved for this requested run, and the episode
is only exported after structural checks pass.
"""

import json
import re
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.concepts import (
    build_concept_extraction_prompt,
    try_parse_full_episode_concept,
)
from src.utils.mlx_client import MLXClient
from src.utils.settings import SETTINGS
from src.utils.prompt_generator import PromptGenerator
from src.utils.storage import EpisodeStorage
from src.utils.story_generator import StoryGenerator
from src.utils.story_validator import deduplicate_story, strip_saved_episode_header, validate_story
from src.utils.prompt_schema import validate_outline_quality, validate_outline_structure


SEED = """A three-day pilot for an original, canon-adjacent survival-horror series.
Qymaen jai Sheelal, still living and only partly cybernetic, enters a ruined
Kaleesh bone-mining settlement during an acid storm to hunt an original Jedi
whose Force practice lets her hide wounded civilians from him. The settlement
is failing, something in the storm is imitating ancestral war chants, and the
Jedi understands that Qymaen's honor can be turned against him. The story must
create dread, tactical pursuit, body-cost horror, and a first compromise that
moves Qymaen toward the colder logic of Grievous. The Jedi does not have to
die; the ending should be a hard image or decision that launches the series.
Do not use canon Jedi, canon supporting characters, the Clone Wars, or a fully
formed General Grievous."""


# The LLM is still used for concept, prose, scene extraction, and visual
# prompts. This compact fallback keeps this named pilot runnable if an outline
# response is truncated or fails the anti-repetition gate.
PILOT_OUTLINE_FALLBACK = """## EPISODE ARC
Qymaen jai Sheelal enters a dying Kaleesh bone settlement to hunt an original Jedi who is shielding wounded civilians. The storm turns ancestral memory into a weapon, forcing Qymaen to choose between the honor of a visible duel and the efficient cruelty of controlling the battlefield. He leaves with living tissue damaged, an old vow compromised, and one colder tactic that points toward Grievous without making him fully cybernetic.

## DAY 1: The Storm Has a Voice
- Purpose: Establish the settlement, the false ancestral chant, the Jedi's protective philosophy, and Qymaen's first restraint.
- Chapter 1:
  - Beat 1: Qymaen breaches the rusted bone gate while acid eats the exposed servo housing in his right arm.
  - Beat 2: A chant rises from empty mine shafts and copies the cadence of a Kaleesh burial march.
  - Beat 3: He finds fresh footprints leading away from a collapsed clinic toward the lower extraction levels.
  - Beat 4: A dying miner warns that the storm has started speaking in the voices of the dead.
- Chapter 2:
  - Beat 1: Qymaen locates the wounded civilians beneath a Force shield in a buried chamber.
  - Beat 2: The original Jedi reveals herself by reinforcing the barrier instead of attacking him.
  - Beat 3: Qymaen tests the shield with one saber stroke and sees the Jedi divert the impact into the ceiling.
  - Beat 4: He refuses to kill a wounded civilian who falls into his reach and withdraws with acid burns across his mask.
- Chapter 3:
  - Beat 1: Qymaen climbs a broken crane spine to survey the settlement from above.
  - Beat 2: He maps three structural failures and realizes the Jedi is using the collapse as a countdown.
  - Beat 3: His damaged servo misfires and nearly throws him into an acid reservoir.
  - Beat 4: He marks a safe route through a flooded transit shaft and hears the Jedi move the civilians below.
- Chapter 4:
  - Beat 1: Qymaen crosses the transit shaft while bone dust turns to paste beneath his boots.
  - Beat 2: The Jedi redirects a collapsing conveyor away from the civilians and exposes her temporary refuge.
  - Beat 3: Qymaen reaches the refuge but chooses observation over a second attack.
  - Beat 4: The Jedi notices his restraint and names it as the last piece of his honor she can still reach.
- Chapter 5:
  - Beat 1: Qymaen plants a tracker on a moving medical crate without entering the shield.
  - Beat 2: The storm repeats Ronderu's name through the mine, using a voice Qymaen cannot dismiss.
  - Beat 3: He realizes the chant is drawing him toward a deeper extraction chamber rather than toward the Jedi.
  - Beat 4: He follows the voice, accepting that the hunt has become a test of memory as well as a mission.
- Ending hook: The storm speaks Qymaen's war name from beneath the settlement.

## DAY 2: The Mine Learns His Voice
- Purpose: Turn the settlement into a tactical maze, injure Qymaen, and force a costly but still human choice.
- Chapter 1:
  - Beat 1: Qymaen follows the tracker into an ossuary maze where old war masks hang from mining cables.
  - Beat 2: A droid scout receives a command in Qymaen's voice and walks willingly into an acid sink.
  - Beat 3: Qymaen discovers the storm is sampling speech from exposed comm lines and repeating it as bait.
  - Beat 4: The Jedi seals a passage behind him, turning the maze into a contest of patience.
- Chapter 2:
  - Beat 1: A group of civilians appears at a junction carrying a false signal from the Jedi.
  - Beat 2: Qymaen identifies one figure as a decoy by noticing that its breathing never changes in the acid mist.
  - Beat 3: The real Jedi attacks from a maintenance shaft while he shields the civilians from falling bone.
  - Beat 4: A hidden blade cuts the flesh around Qymaen's left knee before he can reach the attacker.
- Chapter 3:
  - Beat 1: Qymaen reaches a mining crane control room and studies the load paths instead of pursuing immediately.
  - Beat 2: He reroutes the crane to block the Jedi's escape without dropping the suspended civilians.
  - Beat 3: The machine tears free and destroys his only long-range weapon.
  - Beat 4: The Jedi recognizes that he sacrificed equipment rather than lives and changes her route.
- Chapter 4:
  - Beat 1: Qymaen and the Jedi meet on a bridge above a churning acid sump.
  - Beat 2: Their duel breaks into short exchanges as the bridge cables snap one by one.
  - Beat 3: The Jedi explains that protection is not mercy when it is chosen under pressure.
  - Beat 4: Qymaen loses leverage when his damaged knee locks, and the Jedi escapes with his cybernetic joint cracked.
- Chapter 5:
  - Beat 1: A collapse traps three miners on the far side of a sealed ore lift.
  - Beat 2: Qymaen can preserve the chase or tear open the lift and expose himself to the storm.
  - Beat 3: He rescues the miners, then hides a tracker inside the Jedi's discarded shield emitter.
  - Beat 4: The tracker leads toward the refinery heart where the settlement's oldest memory crystals are failing.
- Ending hook: The Jedi carries his tracker toward the place where the storm was born.

## DAY 3: The Last Human Calculation
- Purpose: Force the final choice between ancestral honor and efficient cruelty, then land on a hard transformation image.
- Chapter 1:
  - Beat 1: Acid floods the refinery floor while the remaining civilians gather behind the Jedi's weakening shield.
  - Beat 2: Qymaen reaches the control deck and sees that one valve can save the chamber only by sealing another.
  - Beat 3: The storm uses Ronderu's voice to offer him a route that bypasses the civilians.
  - Beat 4: Qymaen rejects the voice and enters the refinery through the wounded machinery.
- Chapter 2:
  - Beat 1: The Jedi admits the storm is amplifying ancestral memory through the settlement's crystal supports.
  - Beat 2: She offers Qymaen the civilians' release if he abandons the hunt and leaves his weapon behind.
  - Beat 3: Qymaen discovers the offer is sincere but would leave the Jedi free to warn the settlement's enemies.
  - Beat 4: He chooses to continue the hunt while promising himself that no civilian will become a bargaining chip.
- Chapter 3:
  - Beat 1: Qymaen builds a breach from the refinery's pressure plates and his own damaged servo.
  - Beat 2: The test tears living tissue from his forearm and leaves the joint moving with a new metallic tremor.
  - Beat 3: He uses the breach to split the shield without striking the civilians.
  - Beat 4: The Jedi is forced into the open beside the failing memory core.
- Chapter 4:
  - Beat 1: The final confrontation moves through pipes, sparks, and waist-deep acid as the core begins to rupture.
  - Beat 2: The Jedi chooses to hold the shield for the civilians instead of taking the killing angle.
  - Beat 3: Qymaen can end the duel cleanly or use the shield's strain to disable her permanently.
  - Beat 4: He chooses the efficient strike, then catches the civilians before the core collapses.
- Chapter 5:
  - Beat 1: The Jedi survives but cannot pursue, trapped beneath the sealed refinery gate with her lightsaber out of reach.
  - Beat 2: Qymaen retrieves the weapon and refuses to return it, calling the theft a necessary measure.
  - Beat 3: The storm falls silent as the memory core burns out and the settlement's dead become only dead again.
  - Beat 4: Qymaen replaces the ruined servo with a harsher temporary brace and walks away from the rescued civilians.
- Ending hook: In the black reflection of the stolen saber, Qymaen sees the first shape of the mask he will one day wear.
"""

PILOT_JEDI_FALLBACK = {
    "name": "Sura Venn",
    "species": "Togruta",
    "rank": "Jedi Knight",
    "lightsaber_color": "amber",
    "personality": "protective, calculating, exhausted, and unwilling to abandon civilians",
    "why_targeted": "uses a rare shielding practice to hide wounded civilians from Qymaen's pursuit",
}


def _dedupe_concept_text(text: str) -> str:
    """Keep concept context useful when a local model repeats its answer."""
    paragraphs = []
    seen = set()
    for paragraph in re.split(r"\n\s*\n", str(text or "")):
        normalized = re.sub(r"\s+", " ", paragraph.strip())
        if normalized and normalized not in seen:
            seen.add(normalized)
            paragraphs.append(paragraph.strip())
    return "\n\n".join(paragraphs[:3])


def _complete_visual_variants(visual: dict, scene: dict) -> tuple[dict, bool]:
    """Fill missing Draw Things shots without inventing story facts."""
    scene_text = str(scene.get("text") or "").strip()
    descriptors = {
        "wide": "wide establishing shot, environmental scale, cinematic atmosphere",
        "medium": "medium action shot, character movement, tactical interaction",
        "closeup": "close-up detail shot, face, mask, eyes, cybernetics, and texture",
        "dramatic": "dramatic low-angle shot, menace, rim light, and hard shadows",
        "alternate": "alternate concept-art storyboard frame with restrained cinematic color",
    }
    recovered = False
    for key, descriptor in descriptors.items():
        if not str(visual.get(key) or "").strip():
            visual[key] = f"{descriptor}. Preserve the narrative facts in this scene: {scene_text}"
            recovered = True
    return visual, recovered


def _concept(client: MLXClient) -> tuple[dict, str]:
    concept_text = client.generate(
        model,
        f"Create a vivid 2-4 paragraph concept proposal from this creator seed. "
        f"Keep it a three-day pilot and make all invented backstory provisional. "
        f"Use survival horror and dread as the dominant tone.\n\nSEED:\n{SEED}",
        system="You are the concept editor for a serialized survival-horror space opera. Output only the concept proposal.",
        temperature=0.7,
        max_tokens=1100,
    )
    structured = client.generate(
        model,
        build_concept_extraction_prompt(concept_text),
        system="Return only valid JSON. Do not include reasoning or markdown.",
        temperature=0.2,
        max_tokens=900,
    )
    concept_text = _dedupe_concept_text(concept_text)
    concept, errors = try_parse_full_episode_concept(structured, fallback_text=concept_text)
    if errors:
        raise RuntimeError(f"Concept did not satisfy the structured contract: {errors}")
    concept["days"] = 3
    concept["tone"] = ["Survival horror", "Transformation focus", "Narrow escapes"]
    required = ("title", "setting", "jedi_name", "jedi_species", "jedi_rank", "jedi_saber", "jedi_personality", "jedi_target")
    missing = [field for field in required if not str(concept.get(field, "")).strip()]
    if missing:
        raise RuntimeError(f"Concept is missing required fields: {missing}")
    target_name = str(concept.get("jedi_name", "")).lower()
    if any(term in target_name for term in ("qymaen", "grievous", "gravedancer")):
        concept.update({
            "jedi_name": PILOT_JEDI_FALLBACK["name"],
            "jedi_species": PILOT_JEDI_FALLBACK["species"],
            "jedi_rank": PILOT_JEDI_FALLBACK["rank"],
            "jedi_saber": PILOT_JEDI_FALLBACK["lightsaber_color"],
            "jedi_personality": PILOT_JEDI_FALLBACK["personality"],
            "jedi_target": PILOT_JEDI_FALLBACK["why_targeted"],
            "concept_recovery": "invalid protagonist-as-Jedi output replaced with creator-approved pilot target",
        })
    return concept, concept_text


_last_progress_chars: dict[str, int] = {}


def _progress(stage: str, message: str, text: str = "") -> None:
    previous = _last_progress_chars.get(stage, 0)
    if (len(text) - previous >= 1000) or message.endswith("ready."):
        _last_progress_chars[stage] = len(text)
        print(f"[{stage}] {message} ({len(text):,} chars)", flush=True)


def main() -> None:
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", default=SETTINGS.model,
        help="Model identifier, including lmstudio:<id> for LM Studio.",
    )
    parser.add_argument(
        "--storage-path", default=str(SETTINGS.storage_path),
        help="Episode storage directory (default: repository episodes/).",
    )
    parser.add_argument(
        "--resume-episode",
        help="Resume a staged pilot episode using its saved concept and outline.",
    )
    parser.add_argument(
        "--finalize-episode",
        help="Clean and finalize a generated episode without regenerating its story.",
    )
    args = parser.parse_args()

    model = args.model
    client = MLXClient(model)
    storage = EpisodeStorage(args.storage_path)
    story_generator = StoryGenerator(client)
    prompt_generator = PromptGenerator(client)

    if not model.startswith("lmstudio:") and (
        not client.is_model_available_locally(model)
        or not client.is_model_supported_by_runtime(model)
    ):
        raise RuntimeError(f"The configured model/runtime is not ready: {model}")

    if args.finalize_episode:
        episode_id = args.finalize_episode
        loaded = storage.load_episode(episode_id)
        if not loaded or not loaded.get("story"):
            raise RuntimeError(f"Finalize episode has no saved story: {episode_id}")
        story, cleanup = deduplicate_story(strip_saved_episode_header(loaded["story"]))
        report = validate_story(story, expected_days=3)
        day_heading_count = len(re.findall(r"^##\s*DAY\s+\d+", story, re.MULTILINE | re.IGNORECASE))
        chapter_heading_count = len(re.findall(r"^###\s+Chapter\s+\d+", story, re.MULTILINE | re.IGNORECASE))
        required_terms = {term: bool(re.search(rf"\b{re.escape(term)}\b", story, re.IGNORECASE)) for term in ("Qymaen", "Gravedancer", "Kaleesh", "Ronderu")}
        storage.update_episode(episode_id, story=story, metadata={
            "story_cleanup": cleanup,
            "story_validation": {"word_count": report["word_count"], "warnings": report["warnings"], "day_heading_count": day_heading_count, "chapter_heading_count": chapter_heading_count, "required_terms": required_terms},
            "story_validation_status": "passed" if not report["warnings"] and day_heading_count == 3 and chapter_heading_count >= 15 and all(required_terms.values()) else "failed",
        })
        if report["warnings"] or day_heading_count != 3 or chapter_heading_count < 15 or not all(required_terms.values()):
            raise RuntimeError(json.dumps({"story_report": report, "cleanup": cleanup}, indent=2))
        scenes = prompt_generator.extract_scenes(story, max_scenes_per_day=1)
        if len(scenes) < 3:
            raise RuntimeError(f"Expected at least one visual scene per day; extracted {len(scenes)}")
        scene_prompts = []
        for scene in scenes[:3]:
            visual = prompt_generator.generate_scene_prompts(scene_text=scene["text"], day_number=scene["day"], model=model, beat_label=scene.get("beat_label", ""), aspect_ratio="16:9", temperature=0.6)
            visual, recovered = _complete_visual_variants(visual, scene)
            if recovered:
                visual["prompt_recovery"] = "missing model shot variants filled from extracted scene text"
            visual.update({key: scene.get(key) for key in ("paragraph_index", "beat_label", "display_title", "visual_score", "text")})
            scene_prompts.append(visual)
        storage.update_episode(episode_id, prompts={"scenes": scene_prompts, "model": model, "aspect_ratio": "16:9", "pipeline": "story-success-spec-pilot-v1"}, metadata={"visual_prompts_validated": True, "visual_prompt_recovery_used": any(item.get("prompt_recovery") for item in scene_prompts)})
        bundle = storage.write_episode_bundle(episode_id)
        archive = storage.write_episode_archive(episode_id)
        reloaded = storage.load_episode(episode_id)
        if not reloaded or not reloaded.get("prompts", {}).get("scenes"):
            raise RuntimeError("Saved episode failed reload validation")
        metadata_path = storage.episode_metadata_path(episode_id)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["completed_at"] = datetime.now().isoformat()
        metadata["elapsed_seconds"] = round(time.perf_counter() - started, 1)
        storage.update_episode(episode_id, metadata=metadata)
        print(f"RUN_COMPLETE episode_id={episode_id}", flush=True)
        print(f"BUNDLE={bundle}", flush=True)
        print(f"ARCHIVE={archive}", flush=True)
        print(f"STORY_WORDS={report['word_count']}", flush=True)
        print(f"SCENES={len(scene_prompts)}", flush=True)
        return

    resume_metadata = None
    outline = None
    if args.resume_episode:
        metadata_path = storage.episode_metadata_path(args.resume_episode)
        if not metadata_path.is_file():
            raise RuntimeError(f"Resume episode metadata not found: {args.resume_episode}")
        resume_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        concept = resume_metadata.get("concept_proposal") or {}
        concept_text = str(resume_metadata.get("concept_text") or "")
        title = str(resume_metadata.get("title") or concept.get("title") or "").strip()
        outline = str(resume_metadata.get("outline") or "").strip()
        jedi_details = dict(resume_metadata.get("jedi_details") or {})
        if not title or not outline or not jedi_details:
            raise RuntimeError("Resume episode is missing title, outline, or Jedi details.")
        episode_id = args.resume_episode
        print(f"RESUMING_EPISODE_ID={episode_id}", flush=True)
    else:
        concept, concept_text = _concept(client)
        title = concept["title"]
        jedi_details = {
            "name": concept["jedi_name"],
            "species": concept["jedi_species"],
            "rank": concept["jedi_rank"],
            "lightsaber_color": concept["jedi_saber"],
            "personality": concept["jedi_personality"],
            "why_targeted": concept["jedi_target"],
        }
    additional = f"""APPROVED PILOT SEED:
{SEED}

CONCEPT PROPOSAL (approved for this run; invented facts remain episode-scoped):
{concept_text}

Hard story constraints:
- Qymaen jai Sheelal is the protagonist; use Qymaen and Gravedancer naturally.
- He is a living Kaleesh warlord with an ancestral bone mask and early cybernetics,
  not a finished General Grievous.
- Make survival horror and dread the dominant experience, with tactical combat
  and body-cost consequences.
- Use the original Jedi below as a capable antagonist with a philosophy and
  choice. Do not use canon Jedi, Clone Wars events, or generic replacement heroes.
- Preserve injuries, equipment, locations, emotional state, and tactical position.
- Every day must end with a hook; the final day must land on a hard image or decision.
- A Jedi death is optional and must follow the approved concept.

Mandatory non-repeating scene map (the outline must preserve these distinct
chapter purposes; do not copy one chapter's beats into another):
- Day 1 / Chapter 1: breach the settlement, discover the storm's false chant,
  and find evidence that civilians are being moved through the mine.
- Day 1 / Chapter 2: first contact at the civilian shield; Qymaen chooses not
  to kill a wounded person and withdraws with acid damage.
- Day 1 / Chapter 3: reconnaissance from a crane spine; Qymaen maps structural
  failures and learns the Jedi is using the collapse as a clock.
- Day 1 / Chapter 4: cross the flooded transit shaft; the Jedi redirects a
  collapse to save civilians, exposing a temporary route.
- Day 1 / Chapter 5: Qymaen marks that route and hears the storm use Ronderu's
  name; the hook is a choice to follow the voice instead of the Jedi.
- Day 2 / Chapter 1: pursue the marked route into an ossuary maze and lose a
  droid scout to an imitation of Qymaen's own command voice.
- Day 2 / Chapter 2: the Jedi's empathy trap forces Qymaen to identify which
  civilian is bait; he is wounded while refusing the obvious kill.
- Day 2 / Chapter 3: Qymaen turns a mining crane into a counter-trap and
  sacrifices equipment, not civilians, to split the pursuit.
- Day 2 / Chapter 4: a short duel on a collapsing bridge reveals the Jedi's
  philosophy and leaves Qymaen with a damaged cybernetic joint.
- Day 2 / Chapter 5: Qymaen can rescue trapped miners or preserve the chase;
  he saves them but plants a tracker in the Jedi's escape route.
- Day 3 / Chapter 1: the refinery begins to flood with acid and the remaining
  civilians are trapped behind the Jedi's failing shield.
- Day 3 / Chapter 2: the Jedi reveals the storm is amplifying ancestral
  memory, and offers Qymaen a way to end the hunt without slaughter.
- Day 3 / Chapter 3: Qymaen tests a brutal breach that costs living tissue and
  proves the cold tactical solution works.
- Day 3 / Chapter 4: final confrontation at the refinery heart; the Jedi makes
  a defining choice and Qymaen must choose between honor and efficiency.
- Day 3 / Chapter 5: land on one hard image/decision that advances him toward
  Grievous without making him fully cybernetic or invoking the Clone Wars.
- No beat may repeat an event, location, action, or sentence from another
  chapter. Each chapter must contain four forward-moving beats.
"""
    metadata = dict(resume_metadata or {})
    metadata.update({
        "num_days": 3,
        "setting": str(metadata.get("setting") or concept["setting"]),
        "jedi_name": str(metadata.get("jedi_name") or concept["jedi_name"]),
        "target_jedi_name": str(metadata.get("target_jedi_name") or concept["jedi_name"]),
        "jedi_details": jedi_details,
        "tone_focus": concept["tone"],
        "model": model,
        "concept_proposal": concept,
        "concept_text": concept_text,
        "concept_approved": True,
        "concept_approved_for": "Requested spec-compliant pilot run",
        "seed": SEED,
        "pipeline": "story-success-spec-pilot-v1",
    })
    if not args.resume_episode:
        episode_id = storage.save_episode(title, "", metadata)
        print(f"EPISODE_ID={episode_id}", flush=True)
    print(f"CONCEPT_TITLE={title}", flush=True)
    print(f"CONCEPT_JEDI={concept['jedi_name']}", flush=True)

    if not outline:
        outline = story_generator.generate_episode_outline(
            model=model,
            title=title,
            num_days=3,
            jedi_details=jedi_details,
            setting=concept["setting"],
            tone_focus=concept["tone"],
            additional_instructions=additional,
            temperature=0.45,
            progress_callback=_progress,
        )
    outline_errors = validate_outline_structure(outline, expected_days=3)
    outline_errors += validate_outline_quality(outline, expected_days=3)
    outline_source = "llm"
    if outline_errors:
        print(f"OUTLINE_REJECTED errors={outline_errors}; using curated pilot fallback", flush=True)
        outline = PILOT_OUTLINE_FALLBACK
        fallback_errors = validate_outline_structure(outline, expected_days=3)
        fallback_errors += validate_outline_quality(outline, expected_days=3)
        if fallback_errors:
            raise RuntimeError(f"Curated pilot outline failed validation: {fallback_errors}")
        outline_source = "curated-fallback"
    storage.update_episode(episode_id, metadata={
        "outline": outline,
        "outline_validated": True,
        "outline_source": outline_source,
        "outline_generation_errors": outline_errors,
    })
    print(f"OUTLINE_OK chars={len(outline):,}", flush=True)

    story = story_generator.generate_episode_story_multi_pass(
        model=model,
        title=title,
        num_days=3,
        jedi_details=jedi_details,
        setting=concept["setting"],
        tone_focus=concept["tone"],
        additional_instructions=additional,
        temperature=0.72,
        outline=outline,
        progress_callback=_progress,
    )
    story, cleanup = deduplicate_story(story)
    report = validate_story(story, expected_days=3)
    day_heading_count = len(re.findall(r"^##\s*DAY\s+\d+", story, re.MULTILINE | re.IGNORECASE))
    chapter_heading_count = len(re.findall(r"^###\s+Chapter\s+\d+", story, re.MULTILINE | re.IGNORECASE))
    required_terms = {term: bool(re.search(rf"\b{re.escape(term)}\b", story, re.IGNORECASE)) for term in ("Qymaen", "Gravedancer", "Kaleesh", "Ronderu")}
    validation_metadata = {
        "story_generated": True,
        "story_cleanup": cleanup,
        "story_validation": {
            "word_count": report["word_count"],
            "warnings": report["warnings"],
            "day_heading_count": day_heading_count,
            "chapter_heading_count": chapter_heading_count,
            "required_terms": required_terms,
        },
    }
    # Checkpoint the expensive generation before applying the hard quality gate.
    # A failed validation must never discard an otherwise inspectable local run.
    storage.update_episode(episode_id, story=story, metadata=validation_metadata)
    if report["warnings"] or day_heading_count != 3 or chapter_heading_count < 15 or not all(required_terms.values()):
        storage.update_episode(episode_id, metadata={"story_validation_status": "failed"})
        raise RuntimeError(json.dumps({
            "story_report": report,
            "day_heading_count": day_heading_count,
            "chapter_heading_count": chapter_heading_count,
            "required_terms": required_terms,
        }, indent=2))
    storage.update_episode(episode_id, story=story, metadata={
        "story_validation_status": "passed",
        "story_validated": True,
        "story_validation": {
            "word_count": report["word_count"],
            "day_heading_count": day_heading_count,
            "chapter_heading_count": chapter_heading_count,
            "required_terms": required_terms,
        },
    })
    print(f"STORY_OK words={report['word_count']:,} chapters={chapter_heading_count}", flush=True)

    scenes = prompt_generator.extract_scenes(story, max_scenes_per_day=1)
    if len(scenes) < 3:
        raise RuntimeError(f"Expected at least one visual scene per day; extracted {len(scenes)}")
    scene_prompts = []
    for scene in scenes[:3]:
        visual = prompt_generator.generate_scene_prompts(
            scene_text=scene["text"], day_number=scene["day"], model=model,
            beat_label=scene.get("beat_label", ""), aspect_ratio="16:9", temperature=0.6,
        )
        visual, recovered = _complete_visual_variants(visual, scene)
        if recovered:
            visual["prompt_recovery"] = "missing model shot variants filled from extracted scene text"
        visual.update({key: scene.get(key) for key in ("paragraph_index", "beat_label", "display_title", "visual_score", "text")})
        scene_prompts.append(visual)
    storage.update_episode(episode_id, prompts={
        "scenes": scene_prompts,
        "model": model,
        "aspect_ratio": "16:9",
        "pipeline": "story-success-spec-pilot-v1",
    }, metadata={"visual_prompts_validated": True, "visual_prompt_recovery_used": any(item.get("prompt_recovery") for item in scene_prompts)})
    bundle = storage.write_episode_bundle(episode_id)
    archive = storage.write_episode_archive(episode_id)
    loaded = storage.load_episode(episode_id)
    if not loaded or not loaded.get("prompts", {}).get("scenes"):
        raise RuntimeError("Saved episode failed reload validation")
    metadata_path = storage.episode_metadata_path(episode_id)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["completed_at"] = datetime.now().isoformat()
    metadata["elapsed_seconds"] = round(time.perf_counter() - started, 1)
    storage.update_episode(episode_id, metadata=metadata)
    print(f"RUN_COMPLETE episode_id={episode_id}", flush=True)
    print(f"BUNDLE={bundle}", flush=True)
    print(f"ARCHIVE={archive}", flush=True)
    print(f"STORY_WORDS={report['word_count']}", flush=True)
    print(f"SCENES={len(scene_prompts)}", flush=True)


if __name__ == "__main__":
    main()
