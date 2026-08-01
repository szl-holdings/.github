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

    def test_normalizes_quoted_short_description(self):
        document = '---\nshort_description: "Clear boundaries"\n---\n# Card\n'
        self.assertEqual(check.hub_short_description(document), "Clear boundaries")

    def test_hub_short_description_limit_is_exact(self):
        self.assertEqual(check.HUB_SHORT_DESCRIPTION_MAX_LENGTH, 60)
        self.assertTrue(check.short_description_within_limit("x" * 60))
        self.assertFalse(check.short_description_within_limit("x" * 61))
        self.assertFalse(check.short_description_within_limit(None))


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


class CheckCountingTests(unittest.TestCase):
    def test_require_counts_passes_and_failures(self):
        original = check.CHECKS_EXECUTED
        try:
            check.CHECKS_EXECUTED = 0
            failures = []
            check.require(True, "pass", failures)
            check.require(False, "fail", failures)
            self.assertEqual(check.CHECKS_EXECUTED, 2)
            self.assertEqual(failures, ["fail"])
        finally:
            check.CHECKS_EXECUTED = original


class WorkflowPushPathTests(unittest.TestCase):
    def test_reads_only_active_on_push_paths(self):
        workflow = '''
"on":
  push:
    branches: [main]
    paths:
      - "profile/assets/**"
      - 'huggingface/org-card/**' # publication inputs
  workflow_dispatch:
'''
        self.assertEqual(
            check.workflow_push_paths(workflow),
            {"profile/assets/**", "huggingface/org-card/**"},
        )

    def test_ignores_comments_and_unrelated_scalars(self):
        workflow = '''
# on:
#   push:
#     paths:
#       - "profile/assets/**"
env:
  EXAMPLE: "profile/assets/**"
on:
  workflow_dispatch:
'''
        self.assertEqual(check.workflow_push_paths(workflow), set())


if __name__ == "__main__":
    unittest.main()
