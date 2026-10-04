#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import hashlib
import importlib.util
from html import unescape
from pathlib import Path
import re
import unittest
import tempfile


ROOT = Path(__file__).resolve().parents[2]
COUNT_LINE = re.compile(
    r"(?P<spaces>[0-9]+) public Spaces, "
    r"(?P<models>[0-9]+) model repositories, "
    r"(?P<kernels>[0-9]+) native kernels, "
    r"(?P<datasets>[0-9]+) datasets\b"
)
SPEC = importlib.util.spec_from_file_location("profile_inventory", ROOT / ".github/scripts/render_profile_inventory.py")
render_inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_inventory)


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

    def test_front_doors_bind_current_counts_to_the_dated_public_snapshot(self) -> None:
        for name, path in self.documents.items():
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

    def test_static_front_door_uses_the_same_dated_public_snapshot(self) -> None:
        source = (ROOT / "huggingface/org-card/index.html").read_text(encoding="utf-8")
        current = re.search(
            r'<p data-szl-inventory="current">(.*?)</p>', source, re.DOTALL
        )
        self.assertIsNotNone(current)
        text = unescape(re.sub(r"<[^>]+>", "", current.group(1)))
        match = COUNT_LINE.search(text)
        self.assertIsNotNone(match)
        self.assertEqual(
            {key: int(value) for key, value in match.groupdict().items()},
            self.expected,
        )
        self.assertIn(self.inventory["observed_at"], text)
        self.assertIn(self.inventory["scope"]["id"], text)
        self.assertIn("not a live count", text)
        self.assertIn("profile/public-inventory.json", source)
        self.assertIn(self.inventory["source_revision"], source)

    def test_static_historical_inventory_is_explicitly_separate(self) -> None:
        source = (ROOT / "huggingface/org-card/index.html").read_text(encoding="utf-8")
        historical = re.search(
            r'<p data-szl-inventory="historical">(.*?)</p>', source, re.DOTALL
        )
        self.assertIsNotNone(historical)
        snapshot = self.contract["huggingface_inventory_snapshot"]
        for marker in (
            "HISTORICAL",
            f'{snapshot["portfolio_space_count"]} portfolio Spaces',
            f'{snapshot["model_count"]} models',
            f'{snapshot["dataset_count"]} datasets',
            "1 inventory-only Space",
            "Yarqa",
            "governedKeep=false",
            "not current Hub membership or visibility",
        ):
            self.assertIn(marker, historical.group(1))
        self.assertNotIn("This measured Hub inventory", source)

    def test_visible_static_counters_match_all_four_namespaces(self) -> None:
        source = (ROOT / "huggingface/org-card/index.html").read_text(encoding="utf-8")
        pairs = re.findall(r'<li data-szl-inventory-kind="([a-z]+)"><strong>([0-9]+)</strong>', source)
        self.assertEqual(len(pairs), 4)
        self.assertEqual({kind: int(count) for kind, count in pairs}, self.expected)

    def test_generated_sections_have_no_drift(self) -> None:
        self.assertEqual(render_inventory.refresh(ROOT, self.inventory, check=True), [])

    def test_stale_visible_counter_is_detected_even_when_paragraph_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in ("profile/README.md", "huggingface/org-card/README.md", "huggingface/org-card/index.html"):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                content = (ROOT / relative).read_text()
                if target.suffix == ".html":
                    content = re.sub(r'(data-szl-inventory-kind="kernels"><strong>)[0-9]+', r'\g<1>999', content)
                target.write_text(content)
            self.assertEqual(render_inventory.refresh(root, self.inventory, check=True), ["huggingface/org-card/index.html"])

    def test_binding_does_not_infer_provider_or_readiness_from_membership(self) -> None:
        for key in ("production_authorization", "runtime_readiness_inferred", "model_quality_inferred"):
            self.assertIs(self.inventory[key], False)
        self.assertEqual(self.inventory["scope"]["identity_key"], ["kind", "id"])
        self.assertIn("Native kernel IDs may also appear", render_inventory.markdown(self.inventory))

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


class BindingRefreshTests(unittest.TestCase):
    def manifest(self) -> dict:
        return {
            "org": "SZLHOLDINGS", "observedAt": "2026-10-04T15:36:53Z",
            "inventoryScope": {"visibility": "public-only", "authenticated": False,
                               "privateAssetsIncluded": False},
            "counts": {"models": 1, "kernels": 1, "datasets": 0, "spaces": 0},
            "inventory": {
                "models": [{"id": "SZLHOLDINGS/same-id", "repoType": "model", "private": False}],
                "kernels": [{"id": "SZLHOLDINGS/same-id", "repoType": "kernel", "private": False}],
                "datasets": [], "spaces": [],
            },
        }

    def bind(self, manifest: dict, *, blob: str | None = None) -> dict:
        raw = json.dumps(manifest).encode()
        expected = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        return render_inventory.make_binding(raw, "1" * 40, blob or expected)

    def test_model_and_native_kernel_same_id_remain_separate(self) -> None:
        record = self.bind(self.manifest())
        self.assertEqual(record["counts"], {"models": 1, "kernels": 1, "datasets": 0, "spaces": 0})
        render_inventory.validate_binding(record)

    def test_wrong_blob_cannot_rebind_counters(self) -> None:
        with self.assertRaisesRegex(render_inventory.InventoryError, "blob"):
            self.bind(self.manifest(), blob="0" * 40)

    def test_incomplete_foreign_duplicate_and_private_membership_fail_closed(self) -> None:
        mutations = (
            lambda m: m["inventory"].pop("kernels"),
            lambda m: m["inventory"]["models"][0].update(id="other-org/same-id"),
            lambda m: m["inventory"]["models"][0].update(private=True),
            lambda m: m["inventory"]["kernels"][0].update(repoType="model"),
            lambda m: m["counts"].update(kernels=99),
            lambda m: m["inventoryScope"].update(authenticated=True),
            lambda m: m.update(observedAt="2026-02-31T00:00:00Z"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                manifest = self.manifest()
                mutation(manifest)
                with self.assertRaises(render_inventory.InventoryError):
                    self.bind(manifest)
        manifest = self.manifest()
        manifest["inventory"]["models"] *= 2
        manifest["counts"]["models"] = 2
        with self.assertRaisesRegex(render_inventory.InventoryError, "duplicate"):
            self.bind(manifest)

    def test_wrong_predicate_and_inferred_readiness_are_rejected(self) -> None:
        record = self.bind(self.manifest())
        record["runtime_readiness_inferred"] = True
        with self.assertRaises(render_inventory.InventoryError):
            render_inventory.validate_binding(record)
        record = self.bind(self.manifest())
        record["scope"] = {**record["scope"], "id": "hf-public-author-membership/v1"}
        with self.assertRaises(render_inventory.InventoryError):
            render_inventory.validate_binding(record)


if __name__ == "__main__":
    unittest.main(verbosity=2)
