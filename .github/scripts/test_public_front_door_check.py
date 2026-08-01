import unittest
from pathlib import Path
from types import SimpleNamespace

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


class RequiredAssetBindingTests(unittest.TestCase):
    def test_accepts_exact_destination_source_bindings(self):
        root = Path("C:/repo")
        files = [
            SimpleNamespace(destination=destination, source=root / source)
            for destination, source in check.REQUIRED_HF_ASSETS.items()
        ]
        self.assertEqual(check.required_asset_mismatches(root, files), {})

    def test_rejects_existing_but_wrong_source(self):
        root = Path("C:/repo")
        files = [
            SimpleNamespace(
                destination=destination,
                source=root / ("profile/assets/wrong.svg" if index == 0 else source),
            )
            for index, (destination, source) in enumerate(check.REQUIRED_HF_ASSETS.items())
        ]
        mismatches = check.required_asset_mismatches(root, files)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(next(iter(mismatches.values()))["actual"], "profile/assets/wrong.svg")


if __name__ == "__main__":
    unittest.main()
