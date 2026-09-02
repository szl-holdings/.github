#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

# Keep this test network-free and independent of the real credential module.
stub = types.ModuleType("ci_health_digest_http")
stub.ApiError = type("ApiError", (RuntimeError,), {})
stub.DigestError = type("DigestError", (RuntimeError,), {})
stub.ReaderSelectionError = type("ReaderSelectionError", (RuntimeError,), {})
stub.request_json = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network forbidden"))
stub.select_reader = lambda: (_ for _ in ()).throw(AssertionError("reader forbidden"))
sys.modules["ci_health_digest_http"] = stub

MODULE_PATH = Path(__file__).with_name("github_responsive_estate_audit.py")
spec = importlib.util.spec_from_file_location("github_responsive_estate_audit", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ResponsiveEstateAuditTests(unittest.TestCase):
    def metadata(self, **overrides):
        value = {
            "name": "demo",
            "full_name": "szl-holdings/demo",
            "archived": False,
            "private": False,
            "visibility": "public",
            "default_branch": "main",
            "has_pages": False,
            "homepage": "",
        }
        value.update(overrides)
        return value

    def entry(self, path: str, size: int = 100):
        return module.TreeEntry(path=path, sha="a" * 40, size=size, type="blob")

    def test_archived_repository_is_not_forced_into_ui_contract(self):
        classification, scope = module.classify_repository(
            self.metadata(archived=True), (), ""
        )
        self.assertEqual((classification, scope), ("ARCHIVED", "none"))

    def test_static_pages_repository_is_public_web(self):
        classification, scope = module.classify_repository(
            self.metadata(has_pages=True), (self.entry("index.html"),), ""
        )
        self.assertEqual((classification, scope), ("PUBLIC_WEB", "web_ui"))

    def test_library_is_not_misclassified_as_web(self):
        entries = (self.entry("pyproject.toml"), self.entry("src/pkg/core.py"))
        classification, scope = module.classify_repository(
            self.metadata(), entries, ""
        )
        self.assertEqual((classification, scope), ("LIBRARY", "none"))

    def test_complete_responsive_source_detects_core_and_advanced_signals(self):
        text = """
        <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
        <style>
        .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(16rem,1fr));min-width:0}
        button{min-height:44px}
        pre,table{overflow-x:auto;max-width:100%}
        main{min-height:100dvh;padding-bottom:env(safe-area-inset-bottom)}
        @media (prefers-reduced-motion:reduce){*{animation:none}}
        @media (forced-colors:active){button{border:1px solid ButtonText}}
        </style>
        """
        signals = module.detect_signals(
            ("index.html", ".github/workflows/playwright-responsive.yml"),
            (text,),
        )
        self.assertTrue(signals.viewport)
        self.assertTrue(signals.responsive_layout)
        self.assertTrue(signals.overflow_containment)
        self.assertTrue(signals.reduced_motion)
        self.assertTrue(signals.contrast_modes)
        self.assertTrue(signals.touch_targets)
        self.assertTrue(signals.safe_area)
        self.assertTrue(signals.dynamic_viewport)
        self.assertTrue(signals.local_wide_scroll)
        self.assertTrue(signals.automated_browser_audit)

    def test_public_web_missing_core_controls_is_blocking(self):
        signals = module.SourceSignals(*([False] * 12))
        status, blocking, missing, limitations = module.evaluate_status(
            classification="PUBLIC_WEB",
            tree_complete=True,
            selected=(self.entry("index.html"),),
            signals=signals,
        )
        self.assertEqual(status, "ACTION_REQUIRED")
        self.assertTrue(blocking)
        self.assertIn("viewport", missing)
        self.assertFalse(limitations)

    def test_private_web_missing_core_controls_is_actionable_not_release_blocking(self):
        signals = module.SourceSignals(*([False] * 12))
        status, blocking, _missing, _limitations = module.evaluate_status(
            classification="PRIVATE_WEB",
            tree_complete=True,
            selected=(self.entry("index.html"),),
            signals=signals,
        )
        self.assertEqual(status, "ACTION_REQUIRED")
        self.assertFalse(blocking)

    def test_source_ready_without_browser_automation_keeps_visible_gap(self):
        values = [True, True, True, True, False, False, False, False, False, False, False, False]
        signals = module.SourceSignals(*values)
        status, blocking, missing, _limitations = module.evaluate_status(
            classification="PUBLIC_WEB",
            tree_complete=True,
            selected=(self.entry("index.html"),),
            signals=signals,
        )
        self.assertEqual(status, "SOURCE_READY_AUDIT_GAP")
        self.assertFalse(blocking)
        self.assertEqual(missing, ("automated_browser_audit",))

    def test_truncated_public_tree_fails_closed(self):
        values = [True, True, True, True, False, False, False, False, False, False, False, True]
        signals = module.SourceSignals(*values)
        status, blocking, _missing, limitations = module.evaluate_status(
            classification="PUBLIC_WEB",
            tree_complete=False,
            selected=(self.entry("index.html"),),
            signals=signals,
        )
        self.assertEqual(status, "EVIDENCE_INCOMPLETE")
        self.assertTrue(blocking)
        self.assertIn("recursive Git tree was truncated", limitations)

    def test_candidate_selection_is_bounded_and_skips_vendor(self):
        entries = [self.entry(f"pages/page-{index}.html") for index in range(40)]
        entries.append(self.entry("vendor/index.html"))
        selected = module.select_source_entries(entries)
        self.assertLessEqual(len(selected), module.MAX_FILES_PER_REPOSITORY)
        self.assertNotIn("vendor/index.html", {item.path for item in selected})


if __name__ == "__main__":
    unittest.main(verbosity=2)
