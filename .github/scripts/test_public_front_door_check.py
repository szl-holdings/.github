import unittest

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


if __name__ == "__main__":
    unittest.main()
