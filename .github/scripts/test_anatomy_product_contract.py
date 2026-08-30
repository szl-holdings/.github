#!/usr/bin/env python3
"""Network-free regression tests for the active Anatomy evidence architecture."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from urllib.parse import urlsplit

_GITHUB_DIR = Path(__file__).resolve().parents[1]
_REGISTRY_PATH = _GITHUB_DIR / "data" / "anatomy_map_registry.json"
_WORKFLOW_DIR = _GITHUB_DIR / "workflows"
_ACTIVE_WORKFLOWS = (
    _WORKFLOW_DIR / "anatomy-map-drift.yml",
    _WORKFLOW_DIR / "anatomy-map-product-drift.yml",
    _WORKFLOW_DIR / "reusable-anatomy-map-drift.yml",
)


class TestAnatomyProductContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.surfaces = cls.registry.get("surfaces", [])

    def test_registry_is_current_and_ids_are_unique(self) -> None:
        self.assertGreaterEqual(int(self.registry.get("schema", 0)), 2)
        ids = [str(row.get("id", "")) for row in self.surfaces]
        self.assertTrue(all(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_folded_hf_space_is_not_an_active_surface(self) -> None:
        ids = [str(row.get("id", "")) for row in self.surfaces]
        kinds = [str(row.get("kind", "")) for row in self.surfaces]
        self.assertNotIn("hf-anatomy", ids)
        self.assertNotIn("hf_space", kinds)
        for row in self.surfaces:
            self.assertNotEqual(row.get("space"), "SZLHOLDINGS/anatomy")

    def test_product_origin_is_exact_and_credential_free(self) -> None:
        product_rows = [
            row for row in self.surfaces
            if row.get("id") == "a11oy-anatomy-product"
        ]
        self.assertEqual(len(product_rows), 1)
        row = product_rows[0]
        self.assertEqual(row.get("kind"), "url")
        urls = row.get("urls")
        self.assertEqual(urls, ["https://a-11-oy.com/anatomy-map/data.js"])
        for url in urls:
            parsed = urlsplit(url)
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.hostname, "a-11-oy.com")
            self.assertIsNone(parsed.username)
            self.assertIsNone(parsed.password)

    def test_active_workflows_have_no_hf_secret_contract(self) -> None:
        forbidden = ("HF_TOKEN", "HF_READ_TOKEN", "secrets: inherit", "hf-anatomy")
        for path in _ACTIVE_WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{token!r} found in {path.name}")

    def test_product_watcher_targets_only_the_product_surface(self) -> None:
        text = (_WORKFLOW_DIR / "anatomy-map-product-drift.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("--only a11oy-anatomy-product", text)
        forbidden = (
            "--only hf-anatomy",
            "HF_TOKEN",
            "HF_READ_TOKEN",
            "huggingface.co",
            "hf.space",
        )
        for token in forbidden:
            self.assertNotIn(token, text)

    def test_obsolete_hf_watcher_is_removed(self) -> None:
        self.assertFalse((_WORKFLOW_DIR / "anatomy-map-hf-drift.yml").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
