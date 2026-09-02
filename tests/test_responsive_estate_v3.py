#!/usr/bin/env python3
"""Offline contract for the source-first Space responsive estate controller."""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "responsive_estate_v3.py"
CSS = ROOT / "assets" / "szl-space-responsive-v3.css"


class ResponsiveEstateV3Contract(unittest.TestCase):
    def setUp(self) -> None:
        self.script = SCRIPT.read_text(encoding="utf-8")
        self.css = CSS.read_text(encoding="utf-8")

    def test_python_parses_and_uses_commit_tree_separation(self) -> None:
        ast.parse(self.script)
        self.assertIn("base_tree_sha", self.script)
        self.assertIn('/git/commits/{plan.base_sha}', self.script)
        self.assertIn('"base_tree": plan.base_tree_sha', self.script)

    def test_controller_is_source_first_and_never_writes_hugging_face(self) -> None:
        self.assertIn("SOURCE_MAP_URL", self.script)
        self.assertIn("source_from_space_readme", self.script)
        self.assertIn("exact-name", self.script)
        self.assertIn("It never guesses an arbitrary", self.script)
        self.assertNotIn("create_commit(", self.script.lower())
        self.assertNotRegex(self.script, r"huggingface\.co/api/(?:spaces|repos)/[^\n]+(?:POST|PUT|DELETE)")

    def test_only_reviewed_holographic_hosts_are_patchable(self) -> None:
        expected = {
            "szl-holo-v2.css",
            "szl-hologram-v2.css",
            "szl-space-holo-v2.css",
            "szl-spectral-v2.css",
            "szl-holo-proof-v2.css",
        }
        module = self.script
        for name in expected:
            self.assertIn(f'"{name}"', module)
        self.assertIn("NO_REVIEWED_HOLOGRAPHIC_HOST", module)
        self.assertIn("refusing a blind entrypoint edit", module)

    def test_core_origins_are_excluded_from_cross_repo_rollout(self) -> None:
        for repo in ("a11oy", "a11oy-net", "szl-holdings.github.io", ".github"):
            self.assertIn(f'"{repo}"', self.script)

    def test_responsive_asset_covers_required_formats(self) -> None:
        for token in (
            "min-inline-size: 20rem",
            "@media (max-width: 47.999rem)",
            "orientation: landscape",
            "@media (min-width: 100rem)",
            "@media (min-width: 150rem)",
            "grid-template-columns: repeat(12",
            "container-type: inline-size",
            "Gradio and Streamlit",
        ):
            self.assertIn(token, self.css)

    def test_accessibility_and_framework_contract(self) -> None:
        for token in (
            "--szl-space-touch: 44px",
            "--szl-space-touch-coarse: 48px",
            ":focus-visible",
            "safe-area-inset-top",
            "safe-area-inset-bottom",
            "prefers-reduced-motion",
            "prefers-contrast: more",
            "forced-colors: active",
            "@media print",
            ".gradio-container",
            'data-testid="stHorizontalBlock"',
        ):
            self.assertIn(token, self.css)

    def test_asset_is_local_color_neutral_and_bounded(self) -> None:
        self.assertIsNone(re.search(r"https?://", self.css, re.I))
        self.assertEqual(self.css.count("{"), self.css.count("}"))
        self.assertLessEqual(len(self.css.encode("utf-8")), 28000)
        for prohibited in ("fetch(", "localstorage", "sessionstorage", "document.cookie", "analytics"):
            self.assertNotIn(prohibited, self.css.lower())

    def test_merge_is_green_only_and_sha_bound(self) -> None:
        self.assertIn("merge_green", self.script)
        self.assertIn('"sha": plan.head_sha', self.script)
        self.assertIn("CHECKS_FAILED", self.script)
        self.assertIn("MERGE_BLOCKED", self.script)
        self.assertIn("CHECKS_PENDING", self.script)
        self.assertIn("merge_method\": \"squash", self.script.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
