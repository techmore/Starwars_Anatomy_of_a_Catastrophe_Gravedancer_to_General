#!/usr/bin/env python3
"""Publish a finished pipeline episode to the Gravedancer_to_General site repo.

Converts an episode directory from this pipeline repo (metadata.json + story.md)
into the site's single-file format (episodes/NN-slug.md with YAML frontmatter),
validates it, commits, and pushes — triggering the GitHub Pages deploy.

Gate: only episodes whose metadata carries ``pipeline_complete: true`` are
publishable (stamped automatically by run_creative_pipeline.py at the end of a
successful run). Older finished runs can be gated in retroactively with
``--mark-complete`` after structural validation.

Usage:
    python scripts/publish_episode.py episodes/episode-...-hash \
        [--publish | --status draft] [--episode N] [--tagline "..."]
        [--jedi-fate "..."] [--no-push] [--dry-run] [--mark-complete]

    python scripts/publish_episode.py --unpublish 01-hollow-bridge
    python scripts/publish_episode.py --retire 01-hollow-bridge   # flip to draft
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

LOGGER = logging.getLogger("publish_episode")

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE_REPO = Path("~/Projects/Gravedancer_to_General").expanduser()

DAY_HEADER_RE = re.compile(r"^##\s+DAY\s+(\d+)\s*:\s*(.+)$", re.MULTILINE)
SOURCE_TAG_RE = re.compile(r"<!--\s*gravedancer-pipeline-source:\s*(\S+)\s*-->")
MIN_WORDS = 5_000  # sanity floor: a full 6-day episode is ~20k+ words


# ── helpers ───────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """URL-friendly slug, mirroring the site build's slugify()."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def load_metadata(episode_dir: Path) -> dict:
    path = episode_dir / "metadata.json"
    if not path.exists():
        sys.exit(f"error: no metadata.json in {episode_dir}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_story_body(episode_dir: Path) -> str:
    """Return story.md minus the pipeline preamble (title/Generated/Days block).

    Everything before the first '## DAY N:' header is pipeline bookkeeping;
    the site computes its own word counts and takes metadata from frontmatter.
    """
    path = episode_dir / "story.md"
    if not path.exists():
        sys.exit(f"error: no story.md in {episode_dir}")
    text = path.read_text(encoding="utf-8")
    match = DAY_HEADER_RE.search(text)
    if not match:
        sys.exit(
            "error: story.md has no '## DAY N:' headers — refusing to "
            "publish something that does not match the reader format."
        )
    return text[match.start():].strip()


def site_episodes(site_repo: Path) -> dict[str, dict]:
    """Map site episode filename -> parsed frontmatter."""
    out: dict[str, dict] = {}
    ep_dir = site_repo / "episodes"
    if not (site_repo / "build.py").exists():
        sys.exit(f"error: {site_repo} does not look like the site repo (no build.py)")
    if not ep_dir.is_dir():
        return out  # empty archive is valid
    for path in sorted(ep_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        try:
            meta = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            meta = {}
        out[path.name] = meta if isinstance(meta, dict) else {}
    return out


def next_episode_number(episodes: dict[str, dict]) -> int:
    numbers = [
        int(m["episode"]) for m in episodes.values()
        if isinstance(m.get("episode"), int)
    ]
    return max(numbers, default=0) + 1


def find_existing_source(site_repo: Path, source_id: str) -> str | None:
    """Scan site episodes for the pipeline-source tag (idempotent updates)."""
    for path in sorted((site_repo / "episodes").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = SOURCE_TAG_RE.search(text)
        if m and m.group(1) == source_id:
            return path.name
    return None


def resolve_site_target(site_repo: Path, slug_or_name: str) -> Path:
    """Accept '01-hollow-bridge' or '01-hollow-bridge.md'."""
    name = slug_or_name if slug_or_name.endswith(".md") else f"{slug_or_name}.md"
    path = site_repo / "episodes" / name
    if not path.exists():
        sys.exit(f"error: {path} not found in site repo")
    return path


# ── completion gate ───────────────────────────────────────────────────────

def ensure_complete(episode_dir: Path, metadata: dict, mark: bool) -> None:
    if metadata.get("pipeline_complete"):
        return
    if not mark:
        sys.exit(
            f"error: '{metadata.get('title', episode_dir.name)}' has no "
            "pipeline_complete marker — the run never reached PIPELINE "
            "COMPLETE. Re-run the pipeline, or pass --mark-complete to "
            "validate this older run structurally and stamp it."
        )
    body = load_story_body(episode_dir)
    days = set(int(m.group(1)) for m in DAY_HEADER_RE.finditer(body))
    expected = int(metadata.get("num_days") or 0)
    words = len(body.split())
    problems = []
    if expected and days != set(range(1, expected + 1)):
        problems.append(f"days present {sorted(days)} != expected 1..{expected}")
    if words < MIN_WORDS:
        problems.append(f"only {words:,} words (< {MIN_WORDS:,}) — truncated run?")
    if problems:
        sys.exit("error: --mark-complete refused:\n  - " + "\n  - ".join(problems))
    stamp_completion(episode_dir, metadata, word_count=words, num_days=len(days))
    print(f"  Stamped pipeline_complete into {episode_dir.name}/metadata.json")


def stamp_completion(episode_dir: Path, metadata: dict,
                     word_count: int, num_days: int) -> None:
    now = dt.datetime.now().isoformat()
    metadata["pipeline_complete"] = True
    metadata["pipeline_completed_at"] = now
    metadata["word_count"] = word_count
    metadata["num_days"] = num_days
    metadata["updated_at"] = now
    path = episode_dir / "metadata.json"
    fd, tmp = tempfile.mkstemp(dir=str(episode_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ── conversion ────────────────────────────────────────────────────────────

def build_frontmatter(metadata: dict, body: str, number: int, *,
                      status: str, tagline: str | None,
                      jedi_fate: str | None, published_at) -> dict:
    fate = jedi_fate_or_default(metadata, jedi_fate)
    fm = {
        "title": metadata.get("title", "Untitled"),
        "episode": number,
        "target_jedi": metadata.get("jedi_name")
                       or metadata.get("target_jedi_name") or "Unknown",
        "jedi_species": metadata.get("jedi_species", "Unknown"),
        "jedi_fate": fate,
        "setting": metadata.get("setting", "Unknown"),
        "status": status,
    }
    if tagline:
        fm["tagline"] = tagline
    if status == "published":
        fm["published_at"] = published_at
    return fm


def jedi_fate_or_default(metadata: dict, override: str | None) -> str:
    if override:
        return override
    resolution = (metadata.get("story_resolution") or "").lower()
    if any(word in resolution for word in ("kill", "slay", "death", "die")):
        return "Killed"  # conservative label; refine via --jedi-fate
    return "Unresolved"


def render_episode_md(fm: dict, body: str, source_id: str) -> str:
    front = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True,
                           default_flow_style=False).strip()
    return f"---\n{front}\n---\n\n{body}\n\n<!-- gravedancer-pipeline-source: {source_id} -->\n"


def install_cover(site_repo: Path, episode_dir: Path, slug: str) -> str | None:
    """Copy the episode's banner art into the site as assets/img/<slug>/cover.jpg.

    Returns the site-relative frontmatter value, or None when the episode has
    no generated art. PNG -> JPEG (quality 85, max width 1400) keeps the site
    repo light; Pages serves it fine either way.
    """
    dest = _convert_to_site_img(
        _pick_cover_source(episode_dir),
        site_repo / "assets" / "img" / slug / "cover.jpg",
        slug,
    )
    return dest


def _pick_cover_source(episode_dir: Path) -> Path | None:
    images_dir = episode_dir / "images"
    if images_dir.is_dir():
        # Banner/cover first, then earliest day plate as fallback.
        candidates = sorted(images_dir.glob("*banner*.png")) or \
            sorted(images_dir.glob("day-00-*.png")) or \
            sorted(images_dir.glob("*.png"))
        if candidates:
            return candidates[0]
    return None


def install_day_plates(site_repo: Path, episode_dir: Path, slug: str) -> dict[int, str]:
    """Copy each day's hero art into the site as assets/img/<slug>/day-NN.jpg.

    Returns {day_number: site-relative path} for frontmatter ``plates:``.
    """
    plates: dict[int, str] = {}
    images_dir = episode_dir / "images"
    if not images_dir.is_dir():
        return plates
    for src in sorted(images_dir.glob("day-*-*-hero.png")):
        m = re.match(r"day-(\d+)-", src.name)
        if not m:
            continue
        day = int(m.group(1))
        dest = site_repo / "assets" / "img" / slug / f"day-{day:02d}.jpg"
        if _convert_to_site_img(src, dest, slug):
            plates[day] = f"assets/img/{slug}/day-{day:02d}.jpg"
    return plates


def _convert_to_site_img(src: Path | None, dest: Path, slug: str) -> str | None:
    if src is None:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
        resample = getattr(Image, "Resampling", Image).LANCZOS
        with Image.open(src) as im:
            im = im.convert("RGB")
            if im.width > 1400:
                ratio = 1400 / im.width
                im = im.resize((1400, round(im.height * ratio)), resample)
            im.save(dest, "JPEG", quality=85, optimize=True)
    except ImportError:
        shutil.copyfile(src, dest.with_suffix(".png"))
        return f"assets/img/{slug}/{dest.stem}.png"
    return f"assets/img/{slug}/{dest.name}"


def install_downloads(site_repo: Path, episode_dir: Path, slug: str) -> dict[str, str]:
    """Install ebook downloads into the site as assets/downloads/<slug>/.

    EPUB is copied from the episode's auto-export when present; the PDF is
    generated fresh from story.md so it always matches what's being published.
    Returns {format: site-relative path} for frontmatter ``downloads:``.
    """
    sys.path.insert(0, str(PIPELINE_ROOT))
    from src.utils.export_formats import to_pdf_bytes
    from src.utils.export_hook import _collect_episode_images

    out: dict[str, str] = {}
    dest_dir = site_repo / "assets" / "downloads" / slug
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Name-stamp + date-stamp downloads so saved files are self-describing,
    # e.g. 2026-08-23-forgotten-chain.epub
    created = str(load_metadata(episode_dir).get("created_at") or "")[:10]
    date_part = created if re.match(r"\d{4}-\d{2}-\d{2}", created) else \
        dt.date.today().isoformat()
    stem = f"{date_part}-{slug}"
    # This directory is owned by the publisher.  Remove both the original
    # unsuffixed names and prior date-stamped exports so republishing does not
    # leave stale download links in the site tree.
    for stale in dest_dir.iterdir():
        if stale.is_file() and (
            stale.name.startswith("episode.")
            or stale.suffix.lower() in {".epub", ".pdf"}
        ):
            stale.unlink()

    epubs = sorted(episode_dir.glob("*.epub"))
    if epubs:
        dest = dest_dir / f"{stem}.epub"
        shutil.copyfile(epubs[0], dest)
        out["epub"] = f"assets/downloads/{slug}/{dest.name}"

    metadata = load_metadata(episode_dir)
    story_path = episode_dir / "story.md"
    cover_src = _pick_cover_source(episode_dir)
    cover = None
    if cover_src:
        try:
            cover = cover_src.read_bytes()
        except OSError:
            cover = None
    pdf_bytes = to_pdf_bytes(
        metadata.get("title", "Episode"),
        story_path.read_text(encoding="utf-8"),
        metadata,
        cover_image=cover,
        images=_collect_episode_images(episode_dir),
    )
    pdf_dest = dest_dir / f"{stem}.pdf"
    pdf_dest.write_bytes(pdf_bytes)
    out["pdf"] = f"assets/downloads/{slug}/{pdf_dest.name}"
    return out


def validate(fm: dict, rendered: str) -> list[str]:
    problems = []
    required = ["title", "episode", "target_jedi", "setting", "status"]
    for key in required:
        if not fm.get(key):
            problems.append(f"frontmatter missing '{key}'")
    if fm.get("status") == "published" and not fm.get("published_at"):
        problems.append("published status requires published_at")
    if "**Generated:**" in rendered.split("---", 2)[-1][:400]:
        problems.append("pipeline preamble leaked into body")
    if not DAY_HEADER_RE.search(rendered):
        problems.append("no DAY headers survived conversion")
    return problems


# ── git ───────────────────────────────────────────────────────────────────

def run_git(site_repo: Path, *args: str, check: bool = True) -> str:
    import subprocess
    result = subprocess.run(
        ["git", "-C", str(site_repo), *args],
        capture_output=True, text=True,
    )
    if check and result.returncode != 0:
        sys.exit(f"error: git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return (result.stdout + result.stderr).strip()


# ── main actions ──────────────────────────────────────────────────────────

def action_publish(args: argparse.Namespace) -> None:
    episode_dir = Path(args.episode_dir).expanduser().resolve()
    site_repo = Path(args.site_repo).expanduser().resolve()

    metadata = load_metadata(episode_dir)
    ensure_complete(episode_dir, metadata, mark=args.mark_complete)

    body = load_story_body(episode_dir)
    words = len(body.split())
    if words < MIN_WORDS:
        print(f"warning: body is only {words:,} words "
              f"(<{MIN_WORDS:,}) — possibly truncated.", flush=True)

    # Synchronize before numbering or writing anything.  A dry run must stay
    # read-only, including avoiding a local pull that changes the checkout.
    if not args.dry_run:
        run_git(site_repo, "pull", "--ff-only")
    episodes = site_episodes(site_repo)
    source_id = episode_dir.name
    existing = find_existing_source(site_repo, source_id)

    if args.episode:
        number = args.episode
    elif existing:
        number = int(episodes[existing].get("episode") or next_episode_number(episodes))
    else:
        number = next_episode_number(episodes)

    status = args.status
    today = dt.date.today()
    fm = build_frontmatter(
        metadata, body, number,
        status=status, tagline=args.tagline, jedi_fate=args.jedi_fate,
        published_at=today,
    )

    target_name = existing or f"{number:02d}-{slugify(fm['title'])}.md"
    slug = target_name.removesuffix(".md")
    # Build preview assets in a disposable directory for dry runs.  The
    # generated frontmatter still shows the paths that a real publish would
    # produce, without mutating the site checkout.
    staging_dir = tempfile.TemporaryDirectory(prefix="publish-dry-run-") if args.dry_run else None
    try:
        asset_root = Path(staging_dir.name) if staging_dir is not None else site_repo
        cover_value = install_cover(asset_root, episode_dir, slug)
        if cover_value:
            fm["cover"] = cover_value
        plates = install_day_plates(asset_root, episode_dir, slug)
        if plates:
            fm["plates"] = {day: path for day, path in sorted(plates.items())}
        downloads = install_downloads(asset_root, episode_dir, slug)
        if downloads:
            fm["downloads"] = downloads
        rendered = render_episode_md(fm, body, source_id)

        problems = validate(fm, rendered)
        if problems:
            sys.exit("error: validation failed:\n  - " + "\n  - ".join(problems))
    finally:
        if staging_dir is not None:
            staging_dir.cleanup()

    verb = "update" if existing else "publish"
    print(f"{verb}: EP{number} \"{fm['title']}\" ({fm['status']}, {words:,} words)")
    print(f"  source:  {episode_dir}")
    print(f"  target:  {site_repo / 'episodes' / target_name}")

    if args.dry_run:
        print("dry run — nothing written.")
        print(rendered[:600])
        return

    target_path = site_repo / "episodes" / target_name
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(rendered, encoding="utf-8")

    run_git(site_repo, "add", str(target_path.relative_to(site_repo)))
    cover_site_path = site_repo / "assets" / "img" / slug
    if cover_site_path.is_dir():
        run_git(site_repo, "add", str(cover_site_path.relative_to(site_repo)))
    downloads_site_path = site_repo / "assets" / "downloads" / slug
    if downloads_site_path.is_dir():
        run_git(site_repo, "add", str(downloads_site_path.relative_to(site_repo)))
    msg = (
        f"{'update' if existing else 'publish'}: EP{number} {fm['title']} "
        f"(from pipeline {source_id})"
    )
    run_git(site_repo, "commit", "-m", msg)
    if args.no_push:
        print("committed locally (--no-push); push manually when ready.")
    else:
        run_git(site_repo, "push")
        print("pushed — GitHub Actions will rebuild and deploy Pages.")
    print(f"done: episodes/{target_name}")


def action_unpublish(args: argparse.Namespace, retire: bool) -> None:
    site_repo = Path(args.site_repo).expanduser().resolve()
    target = resolve_site_target(site_repo, args.unpublish or args.retire)
    rel = target.relative_to(site_repo)

    if args.dry_run:
        print(f"dry run — would {'retire (draft)' if retire else 'delete'} {rel}")
        return

    if retire:
        text = target.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        fm = yaml.safe_load(parts[1]) or {}
        fm["status"] = "draft"
        fm.pop("published_at", None)
        new = f"---\n{yaml.safe_dump(fm, sort_keys=False).strip()}\n---{parts[2]}"
        target.write_text(new, encoding="utf-8")
        run_git(site_repo, "add", str(rel))
        run_git(site_repo, "commit", "-m", f"retire: {rel.stem} (status -> draft)")
    else:
        target.unlink()
        run_git(site_repo, "add", str(rel))
        run_git(site_repo, "commit", "-m", f"unpublish: remove {rel.stem}")

    if args.no_push:
        print("committed locally (--no-push); push manually when ready.")
    else:
        run_git(site_repo, "push")
        print("pushed — Pages will rebuild without it.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode_dir", nargs="?",
                        help="episode directory in this repo (e.g. episodes/episode-...)")
    parser.add_argument("--publish", action="store_true",
                        help="go live immediately (default lands as draft)")
    parser.add_argument("--status", choices=["draft", "published"], default=None)
    parser.add_argument("--episode", type=int, default=None,
                        help="explicit episode number (default: next available)")
    parser.add_argument("--tagline", default=None)
    parser.add_argument("--jedi-fate", default=None,
                        help='override jedi_fate (e.g. "Killed by Qymaen")')
    parser.add_argument("--site-repo", default=str(DEFAULT_SITE_REPO))
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mark-complete", action="store_true",
                        help="stamp pipeline_complete after structural validation "
                             "(for runs that predate the marker)")
    parser.add_argument("--unpublish", metavar="SLUG",
                        help="delete an episode file from the site and push")
    parser.add_argument("--retire", metavar="SLUG",
                        help="flip an episode to draft instead of deleting")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.unpublish and args.retire:
        sys.exit("error: --unpublish and --retire are mutually exclusive")
    if args.unpublish or args.retire:
        action_unpublish(args, retire=bool(args.retire))
        return

    if not args.episode_dir:
        parser.error("an episode directory is required (or use --unpublish/--retire)")

    if args.publish and args.status:
        sys.exit("error: --publish and --status are mutually exclusive")
    args.status = "published" if args.publish else (args.status or "draft")

    action_publish(args)


if __name__ == "__main__":
    main()
