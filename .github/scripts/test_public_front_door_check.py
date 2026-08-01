import unittest
from pathlib import Path

import public_front_door_check as check


class FrontMatterTests(unittest.TestCase):
    def test_reads_emoji_from_leading_front_matter(self):
        document = "---\nsdk: static\nemoji: 🛡️\n---\n# Card\n"
        self.assertEqual(check.front_matter_value(document, "emoji"), "🛡️")

    def test_ignores_emoji_line_in_card_body(self):
        document = "---\nsdk: static\n---\n# Card\nemoji: 🛡️\n"
        self.assertIsNone(check.front_matter_value(document, "emoji"))

    def test_rejects_non_leading_front_matter(self):
        document = "# Card\n---\nemoji: 🛡️\n---\n"
        self.assertIsNone(check.front_matter_value(document, "emoji"))

    def test_approved_value_is_exact(self):
        self.assertEqual(check.HUB_CARD_EMOJI, "🛡️")
        self.assertNotEqual(check.HUB_CARD_EMOJI, "𠀀")


    def test_org_card_short_description_fits_hugging_face_limit(self):
        root = Path(__file__).resolve().parents[2]
        document = (root / "huggingface/org-card/README.md").read_text(encoding="utf-8")
        description = check.front_matter_value(document, "short_description")
        self.assertIsNotNone(description)
        self.assertLessEqual(len(description or ""), 60)


if __name__ == "__main__":
    unittest.main()
