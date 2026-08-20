import unittest

from src.utils.prompt_schema import MIN_CHAPTERS_PER_DAY
from src.utils.story_generator import OUTLINE_RECOVERY_ATTEMPTS, _retry_outline


def _valid_outline(num_days: int) -> str:
    parts = ["## EPISODE ARC\nA self-contained arc with a meaningful ending."]
    for day in range(1, num_days + 1):
        parts.append(f"## DAY {day}: Distinct event for day {day}")
        for chapter in range(1, MIN_CHAPTERS_PER_DAY + 1):
            beats = "\n".join(
                f"Beat {b}: Distinct action for day {day} chapter {chapter} beat {b}."
                for b in range(1, 5)
            )
            parts.append(f"- Chapter {chapter}: {beats}")
        parts.append(f"- Ending hook: A distinct unresolved hook for day {day}.")
        parts.append(f"- Purpose: The distinct goal for day {day}.")
    return "\n\n".join(parts)


def _truncated_outline(requested_days: int, complete_days: int) -> str:
    """The tail case the multi_pass crash hit: model stops before the final day."""
    full = _valid_outline(requested_days)
    marker = f"\n## DAY {complete_days + 1}:"
    idx = full.find(marker)
    if idx == -1:
        return full
    return full[:idx].rstrip()


class TestOutlineRetry(unittest.TestCase):
    def test_valid_outline_passes_first_attempt(self):
        calls = []
        outline, errors = _retry_outline(
            lambda: calls.append(0) or _valid_outline(2),
            2,
            OUTLINE_RECOVERY_ATTEMPTS,
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 1)
        self.assertIn("## DAY 2:", outline)

    def test_truncated_outline_retries_then_succeeds(self):
        calls = []

        def gen():
            calls.append(0)
            if len(calls) == 1:
                return _truncated_outline(3, 2)
            return _valid_outline(3)

        outline, errors = _retry_outline(gen, 3, OUTLINE_RECOVERY_ATTEMPTS)
        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 2)
        self.assertIn("## DAY 3:", outline)

    def test_persistent_truncation_exhausts_attempts(self):
        calls = []
        gen = lambda: calls.append(0) or _truncated_outline(3, 2)
        outline, errors = _retry_outline(gen, 3, 3)
        self.assertEqual(len(calls), 3)
        self.assertTrue(errors)
        self.assertIn("truncated", " ".join(errors))
        self.assertIn("## DAY 3:", " ".join(errors))

    def test_on_attempt_called_every_round(self):
        emissions = []

        def gen():
            return _truncated_outline(2, 1)

        def on_attempt(attempt, total):
            emissions.append((attempt, total))

        _, errors = _retry_outline(gen, 2, 3, on_attempt=on_attempt)
        self.assertEqual(emissions, [(1, 3), (2, 3), (3, 3)])
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()