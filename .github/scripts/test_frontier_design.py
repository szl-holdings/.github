#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free regression tests for SZL Frontier Design Kernel v1."""
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / ".github" / "design" / "frontier-v1"
SCRIPT = ROOT / ".github" / "scripts" / "rollout_frontier_design.py"
WORKFLOW = ROOT / ".github" / "workflows" / "frontier-design-rollout.yml"

_spec = importlib.util.spec_from_file_location("rollout_frontier_design", SCRIPT)
assert _spec and _spec.loader
rollout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rollout)


class FrontierKernelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads((DESIGN / "brands.json").read_text(encoding="utf-8"))
        cls.css = (DESIGN / "szl-frontier.css").read_text(encoding="utf-8")
        cls.javascript = (DESIGN / "szl-frontier.js").read_text(encoding="utf-8")

    def test_registry_has_one_shared_kernel_and_three_distinct_adapters(self) -> None:
        self.assertEqual(self.registry["schema"], "szl.frontier-design.registry/v1")
        self.assertEqual(self.registry["version"], "1.0.0")
        self.assertEqual(set(self.registry["brands"]), {"a11oy", "killinchu", "hatun"})
        motifs = {record["motif"] for record in self.registry["brands"].values()}
        descriptors = {record["descriptor"] for record in self.registry["brands"].values()}
        self.assertEqual(len(motifs), 3)
        self.assertEqual(len(descriptors), 3)
        self.assertEqual(self.registry["asset_contract"]["network_fetches"], 0)
        self.assertEqual(self.registry["asset_contract"]["authority"], "PRESENTATION_ONLY")

    def test_css_exposes_shared_components_and_distinct_brand_tokens(self) -> None:
        for brand in ("a11oy", "killinchu", "hatun"):
            self.assertEqual(
                self.css.count(f'body[data-szl-frontier="{brand}"]'),
                1,
                brand,
            )
        for component in (
            ".szl-frontier-rail",
            ".szl-frontier-card",
            ".szl-frontier-button",
            ".szl-frontier-chip",
            ":focus-visible",
            "prefers-reduced-motion",
            "forced-colors",
        ):
            self.assertIn(component, self.css)
        self.assertNotIn("@import url", self.css.lower())
        self.assertNotRegex(self.css, r"https?://")

    def test_javascript_is_progressive_and_presentation_only(self) -> None:
        for brand in ("a11oy", "killinchu", "hatun"):
            self.assertIn(f"{brand}:", self.javascript)
        for required in (
            "DOMContentLoaded",
            "IntersectionObserver",
            "prefers-reduced-motion",
            "szl:frontier-ready",
            "PRESENTATION_ONLY",
        ):
            self.assertIn(required, self.javascript)
        for forbidden in (
            "eval(",
            "new Function(",
            ".innerHTML",
            "document.cookie",
            "localStorage",
            "sessionStorage",
            "fetch(",
            "XMLHttpRequest",
        ):
            self.assertNotIn(forbidden, self.javascript)

    def test_html_patcher_is_marker_bound_and_idempotent(self) -> None:
        source = "<!doctype html><html><head><title>x</title></head><body class=\"existing\"><main>x</main></body></html>"
        once = rollout.patch_entry(
            source,
            brand="killinchu",
            css_url="/static/szl/frontier-v1/szl-frontier.css",
            js_url="/static/szl/frontier-v1/szl-frontier.js",
        )
        twice = rollout.patch_entry(
            once,
            brand="killinchu",
            css_url="/static/szl/frontier-v1/szl-frontier.css",
            js_url="/static/szl/frontier-v1/szl-frontier.js",
        )
        self.assertEqual(once, twice)
        self.assertEqual(once.count(rollout.HEAD_START), 1)
        self.assertEqual(once.count(rollout.BODY_START), 1)
        self.assertIn('class="existing szl-frontier"', once)
        self.assertIn('data-szl-frontier="killinchu"', once)
        self.assertIn("<main>x</main>", once)

    def test_unknown_or_malformed_pages_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            rollout.patch_entry(
                "<html><head></head><main>no body</main></html>",
                brand="hatun",
                css_url="x.css",
                js_url="x.js",
            )
        with self.assertRaises(ValueError):
            rollout.patch_entry(
                "<body></body>",
                brand="a11oy",
                css_url="x.css",
                js_url="x.js",
            )

    def test_dynamic_discovery_excludes_docs_tests_and_dependencies(self) -> None:
        selected = rollout.dynamic_entrypoints(
            [
                "docs/index.html",
                "tests/index.html",
                "node_modules/pkg/index.html",
                "web/hatun.html",
                "web/index.html",
                "server.py",
            ],
            brand="hatun",
            excluded_directories={"docs", "tests", "node_modules"},
            maximum=3,
        )
        self.assertIn("web/hatun.html", selected)
        self.assertNotIn("docs/index.html", selected)
        self.assertNotIn("tests/index.html", selected)
        self.assertNotIn("node_modules/pkg/index.html", selected)

    def test_rollout_never_pushes_a_default_branch(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('branch = f"{branch_prefix}-{source_revision[:12]}"', source)
        self.assertIn('"direct_main_push": False', source)
        self.assertNotRegex(source, r"git[^\n]+push[^\n]+origin[^\n]+(?:main|master)[\"']")
        self.assertIn("git", source)
        self.assertIn("diff", source)
        self.assertIn("--check", source)
        self.assertIn("py_compile", source)

    def test_workflow_is_pinned_and_emits_a_receipt(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch", text)
        self.assertIn("rollout_frontier_design.py", text)
        self.assertIn("test_frontier_design.py", text)
        self.assertIn("frontier-design-rollout-receipt.json", text)
        self.assertIn("GH_ADMIN_TOKEN", text)
        for uses_line in re.findall(r"^\s*uses:\s*(.+)$", text, flags=re.MULTILINE):
            self.assertRegex(uses_line, r"@[0-9a-f]{40}(?:\s|$)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
