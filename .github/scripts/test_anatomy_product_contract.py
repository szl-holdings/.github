#!/usr/bin/env python3
"""Network-free regression tests for the active Living Anatomy architecture."""
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
        self.assertGreaterEqual(int(self.registry.get("schema", 0)), 3)
        ids = [str(row.get("id", "")) for row in self.surfaces]
        self.assertTrue(all(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_hf_space_is_an_active_public_credential_free_surface(self) -> None:
        rows = [row for row in self.surfaces if row.get("id") == "hf-anatomy"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.get("kind"), "url")
        self.assertEqual(row.get("extract"), "invariant_scan")
        urls = row.get("urls")
        self.assertEqual(
            urls,
            [
                "https://szlholdings-anatomy.hf.space/data.js",
                "https://szlholdings-anatomy.hf.space/index.html",
            ],
        )
        for url in urls:
            parsed = urlsplit(url)
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.hostname, "szlholdings-anatomy.hf.space")
            self.assertIsNone(parsed.username)
            self.assertIsNone(parsed.password)

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
        forbidden = (
            "HF_TOKEN",
            "HF_READ_TOKEN",
            "HF_ORG_TOKEN",
            "HF_WRITE_TOKEN",
            "secrets: inherit",
        )
        for path in _ACTIVE_WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{token!r} found in {path.name}")

    def test_cross_surface_watcher_includes_the_hf_runtime(self) -> None:
        text = (_WORKFLOW_DIR / "anatomy-map-drift.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("HF Space, and product origin", text)
        self.assertIn("Compare active Living Anatomy surfaces", text)
        self.assertNotIn("--skip-kind url", text)

    def test_product_watcher_targets_only_the_product_surface(self) -> None:
        text = (_WORKFLOW_DIR / "anatomy-map-product-drift.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("--only a11oy-anatomy-product", text)
        self.assertNotIn("--only hf-anatomy", text)
        for token in ("HF_TOKEN", "HF_READ_TOKEN", "HF_ORG_TOKEN", "HF_WRITE_TOKEN"):
            self.assertNotIn(token, text)

    def test_obsolete_mutating_hf_watcher_is_absent(self) -> None:
        self.assertFalse((_WORKFLOW_DIR / "anatomy-map-hf-drift.yml").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
