#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
COUNT_LINE = re.compile(
    r"(?P<spaces>[0-9]+) public Spaces, "
    r"(?P<models>[0-9]+) models, "
    r"(?P<datasets>[0-9]+) datasets\."
)


class PublicInventoryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(
            (ROOT / "docs/ESTATE_ALIGNMENT_CONTRACT_V1.json").read_text(
                encoding="utf-8"
            )
        )
        snapshot = self.contract["huggingface_inventory_snapshot"]
        self.expected = {
            "spaces": int(snapshot["public_space_count"]),
            "models": int(snapshot["model_count"]),
            "datasets": int(snapshot["dataset_count"]),
        }
        self.documents = {
            "profile": ROOT / "profile/README.md",
            "hub_card": ROOT / "huggingface/org-card/README.md",
        }

    def test_both_front_doors_publish_the_exact_public_inventory(self) -> None:
        for name, path in self.documents.items():
            with self.subTest(document=name):
                source = path.read_text(encoding="utf-8")
                match = COUNT_LINE.search(source)
                self.assertIsNotNone(match)
                observed = {
                    key: int(value)
                    for key, value in match.groupdict().items()
                }
                self.assertEqual(observed, self.expected)
                self.assertIn("16 portfolio Spaces", source)
                self.assertIn("1 inventory-only Space", source)
                self.assertIn("Yarqa", source)
                self.assertIn("governedKeep=false", source)

    def test_public_markdown_has_no_hidden_control_characters(self) -> None:
        for name, path in self.documents.items():
            with self.subTest(document=name):
                source = path.read_text(encoding="utf-8")
                offenders = sorted(
                    {
                        ord(character)
                        for character in source
                        if ord(character) < 32
                        and character not in {"\n", "\r", "\t"}
                    }
                )
                self.assertEqual(offenders, [])
                self.assertNotIn("¡", source)

    def test_profile_keeps_all_public_navigation_paths_well_formed(self) -> None:
        source = self.documents["profile"].read_text(encoding="utf-8")
        required = (
            "[**Product**](https://a-11-oy.com)",
            "[**Proof**](https://a11oy.net)",
            "[**GitHub**](https://github.com/szl-holdings)",
            "[**Hugging Face**](https://huggingface.co/SZLHOLDINGS)",
            "[Channel A](https://huggingface.co/spaces/SZLHOLDINGS/immune)",
            "[Channel B](https://huggingface.co/spaces/SZLHOLDINGS/immune-lattice)",
        )
        for marker in required:
            self.assertIn(marker, source)
        self.assertNotIn("·`[Channel B]", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
