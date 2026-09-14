"""text_safety.sanitize : un texte tapé par un membre ne doit jamais pinguer tout le serveur."""

import unittest

from text_safety import sanitize


class SanitizeTest(unittest.TestCase):
    def test_mass_mentions_are_broken(self):
        cleaned = sanitize("salut @everyone et @here")
        self.assertNotIn("@everyone", cleaned)
        self.assertNotIn("@here", cleaned)
        self.assertIn("everyone", cleaned)

    def test_text_is_truncated(self):
        self.assertEqual(len(sanitize("x" * 500, 40)), 40)

    def test_empty_values(self):
        self.assertEqual(sanitize(None), "")
        self.assertEqual(sanitize(""), "")


if __name__ == "__main__":
    unittest.main()
