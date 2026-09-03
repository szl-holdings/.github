#!/usr/bin/env python3
"""Network-free tests for the Public Experience v3 rollout extension."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / ".github" / "scripts" / "responsive_space_contract.py"
spec = importlib.util.spec_from_file_location("responsive_space_contract_test", MODULE)
assert spec and spec.loader
responsive = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = responsive
spec.loader.exec_module(responsive)


class Change:
    def __init__(self, path: str, content: str):
        self.path = path
        self.content = content


class ResponsiveSpaceContractTests(unittest.TestCase):
    def test_assets_cover_phone_tablet_desktop_theatre_and_zoom(self) -> None:
        css, javascript = responsive._read_assets()
        for marker in (
            "max-width: 479px",
            "min-width: 768px",
            "min-width: 1024px",
            "min-width: 1440px",
            "min-width: 1920px",
            "min-width: 2560px",
            "100dvh",
            "safe-area-inset",
            "--szl-touch-target",
            "--szl-touch-target-coarse",
            "--szl-effective-inline-size",
            "data-szl-zoom-tier",
            "overflow-x: clip",
            "prefers-reduced-motion",
            "prefers-contrast",
            "forced-colors",
            "@media print",
        ):
            self.assertIn(marker, css)
        for marker in (
            "__SZL_PUBLIC_EXPERIENCE_V3__",
            "szlPublicExperienceV3",
            "szlSpaceHoloV2",
            "szlViewportTier",
            "szlZoomTier",
            "szlAudience",
            "visualViewport",
            "requestAnimationFrame",
            "MutationObserver",
            "document.title",
            "effectiveWidth",
            "phone",
            "tablet",
            "theatre",
            "ultrawide",
        ):
            self.assertIn(marker, javascript)

    def test_assets_are_local_and_nontracking(self) -> None:
        css, javascript = responsive._read_assets()
        self.assertNotIn("@import", css)
        for token in (
            "fetch(",
            "XMLHttpRequest",
            "sendBeacon",
            "localStorage",
            "sessionStorage",
            "document.cookie",
        ):
            self.assertNotIn(token, javascript)
        self.assertEqual(css.count("{"), css.count("}"))

    def test_zoom_navigation_is_bounded_and_not_a_fixed_viewport_sheet(self) -> None:
        _, javascript = responsive._read_assets()
        self.assertIn(":host([data-szl-zoom-tier=high])", javascript)
        self.assertIn("position:absolute!important", javascript)
        self.assertIn("max-height:min(56dvh,420px)", javascript)
        self.assertIn("min-width:54px!important", javascript)
        self.assertIn("min-height:48px!important", javascript)
        self.assertIn("border-radius:10px!important", javascript)
        self.assertNotIn("nav{position:fixed!important", javascript)

    def test_empty_title_fallback_is_non_destructive(self) -> None:
        _, javascript = responsive._read_assets()
        self.assertIn('if (String(document.title || "").trim()) return;', javascript)
        self.assertIn('document.title = declaredIdentity() + " · SZL Holdings";', javascript)
        self.assertIn("SZLPublicExperience", javascript)
        self.assertIn("snapshot: snapshot", javascript)

    def test_append_once_is_idempotent(self) -> None:
        once = responsive._append_once("base", "SZL Public Experience v3\n", responsive.CSS_MARKER)
        twice = responsive._append_once(once, "SZL Public Experience v3\n", responsive.CSS_MARKER)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count(responsive.CSS_MARKER), 1)

    def _core(self, original_plan):
        def streamlit_helper():
            return (
                "markup = f\"\"\"<script>"
                "document.documentElement.dataset.szlSpaceSlug={slug!r};</script>"
                "\"\"\"\n"
            )

        return SimpleNamespace(
            read_assets=lambda root: ("base css", "base js", "{}"),
            plan_repository=original_plan,
            pr_body=lambda plan, digest: "base body",
            streamlit_helper=streamlit_helper,
            gradio_helper=lambda: "gradio helper",
            NEXT_LAYOUTS=("app/layout.tsx",),
            STATIC_INDEXES=("index.html",),
            PYTHON_ENTRIES=("app.py",),
            Change=Change,
            BRANCH="design/old",
        )

    def test_install_extends_assets_and_moves_review_branch(self) -> None:
        core = self._core(
            lambda *args, **kwargs: SimpleNamespace(
                status="planned",
                adapter="static",
                entrypoint="index.html",
                changes=[Change("szl-space-hologram.css", args[-2])],
            )
        )
        responsive.install(core)
        css, javascript, registry = core.read_assets(Path("unused"))
        self.assertIn(responsive.CSS_MARKER, css)
        self.assertIn(responsive.JS_MARKER, javascript)
        self.assertEqual(registry, "{}")
        self.assertEqual(core.BRANCH, "design/szl-public-experience-v3")
        helper = core.streamlit_helper()
        self.assertIn("dataset.szlPublicExperienceV3", helper)
        self.assertIn("dataset.szlViewportTier", helper)
        self.assertIn("dataset.szlZoomTier", helper)
        self.assertIn("document.title", helper)
        self.assertIn("SZL Holdings", helper)

    def test_already_integrated_repository_becomes_reviewable_refresh(self) -> None:
        core = self._core(
            lambda *args, **kwargs: SimpleNamespace(
                status="already-integrated",
                adapter=None,
                entrypoint=None,
                changes=[],
            )
        )
        responsive.install(core)

        class GitHub:
            @staticmethod
            def tree(full_name, default_branch):
                return [
                    {"path": "index.html"},
                    {"path": "szl-space-hologram.css"},
                    {"path": "szl-space-hologram.js"},
                ]

            @staticmethod
            def file(full_name, path, default_branch):
                return ("legacy v2 asset", "sha")

        css = "v2\nSZL Public Experience v3\n"
        javascript = "v2\n__SZL_PUBLIC_EXPERIENCE_V3__\n"
        plan = core.plan_repository(
            GitHub(),
            {"full_name": "szl-holdings/example", "default_branch": "main"},
            [],
            100,
            "test",
            css,
            javascript,
        )
        self.assertEqual(plan.status, "planned")
        self.assertEqual(plan.adapter, "responsive-existing-host")
        self.assertEqual(plan.entrypoint, "index.html")
        self.assertEqual(
            {change.path for change in plan.changes},
            {"szl-space-hologram.css", "szl-space-hologram.js"},
        )

    def test_product_owned_asset_host_is_refreshed_without_duplicate_shell(self) -> None:
        core = self._core(
            lambda *args, **kwargs: SimpleNamespace(
                status="planned",
                adapter="static",
                entrypoint="app/static/index.html",
                changes=[Change("app/static/szl-space-hologram.css", args[-2])],
            )
        )
        responsive.install(core)

        class GitHub:
            @staticmethod
            def tree(full_name, default_branch):
                return [
                    {"path": "app/static/index.html"},
                    {"path": "app/static/holo.css"},
                    {"path": "app/static/holo.js"},
                ]

            @staticmethod
            def file(full_name, path, default_branch):
                return ("product-owned asset", "sha")

        plan = core.plan_repository(
            GitHub(),
            {"full_name": "szl-holdings/david-leads", "default_branch": "main"},
            [],
            1000,
            "canonical source map",
            "combined css",
            "combined js",
        )
        self.assertEqual(plan.status, "planned")
        self.assertEqual(plan.adapter, "responsive-existing-host")
        self.assertEqual(plan.entrypoint, "app/static/index.html")
        self.assertEqual(
            {change.path for change in plan.changes},
            {"app/static/holo.css", "app/static/holo.js"},
        )
        for change in plan.changes:
            self.assertIn("SZL Public Experience v3" if change.path.endswith(".css") else "__SZL_PUBLIC_EXPERIENCE_V3__", change.content)

    def test_pr_body_states_additive_truth_boundary(self) -> None:
        core = self._core(
            lambda *args, **kwargs: SimpleNamespace(
                status="planned", adapter="static", entrypoint="index.html", changes=[]
            )
        )
        responsive.install(core)
        body = core.pr_body(SimpleNamespace(), "digest")
        self.assertIn("SZL Public Experience v3.1", body)
        self.assertIn("phone widths from 320px", body)
        self.assertIn("400% zoom", body)
        self.assertIn("fallback title", body)
        self.assertIn("investor", body)
        self.assertIn("additive", body.lower())
        self.assertIn("does not replace", body.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
