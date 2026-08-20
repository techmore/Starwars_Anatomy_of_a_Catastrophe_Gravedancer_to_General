import unittest

from src.components.ui import preformatted_html


class TestUiHelpers(unittest.TestCase):
    def test_preformatted_model_text_is_html_escaped(self):
        rendered = preformatted_html("<script>alert('x')</script>")

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
