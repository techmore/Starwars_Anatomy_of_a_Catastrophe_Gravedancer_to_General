import json
import tempfile
import unittest
from pathlib import Path

from src.utils.series_bible import (
    BIBLE_PROMPT_MAX_CHARS,
    bible_path,
    build_entry_prompt,
    format_for_prompt,
    load_entries,
    parse_entry,
    update_entry,
)


def _entry(title: str, **overrides) -> dict:
    entry = {
        "title": title,
        "jedi": {"name": "Nyx Vex", "species": "Cerean", "fate": "escaped into the ruins"},
        "setting": "Jungle moon, dying red sun",
        "key_events": ["The hunt began", "A trap was sprung"],
        "injuries": ["Qymaen lost his left eye"],
        "artifacts": ["The carbonite queen"],
        "unresolved_threads": ["The queen's signal still broadcasts"],
        **overrides,
    }
    return entry


class TestSeriesBible(unittest.TestCase):
    def test_load_entries_without_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(load_entries(tmpdir), [])

    def test_update_entry_round_trip_replaces_same_title(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            update_entry(tmpdir, _entry("The Ashen Chain"))
            update_entry(tmpdir, _entry("Hollow Bridge"))
            update_entry(tmpdir, _entry("The Ashen Chain", setting="Revised setting"))

            entries = load_entries(tmpdir)
            titles = [entry["title"] for entry in entries]

            self.assertEqual(titles.count("The Ashen Chain"), 1)
            self.assertIn("Hollow Bridge", titles)
            revised = next(e for e in entries if e["title"] == "The Ashen Chain")
            self.assertEqual(revised["setting"], "Revised setting")
            self.assertTrue(revised["recorded_at"])
            self.assertTrue(bible_path(tmpdir).is_file())

    def test_load_entries_survives_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = bible_path(tmpdir)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(load_entries(tmpdir), [])

    def test_update_entry_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "episodes"
            update_entry(nested, _entry("Nested"))
            self.assertEqual([e["title"] for e in load_entries(nested)], ["Nested"])

    def test_parse_entry_accepts_plain_and_fenced_json(self):
        plain = '{"title": "Ash", "jedi": {"name": "Vex"}}'
        fenced = f"```json\n{plain}\n```"
        for text in (plain, fenced):
            parsed = parse_entry(text)
            self.assertEqual(parsed["title"], "Ash")

    def test_parse_entry_rejects_unusable_responses(self):
        self.assertIsNone(parse_entry("no json here"))
        self.assertIsNone(parse_entry('{"missing": "title"}'))
        self.assertIsNone(parse_entry(""))
        self.assertIsNone(parse_entry(None))

    def test_build_entry_prompt_contains_story_and_schema(self):
        prompt = build_entry_prompt("Ash", "## DAY 1: Ashfall\n\nProse.")
        self.assertIn('"Ash"', prompt)
        self.assertIn("## DAY 1: Ashfall", prompt)
        self.assertIn("unresolved_threads", prompt)

    def test_format_for_prompt_renders_digest_fields(self):
        text = format_for_prompt([_entry("The Ashen Chain")])
        self.assertIn('"The Ashen Chain"', text)
        self.assertIn("Nyx Vex", text)
        self.assertIn("escaped into the ruins", text)
        self.assertIn("Qymaen lost his left eye", text)
        self.assertIn("The carbonite queen", text)
        self.assertIn("The queen's signal still broadcasts", text)

    def test_format_for_prompt_empty_history_is_empty_string(self):
        self.assertEqual(format_for_prompt([]), "")

    def test_format_for_prompt_truncates_keeping_recent_tail(self):
        filler = {"title": "Filler", "setting": "x" * 3000}
        recent = _entry("Recent Episode")
        text = format_for_prompt([filler] * 10 + [recent])

        self.assertLessEqual(len(text), BIBLE_PROMPT_MAX_CHARS + 1)
        self.assertIn('"Recent Episode"', text)

    def test_bible_file_payload_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            update_entry(tmpdir, _entry("Shape Test"))
            payload = json.loads(bible_path(tmpdir).read_text(encoding="utf-8"))
            self.assertIsInstance(payload["episodes"], list)
            self.assertEqual(payload["episodes"][0]["title"], "Shape Test")


if __name__ == "__main__":
    unittest.main()
