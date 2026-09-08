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
    r"(?P<datasets>[0-9]+) datasets\b"
)


class PublicInventoryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(
            (ROOT / "docs/ESTATE_ALIGNMENT_CONTRACT_V1.json").read_text(
                encoding="utf-8"
            )
        )
        self.inventory = json.loads(
            (ROOT / "profile/public-inventory.json").read_text(encoding="utf-8")
        )
        self.expected = self.inventory["counts"]
        self.documents = {
            "profile": ROOT / "profile/README.md",
            "hub_card": ROOT / "huggingface/org-card/README.md",
        }

    def test_portfolio_profile_binds_current_counts_to_the_dated_public_snapshot(self) -> None:
        for name, path in {"profile": self.documents["profile"]}.items():
            with self.subTest(document=name):
                source = path.read_text(encoding="utf-8")
                # A historical paragraph must never satisfy the current-state gate.
                current = re.search(
                    r"^## Current state\s*\n(.*?)(?=^## |\Z)",
                    source,
                    flags=re.MULTILINE | re.DOTALL,
                )
                self.assertIsNotNone(current)
                match = COUNT_LINE.search(current.group(1))
                self.assertIsNotNone(match)
                observed = {
                    key: int(value)
                    for key, value in match.groupdict().items()
                }
                self.assertEqual(observed, self.expected)
                self.assertIn(self.inventory["observed_at"], current.group(1))
                self.assertIn(self.inventory["scope"]["id"], current.group(1))
                self.assertIn("profile/public-inventory.json", current.group(1))
                self.assertIn(self.inventory["source_revision"], current.group(1))
                self.assertIn("HISTORICAL", source)
                self.assertIn("16 portfolio Spaces", source)
                self.assertIn("1 inventory-only Space", source)

    def test_scientist_entry_points_do_not_present_inventory_counts(self) -> None:
        for path in (self.documents["hub_card"], ROOT / "huggingface/org-card/index.html"):
            with self.subTest(document=path):
                source = path.read_text(encoding="utf-8")
                self.assertIsNone(COUNT_LINE.search(source))
                self.assertNotIn("portfolio Spaces", source)
                self.assertNotIn("governedKeep", source)
                self.assertIn("GEO GSE85241", source)

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
        required_destinations = (
            "https://a-11-oy.com",
            "https://a11oy.net",
            "https://github.com/szl-holdings",
            "https://huggingface.co/SZLHOLDINGS",
        )
        for destination in required_destinations:
            self.assertRegex(source, r"\[[^\]\n]+\]\(" + re.escape(destination) + r"\)")
        # The canonical fleet, not retired Channel A/B copy, owns navigation.
        self.assertIn("https://github.com/szl-holdings/szl-router", source)
        self.assertIn("https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live", source)
        self.assertNotIn("·`[Channel B]", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
